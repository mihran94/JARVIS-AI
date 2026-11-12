"""The bridge listener.

The listener is deliberately hard to misconfigure:

- it binds the loopback interface by default;
- it refuses to start without TLS unless the owner explicitly allows
  plaintext, which is only sensible on a private tunnel;
- it refuses a non loopback address unless the owner explicitly allows it,
  and then TLS is still required;
- every request is authenticated by the bridge protocol itself, so an
  unauthenticated caller learns nothing.

The listener grants no permission. A job that arrives from a phone is recorded
as QUEUED and still needs the owner's approval in the desktop interface.

Request bodies and headers are never logged. The audit trail records the
method, the path, the status and the peer address only.
"""
from dataclasses import dataclass, field
import http.server
import logging
import socket
import ssl
import threading

from remote.loopback import is_loopback_host
from remote.protocol import normalize_headers
from remote.server import BridgeRequest, BridgeResponse

LOGGER = logging.getLogger('jarvis.bridge')


class ListenerError(RuntimeError):
    """The listener was refused to start."""


@dataclass(frozen=True)
class ListenerConfig:
    """How the listener binds and what it accepts."""

    host: str = '127.0.0.1'
    port: int = 8765
    #: PEM certificate and key for the private listener.
    tls_cert: str = ''
    tls_key: str = ''
    #: Set by the owner when the listener sits behind a private tunnel and
    #: TLS is provided by that tunnel instead.
    allow_plaintext: bool = False
    #: Set by the owner to bind an address other than loopback.
    allow_public_bind: bool = False
    #: Peer addresses that may talk to the listener.
    allowed_hosts: tuple = ('127.0.0.1', '::1')
    #: Seconds a single request may take.
    request_timeout_seconds: float = 30.0

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_cert and self.tls_key)

    def validate(self) -> None:
        """Refuse an unsafe configuration before anything is bound."""
        if not self.tls_enabled and not self.allow_plaintext:
            raise ListenerError(
                'TLS is required. Provide a certificate and key, or confirm that the '
                'listener sits behind a private tunnel that terminates TLS.')
        if not is_loopback_host(self.host) and not self.allow_public_bind:
            raise ListenerError(
                'Refusing to bind a non loopback address. Put the listener behind a '
                'private tunnel, or confirm the address explicitly.')
        if not self.allow_public_bind and not is_loopback_host(self.host):
            raise ListenerError('Refusing to bind a non loopback address.')
        if self.port < 0 or self.port > 65535:
            raise ListenerError('Invalid port.')


class _Handler(http.server.BaseHTTPRequestHandler):
    """Maps HTTP requests onto the bridge handler."""

    server_version = 'JARVIS-AI-bridge'
    protocol_version = 'HTTP/1.1'

    def do_GET(self):  # noqa: N802 - the base class names these
        self._respond()

    def do_POST(self):  # noqa: N802
        self._respond()

    def _respond(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode('utf-8', 'replace') if length > 0 else ''
        headers = normalize_headers({key: value for key, value in self.headers.items()})
        request = BridgeRequest(method=self.command, path=self.path, headers=headers,
                                body=body, remote_addr=self.client_address[0])
        response = self.server.bridge.handle(request)
        payload = response.to_json().encode('utf-8')
        self.send_response(response.status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)
        LOGGER.info('bridge %s %s -> %s from %s', request.method, request.path,
                    response.status, request.remote_addr)

    def log_message(self, fmt, *args):  # noqa: A003 - base class name
        LOGGER.debug('bridge http %s', fmt % args)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, bridge, config: ListenerConfig):
        self.bridge = bridge
        self.config = config
        super().__init__(address, handler)


class BridgeListener:
    """Serves the bridge over HTTP(S) on a private address."""

    def __init__(self, bridge, config: ListenerConfig | None = None, *, logger=None):
        self._bridge = bridge
        self._config = config or ListenerConfig()
        self._server = None
        self._thread = None
        self._logger = logger or LOGGER

    @property
    def config(self) -> ListenerConfig:
        return self._config

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def address(self) -> str:
        """The address a paired phone should use."""
        if self._server is None:
            return ''
        host, port = self._server.server_address[:2]
        return f'https://{host}:{port}' if self._config.tls_enabled else f'http://{host}:{port}'

    def start(self) -> str:
        """Start listening. Returns the address. Raises `ListenerError`."""
        if self._server is not None:
            raise ListenerError('The listener is already running.')
        self._config.validate()
        try:
            server = _Server((self._config.host, self._config.port), _Handler, self._bridge,
                             self._config)
        except OSError as error:
            raise ListenerError(f'Could not bind the bridge listener: {error}') from None
        if self._config.tls_enabled:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            try:
                context.load_cert_chain(self._config.tls_cert, self._config.tls_key)
            except (OSError, ssl.SSLError) as error:
                server.server_close()
                raise ListenerError(f'Could not load the TLS certificate: {error}') from None
            server.socket = context.wrap_socket(server.socket, server_side=True)
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True,
                                        name='jarvis-bridge-listener')
        self._thread.start()
        self._logger.info('bridge listener started on %s', self.address)
        return self.address

    def stop(self) -> None:
        """Stop listening. Safe to call when not running."""
        server, self._server = self._server, None
        thread, self._thread = self._thread, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        self._logger.info('bridge listener stopped')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exception):
        self.stop()
        return False
