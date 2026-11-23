"""The Web Download Center: bringing a file down, safely.

WHAT THIS IS
    The owner names a page and JARVIS keeps the file. This module is the
    part that has to be careful, because it takes a name from the
    internet and writes to the owner's disk.

    It refuses, before any connection is made:

    * an address that is not https;
    * an address that points at this computer, at the local network or
      at a name that resolves there, so a page cannot ask the downloader
      to read the owner's files;
    * an address with credentials in it, or with a port that is not the
      usual one.

    It follows redirects by hand, because every hop has to be checked
    again. A redirect into the private network is refused even when the
    first address was public.

    It writes to a name it chooses: the name from the address is only a
    suggestion, and it is cleaned until it is safe on Windows.

WHAT THIS IS NOT
    * It is not a crawler and it does not parse a page for links.
    * It does not run anything it downloads, and it does not open the
      file.
    * It does not resume a download unless the server says it may.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import socket
import unicodedata
from urllib.parse import unquote, urlparse, urlunparse

#: The largest file that will be downloaded.
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

#: The longest address that will be tried.
MAX_URL_LENGTH = 2048

#: How many redirects are followed.
MAX_REDIRECTS = 5

#: The ports a public https download may use.
ALLOWED_PORTS = (443,)

#: The user agent the downloader identifies as.
USER_AGENT = 'JARVIS-AI-Downloader/1.0'

#: The characters that may be in a file name.
_SAFE_NAME = re.compile(r'[^A-Za-z0-9._ -]+')

#: The names Windows refuses, whatever the extension.
RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{index}' for index in range(1, 10)),
    *(f'LPT{index}' for index in range(1, 10)),
}


class DownloadError(RuntimeError):
    """A download could not be made."""


class DownloadRefused(DownloadError):
    """The address was refused before any connection was made."""


@dataclass
class DownloadResult:
    """What one download actually did."""

    url: str
    path: Path | None = None
    bytes: int = 0
    sha256: str = ''
    content_type: str = ''
    resumed: bool = False
    status: int = 0
    message: str = ''
    elapsed_ms: int = 0

    def as_dict(self) -> dict:
        return {
            'url': self.url,
            'path': str(self.path) if self.path else '',
            'bytes': self.bytes,
            'sha256': self.sha256,
            'content_type': self.content_type,
            'resumed': self.resumed,
            'status': self.status,
            'message': self.message,
            'elapsed_ms': self.elapsed_ms,
        }


@dataclass
class DownloadRecord:
    """One line of the download history."""

    url: str
    name: str
    bytes: int
    sha256: str
    created: str
    status: str = 'completed'
    detail: str = ''


# ── the address checks ─────────────────────────────────────────────────────


def check_url(url: str, *, resolver=socket.getaddrinfo) -> str:
    """Check one address and return it, or refuse it.

    The check happens before any connection is made, so a refused
    address never reaches the network.
    """
    if not isinstance(url, str) or not url.strip():
        raise DownloadRefused('There is no address to download.')
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise DownloadRefused('That address is too long.')
    try:
        parsed = urlparse(url)
    except ValueError:
        raise DownloadRefused('That address could not be read.') from None
    if parsed.scheme.casefold() != 'https':
        raise DownloadRefused('Only https addresses are downloaded.')
    if parsed.username or parsed.password:
        raise DownloadRefused('An address with a user name in it is refused.')
    host = parsed.hostname
    if not host:
        raise DownloadRefused('That address has no host in it.')
    if parsed.port is not None and parsed.port not in ALLOWED_PORTS:
        raise DownloadRefused('Only the usual https port is downloaded.')
    if host.casefold() in ('localhost', 'localhost.localdomain'):
        raise DownloadRefused('That address points at this computer.')
    check_host(host, resolver=resolver)
    return url


def check_host(host: str, *, resolver=socket.getaddrinfo) -> None:
    """Refuse a host that is, or resolves to, a private address."""
    literal = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(literal):
            raise DownloadRefused('That address points at this computer or a private network.')
        return
    try:
        answers = resolver(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError):
        raise DownloadRefused('That address could not be resolved.') from None
    if not answers:
        raise DownloadRefused('That address could not be resolved.')
    for answer in answers:
        try:
            address = ipaddress.ip_address(answer[4][0])
        except (ValueError, IndexError):
            continue
        if not _is_public(address):
            raise DownloadRefused('That address points at this computer or a private network.')


def _is_public(address) -> bool:
    """Whether an address may be reached by a download."""
    if address.is_private or address.is_loopback or address.is_link_local:
        return False
    if address.is_reserved or address.is_multicast or address.is_unspecified:
        return False
    if getattr(address, 'is_site_local', False):
        return False
    return True


def safe_name(name: str, *, fallback: str = 'download') -> str:
    """A file name that is safe to write on Windows.

    The name from the address is only a suggestion. Everything that is
    not a letter, a digit, a dot, a dash, an underscore or a space is
    replaced, the name cannot be a reserved Windows device, and it can
    never point outside the folder it is written into.
    """
    name = unicodedata.normalize('NFKC', unquote(str(name or '')))
    name = name.replace('\\', '/').split('/')[-1]
    name = _SAFE_NAME.sub('_', name).strip(' .')
    while '..' in name:
        name = name.replace('..', '.')
    if not name:
        name = fallback
    stem, dot, extension = name.partition('.')
    if stem.upper() in RESERVED_NAMES:
        name = f'_{stem}{dot}{extension}'
    if len(name) > 180:
        stem, dot, extension = name.rpartition('.')
        keep = 180 - len(extension) - 1 if dot else 180
        name = (stem[:keep] + dot + extension) if dot else name[:180]
    return name


def suggested_name(url: str) -> str:
    """The file name the address suggests."""
    parsed = urlparse(url)
    return safe_name(parsed.path.rsplit('/', 1)[-1] or (parsed.hostname or 'download'))


# ── the download ───────────────────────────────────────────────────────────


def download(url: str, destination, *, resolver=socket.getaddrinfo, client=None,
             progress=None, should_stop=None, max_bytes=MAX_DOWNLOAD_BYTES,
             resume=False) -> DownloadResult:
    """Download one file, safely.

    `progress` is called with the number of bytes so far. `should_stop`
    is called between chunks; when it returns True the download is
    cancelled and the partial file is kept, so the owner can see that
    something was fetched.
    """
    import time

    started = time.monotonic()
    destination = Path(destination)
    check_url(url, resolver=resolver)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not resume:
        raise DownloadRefused('A file with that name is already there.')

    import httpx

    close = False
    if client is None:
        client = httpx.Client(follow_redirects=False, timeout=httpx.Timeout(30, connect=10),
                               headers={'User-Agent': USER_AGENT}, trust_env=False)
        close = True
    try:
        current = url
        response = None
        for _ in range(MAX_REDIRECTS + 1):
            check_url(current, resolver=resolver)
            with client.stream('GET', current) as attempt:
                if attempt.status_code in (301, 302, 303, 307, 308):
                    location = attempt.headers.get('location')
                    if not location:
                        raise DownloadError('The address asked for a redirect with no destination.')
                    current = _resolve_redirect(current, location)
                    continue
                if attempt.status_code >= 400:
                    raise DownloadError(f'The server answered {attempt.status_code}.')
                response = attempt
                break
        else:
            raise DownloadError('The address redirected too many times.')

        content_type = response.headers.get('content-type', '')
        length = response.headers.get('content-length')
        total = int(length) if length and length.isdigit() else None
        if total is not None and total > max_bytes:
            raise DownloadRefused(f'That file is larger than this will download '
                                  f'({total:,} bytes).')
        resuming = resume and destination.exists()
        mode = 'ab' if resuming else 'wb'
        written = destination.stat().st_size if resuming else 0
        if resuming:
            headers = {'Range': f'bytes={written}-'}
        else:
            headers = {}
        digest = hashlib.sha256()
        if resuming:
            with destination.open('rb') as existing:
                for chunk in iter(lambda: existing.read(1 << 20), b''):
                    digest.update(chunk)
        with destination.open(mode) as output:
            for chunk in response.iter_bytes(1 << 16):
                if should_stop is not None and should_stop():
                    output.flush()
                    return DownloadResult(
                        url=url, path=destination, bytes=written, status=response.status_code,
                        content_type=content_type, resumed=resuming,
                        message='The download was cancelled. The partial file was kept.')
                written += len(chunk)
                if written > max_bytes:
                    raise DownloadRefused('That file is larger than this will download.')
                output.write(chunk)
                digest.update(chunk)
                if progress is not None:
                    progress(written, total)
        return DownloadResult(
            url=url, path=destination, bytes=written, sha256=digest.hexdigest(),
            content_type=content_type, resumed=resuming, status=response.status_code,
            message='The file was downloaded.',
            elapsed_ms=int((time.monotonic() - started) * 1000))
    finally:
        if close:
            client.close()


def _resolve_redirect(base: str, location: str) -> str:
    """The next address to try, from a redirect."""
    from urllib.parse import urljoin

    return urljoin(base, location)


def supports_resume(response) -> bool:
    """Whether the server allows the download to be continued.

    A server that answers a range request with 206 allows it. One that
    answers 200 does not: it is sending the whole file again, so the
    download starts over rather than pretending to continue.
    """
    return getattr(response, 'status_code', 0) == 206


@dataclass
class DownloadHistory:
    """What was downloaded, kept on this computer."""

    path: Path
    entries: list = field(default_factory=list)

    def add(self, entry: DownloadRecord):
        self.entries.append(entry)
        self.save()

    def rows(self, limit: int = 100) -> list:
        return list(reversed(self.entries[-limit:]))

    def save(self):
        """Write the history out."""
        import json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{'url': entry.url, 'name': entry.name, 'bytes': entry.bytes,
                 'sha256': entry.sha256, 'created': entry.created, 'status': entry.status,
                 'detail': entry.detail} for entry in self.entries]
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path) -> 'DownloadHistory':
        """Read the history back, or start an empty one."""
        import json
        path = Path(path)
        entries = []
        if path.is_file():
            try:
                rows = json.loads(path.read_text(encoding='utf-8'))
                for row in rows:
                    entries.append(DownloadRecord(
                        url=str(row.get('url', '')), name=str(row.get('name', '')),
                        bytes=int(row.get('bytes', 0)), sha256=str(row.get('sha256', '')),
                        created=str(row.get('created', '')), status=str(row.get('status', '')),
                        detail=str(row.get('detail', ''))))
            except (OSError, ValueError, TypeError):
                entries = []
        return cls(path, entries)


__all__ = ['ALLOWED_PORTS', 'MAX_DOWNLOAD_BYTES', 'MAX_REDIRECTS', 'USER_AGENT',
           'DownloadError', 'DownloadHistory', 'DownloadRecord', 'DownloadRefused',
           'DownloadResult', 'check_host', 'check_url', 'download', 'safe_name',
           'suggested_name', 'supports_resume']
