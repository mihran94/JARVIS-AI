"""Bridge request handling, independent of any HTTP server.

This module deliberately does not bind a socket. Choosing the listening
interface is an operator decision, and the default is the loopback interface
only. A private tunnel such as Tailscale or WireGuard is the expected way to
reach a paired phone, and no control port is published to the public internet.

`handle()` is the whole protocol surface:

    GET  /api/status                   -> PC status
    GET  /api/jobs                     -> {"jobs": [...]}
    GET  /api/jobs/<id>                -> one job record
    POST /api/jobs                     -> one job record
    POST /api/jobs/<id>/cancel         -> {"ok": true|false}
    POST /api/chat                     -> the desktop answers one message
    GET  /api/memory                   -> {"memory": [...]}
    POST /api/memory                   -> one memory entry
    GET  /api/notifications            -> {"notifications": [...]}
    POST /api/notifications/<id>/ack   -> {"ok": true|false}

Every request is authenticated with the scheme in `remote.protocol`. The
Android client in `core/windows/BridgeClient.kt` is the other half, and the
iPhone PWA in `iphone-pwa/` is the third.

Two of these endpoints are served by the desktop rather than by this module:
the chat answer comes from the provider the desktop selected, and the status
numbers come from the machine the desktop runs on. Both are injected, so the
bridge stays free of provider keys and of platform code.
"""
from dataclasses import dataclass, field
import json
import platform
import socket
import time

from remote.audit import AuditLog
from remote.jobs import JobError, JobStore
from remote.memory import MemoryError_, MemoryStore
from remote.notifications import NotificationError, NotificationStore
from remote.pairing import PairingStore
from remote.protocol import (
    KEY_ID_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    ProtocolError,
    check_timestamp,
    normalize_headers,
    verify,
)
from remote.replay import ReplayGuard

#: Only loopback is reachable unless the owner widens this for a private tunnel.
DEFAULT_ALLOWED_HOSTS = ('127.0.0.1', '::1')

#: The generic message used for every authentication failure so that a caller
#: cannot learn whether a key id exists.
AUTH_MESSAGE = 'The Windows bridge rejected the pairing signature'

#: The most characters one chat message may hold.
MAX_CHAT_MESSAGE = 8000

#: The most characters one memory entry may hold.
MAX_MEMORY_TEXT = 2000


