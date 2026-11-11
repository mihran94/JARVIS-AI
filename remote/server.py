"""Bridge request handling, independent of any HTTP server.

This module deliberately does not bind a socket. Choosing the listening
interface is an operator decision, and the default is the loopback interface
only. A private tunnel such as Tailscale or WireGuard is the expected way to
reach a paired phone, and no control port is published to the public internet.

`handle()` is the whole protocol surface:

    GET  /api/status              -> PC status
    GET  /api/jobs                -> {"jobs": [...]}
    POST /api/jobs                -> one job record
    POST /api/jobs/<id>/cancel    -> {"ok": true|false}

Every request is authenticated with the scheme in `remote.protocol`. The
Android client in `core/windows/BridgeClient.kt` is the other half.
"""
from dataclasses import dataclass, field
import json
import platform
import socket
import time

from remote.jobs import JobError, JobStore
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
                 clock_skew_seconds: int = 300, now=time.time):
        self._pairing = pairing
        self._jobs = jobs if jobs is not None else JobStore(now=now)
        self._replay = replay if replay is not None else ReplayGuard()
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

    def handle(self, request: BridgeRequest) -> BridgeResponse:
        """Authenticate and serve one request."""
        try:
            self._check_source(request)
            device = self._authenticate(request)
            payload = self._dispatch(request, device)
        except BridgeHandlerError as error:
            return BridgeResponse(status=error.status, payload={'error': error.message})
        return BridgeResponse(status=200, payload=payload)

    # ----------------------------------------------------------------- routing

    def _dispatch(self, request: BridgeRequest, device) -> dict:
        method = request.method.upper()
        path = request.path
        if method == 'GET' and path == '/api/status':
            return self._status()
        if method == 'GET' and path == '/api/jobs':
            return {'jobs': [job.to_json() for job in self._jobs.list()]}
        if method == 'POST' and path == '/api/jobs':
            return self._submit(request)
        if method == 'POST' and path.startswith('/api/jobs/') and path.endswith('/cancel'):
            job_id = path[len('/api/jobs/'):-len('/cancel')]
            if not job_id or '/' in job_id:
                raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')
            return {'ok': self._jobs.cancel(job_id)}
        raise BridgeHandlerError(404, 'The Windows bridge does not expose that endpoint')

    def _status(self) -> dict:
        queued, running = self._jobs.counts()
        return {
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