class BridgeHandlerError(RuntimeError):
    """A request could not be served, with the status to return."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class BridgeRequest:
    """One signed bridge request."""

    method: str
    path: str
    headers: dict = field(default_factory=dict)
    body: str = ''
    remote_addr: str = '127.0.0.1'


@dataclass(frozen=True)
class BridgeResponse:
    """The answer to a bridge request."""

    status: int
    payload: dict

    def to_json(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


class BridgeServer:
    """Authenticates and serves bridge requests.

    `pairing` holds the paired devices and their secrets, `jobs` holds the
    job records. Both can be replaced for tests or for a future persistent
    store.
    """

    def __init__(self, pairing: PairingStore, jobs: JobStore | None = None,
                 replay: ReplayGuard | None = None, *, peer_id: str = 'windows',
                 agent_version: str = '', allowed_hosts=DEFAULT_ALLOWED_HOSTS,
                 clock_skew_seconds: int = 300, now=time.time,
                 memory: MemoryStore | None = None,
                 notifications: NotificationStore | None = None,
                 audit: AuditLog | None = None,
                 chat=None, status_provider=None, memory_allowed=None):
        self._pairing = pairing
        self._jobs = jobs if jobs is not None else JobStore(now=now)
        self._replay = replay if replay is not None else ReplayGuard()
        self._memory = memory if memory is not None else MemoryStore(now=now)
        self._notifications = notifications if notifications is not None else NotificationStore(now=now)
        self._audit = audit if audit is not None else AuditLog(now=now)
        self._chat = chat
        self._status_provider = status_provider
        self._memory_allowed = memory_allowed
        self._peer_id = peer_id
        self._agent_version = agent_version
        self._allowed_hosts = tuple(allowed_hosts)
        self._clock_skew_seconds = clock_skew_seconds
        self._now = now

    # ------------------------------------------------------------------ public

    @property
    def jobs(self) -> JobStore:
        return self._jobs

    @property
    def pairing(self) -> PairingStore:
        return self._pairing

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def notifications(self) -> NotificationStore:
        return self._notifications

    @property
    def audit(self) -> AuditLog:
        return self._audit

    def set_chat(self, handler) -> None:
        """Let the desktop answer chat requests. The handler takes the message
        and the consent flag and returns the answer."""
        self._chat = handler

    def set_memory_allowed(self, checker) -> None:
        """Decide whether a paired device may synchronise memory."""
        self._memory_allowed = checker

    def handle(self, request: BridgeRequest) -> BridgeResponse:
        """Authenticate and serve one request."""
        key_id = normalize_headers(request.headers).get(KEY_ID_HEADER.lower(), '')
        try:
            self._check_source(request)
            device = self._authenticate(request)
            payload = self._dispatch(request, device)
        except BridgeHandlerError as error:
            self._audit.record(key_id, request.method, request.path, error.status,
                               request.body, note=error.message)
            return BridgeResponse(status=error.status, payload={'error': error.message})
        self._audit.record(key_id, request.method, request.path, 200, request.body)
        return BridgeResponse(status=200, payload=payload)

    # ----------------------------------------------------------------- routing

    def _dispatch(self, request: BridgeRequest, device) -> dict:
        method = request.method.upper()
        path = request.path
        if method == 'GET' and path == '/api/status':
            return self._status()
        if method == 'GET' and path == '/api/jobs':
            return {'jobs': [job.to_json() for job in self._jobs.list()]}
        if method == 'GET' and path.startswith('/api/jobs/') and not path.endswith('/cancel'):
            job_id = path[len('/api/jobs/'):]
            if not job_id or '/' in job_id:
                raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')
            job = self._jobs.get(job_id)
            if job is None:
                raise BridgeHandlerError(404, 'Unknown job.')
            return job.to_json()
        if method == 'POST' and path == '/api/jobs':
            return self._submit(request)
        if method == 'POST' and path.startswith('/api/jobs/') and path.endswith('/cancel'):
            job_id = path[len('/api/jobs/'):-len('/cancel')]
            if not job_id or '/' in job_id:
                raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')
            return {'ok': self._jobs.cancel(job_id)}
        if method == 'POST' and path == '/api/chat':
            return self._chat_answer(request)
        if method == 'GET' and path == '/api/memory':
            return {'memory': [entry.to_json() for entry in self._memory.entries()]}
        if method == 'POST' and path == '/api/memory':
            return self._remember(request)
        if method == 'GET' and path == '/api/notifications':
            return {'notifications': [item.to_json() for item in self._notifications.pending()]}
        if method == 'POST' and path.startswith('/api/notifications/') and path.endswith('/ack'):
            notification_id = path[len('/api/notifications/'):-len('/ack')]
            if not notification_id or '/' in notification_id:
                raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')
            return {'ok': self._notifications.acknowledge(notification_id)}
        raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')

    def _status(self) -> dict:
        queued, running = self._jobs.counts()
        status = {
            'peer_id': self._peer_id,
            'state': 'online',
            'hostname': socket.gethostname(),
            'platform': platform.system(),
            'agent_version': self._agent_version,
            'heartbeat': int(self._now() * 1000),
            'queued_jobs': queued,
            'running_jobs': running,
            'cpu_percent': None,
            'memory_percent': None,
            'gpu_percent': None,
            'disk_free_gb': None,
            'detail': 'JARVIS AI bridge',
        }
        if self._status_provider is not None:
            try:
                extra = self._status_provider() or {}
            except Exception:
                extra = {}
            for name in ('cpu_percent', 'memory_percent', 'gpu_percent', 'disk_free_gb',
                         'disk_total_gb', 'uptime_seconds', 'detail'):
                if name in extra and extra[name] is not None:
                    status[name] = extra[name]
        return status

    def _chat_answer(self, request: BridgeRequest) -> dict:
        """Let the desktop answer one message on behalf of a paired device."""
        if self._chat is None:
            raise BridgeHandlerError(503, 'The Windows desktop has not enabled chat for paired devices.')
        try:
            body = json.loads(request.body or '{}')
        except (ValueError, TypeError):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.') from None
        if not isinstance(body, dict):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.')
        message = body.get('message')
        consent = body.get('consent', False)
        if not isinstance(message, str) or not message.strip():
            raise BridgeHandlerError(400, 'A chat message is required.')
        if len(message) > MAX_CHAT_MESSAGE:
            raise BridgeHandlerError(400, 'That chat message is too long.')
        if type(consent) is not bool:
            raise BridgeHandlerError(400, 'The Windows bridge received an invalid consent flag.')
        try:
            answer = self._chat(message.strip(), consent)
        except BridgeHandlerError as error:
            raise error
        except Exception:
            raise BridgeHandlerError(502, 'The Windows desktop could not answer that message.') from None
        if not isinstance(answer, dict) or not isinstance(answer.get('text'), str):
            raise BridgeHandlerError(502, 'The Windows desktop returned an unusable answer.')
        return answer

    def _remember(self, request: BridgeRequest) -> dict:
        """Store one memory entry that a paired device sent."""
        try:
            body = json.loads(request.body or '{}')
        except (ValueError, TypeError):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.') from None
        if not isinstance(body, dict):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.')
        text = body.get('text')
        source = body.get('source', 'phone')
        if not isinstance(text, str) or len(text) > MAX_MEMORY_TEXT:
            raise BridgeHandlerError(400, 'That memory entry is not usable.')
        if self._memory_allowed is not None:
            try:
                allowed = bool(self._memory_allowed())
            except Exception:
                allowed = False
            if not allowed:
                raise BridgeHandlerError(403, 'The Windows desktop has not allowed memory synchronisation.')
        try:
            entry = self._memory.append(text, source)
        except MemoryError_ as error:
            raise BridgeHandlerError(400, str(error)) from None
        return entry.to_json()

    def _submit(self, request: BridgeRequest) -> dict:
        try:
            body = json.loads(request.body or '{}')
        except (ValueError, TypeError):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.') from None
        if not isinstance(body, dict):
            raise BridgeHandlerError(400, 'The Windows bridge received invalid JSON.')
        kind = body.get('kind')
        title = body.get('title')
        payload = body.get('payload', '')
        # The Android client sends "requireApproval"; accept the snake_case
        # spelling as well so either side can be used directly.
        approval = body.get('requireApproval', body.get('require_approval', True))
        if type(approval) is not bool:
            raise BridgeHandlerError(400, 'The Windows bridge received an invalid approval flag.')
        try:
            job = self._jobs.submit(kind, title, payload, approval)
        except JobError as error:
            raise BridgeHandlerError(400, str(error)) from None
        return job.to_json()

    # ------------------------------------------------------------- authenticity

    def _check_source(self, request: BridgeRequest) -> None:
        """Reject a request that did not arrive over an allowed interface."""
        if request.remote_addr not in self._allowed_hosts:
            raise BridgeHandlerError(403, AUTH_MESSAGE)

    def _authenticate(self, request: BridgeRequest):
        headers = normalize_headers(request.headers)
        key_id = headers.get(KEY_ID_HEADER.lower(), '')
        timestamp = headers.get(TIMESTAMP_HEADER.lower(), '')
        nonce = headers.get(NONCE_HEADER.lower(), '')
        signature = headers.get(SIGNATURE_HEADER.lower(), '')
        if not key_id or not timestamp or not nonce or not signature:
            raise BridgeHandlerError(403, AUTH_MESSAGE)
        device = self._pairing.device(key_id)
        if device is None:
            raise BridgeHandlerError(403, AUTH_MESSAGE)
        secret = self._pairing.secret_for(key_id)
        if not secret:
            raise BridgeHandlerError(403, AUTH_MESSAGE)
        try:
            check_timestamp(timestamp, now=self._now(),
                            max_skew_seconds=self._clock_skew_seconds)
            self._replay.check(nonce)
            verify(request.method, request.path, timestamp, request.body, secret, nonce, signature)
        except ProtocolError:
            raise BridgeHandlerError(403, AUTH_MESSAGE) from None
        self._pairing.touch(key_id)
        return device
