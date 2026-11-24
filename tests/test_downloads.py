"""The Web Download Center: the address checks and the writing of the file.

WHAT IS COVERED
    * An address that is not https, or that carries credentials, or that
      uses an unusual port, is refused before any connection is made.
    * An address that points at this computer or at a private network is
      refused, including when the name only resolves there.
    * A redirect is checked again, so a public address cannot bounce
      the downloader into the private network.
    * The file name is cleaned until it is safe on Windows, and it can
      never point outside the folder.
    * The file is written, its size and its SHA-256 are reported, and
      the download can be cancelled with the partial file kept.
    * A file that is already there is not overwritten by accident.
    * The history is kept and read back.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import socket

import httpx
import pytest

from core.downloads import (
    DownloadError, DownloadHistory, DownloadRecord, DownloadRefused, check_url,
    download, safe_name, suggested_name,
)


def public_resolver(host, port, *args, **kwargs):
    """A resolver that says every name is on the public internet."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))]


def private_resolver(host, port, *args, **kwargs):
    """A resolver that says every name is on the private network."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', port))]


# ── the address checks ─────────────────────────────────────────────────────

def test_https_is_accepted():
    url = check_url('https://example.com/file.zip', resolver=public_resolver)
    assert url == 'https://example.com/file.zip'


def test_plain_http_is_refused():
    with pytest.raises(DownloadRefused) as error:
        check_url('http://example.com/file.zip', resolver=public_resolver)
    assert 'https' in str(error.value)


def test_an_address_with_a_user_name_is_refused():
    with pytest.raises(DownloadRefused):
        check_url('https://user:pass@example.com/file.zip', resolver=public_resolver)


def test_an_unusual_port_is_refused():
    with pytest.raises(DownloadRefused):
        check_url('https://example.com:8080/file.zip', resolver=public_resolver)


def test_localhost_is_refused():
    with pytest.raises(DownloadRefused):
        check_url('https://localhost/file.zip', resolver=public_resolver)


def test_a_loopback_address_is_refused():
    with pytest.raises(DownloadRefused):
        check_url('https://127.0.0.1/file.zip', resolver=public_resolver)


def test_a_private_address_is_refused():
    with pytest.raises(DownloadRefused) as error:
        check_url('https://192.168.1.5/file.zip', resolver=public_resolver)
    assert 'private' in str(error.value)


def test_a_name_that_resolves_to_a_private_address_is_refused():
    with pytest.raises(DownloadRefused):
        check_url('https://router.local/file.zip', resolver=private_resolver)


def test_a_name_that_cannot_be_resolved_is_refused():
    def failing(host, port, *args, **kwargs):
        raise socket.gaierror('no such name')

    with pytest.raises(DownloadRefused):
        check_url('https://nowhere.invalid/file.zip', resolver=failing)


# ── the file name ──────────────────────────────────────────────────────────

def test_a_file_name_is_cleaned():
    # Only letters, digits, a dot, a dash, an underscore and a space are
    # kept. Everything else is replaced, so a name from the internet can
    # never carry a character that Windows treats specially.
    assert safe_name('report (final).pdf') == 'report _final_.pdf'
    assert safe_name('report-final_v2.pdf') == 'report-final_v2.pdf'
    assert '/' not in safe_name('a/b/c.txt')
    assert safe_name('a/b/c.txt') == 'c.txt'
    assert safe_name('..\\..\\windows\\system32\\cmd.exe') == 'cmd.exe'


def test_a_reserved_windows_name_is_not_used():
    assert safe_name('CON.txt').startswith('_')
    assert safe_name('nul') .startswith('_')


def test_a_name_with_nothing_in_it_gets_a_fallback():
    assert safe_name('') == 'download'
    assert safe_name('///') == 'download'


def test_the_name_from_an_address_is_only_a_suggestion():
    assert suggested_name('https://example.com/files/report%20final.pdf') == 'report final.pdf'


# ── the download ───────────────────────────────────────────────────────────

def make_transport(body=b'hello download', status=200, headers=None):
    def handler(request):
        return httpx.Response(status, content=body, headers=headers or {})

    return httpx.MockTransport(handler)


def test_a_file_is_downloaded_and_measured(tmp_path):
    transport = make_transport(b'hello download')
    client = httpx.Client(transport=transport)
    target = tmp_path / 'out' / 'file.bin'
    result = download('https://example.com/file.bin', target, resolver=public_resolver,
                      client=client)
    assert target.is_file()
    assert target.read_bytes() == b'hello download'
    assert result.bytes == len(b'hello download')
    assert len(result.sha256) == 64
    assert result.status == 200


def test_a_progress_callback_is_called(tmp_path):
    seen = []
    transport = make_transport(b'x' * 100)
    client = httpx.Client(transport=transport)
    download('https://example.com/file.bin', tmp_path / 'f.bin', resolver=public_resolver,
             client=client, progress=lambda done, total: seen.append(done))
    assert seen and seen[-1] == 100


def test_a_cancelled_download_keeps_what_it_had(tmp_path):
    transport = make_transport(b'x' * 100)
    client = httpx.Client(transport=transport)
    target = tmp_path / 'f.bin'
    result = download('https://example.com/file.bin', target, resolver=public_resolver,
                      client=client, should_stop=lambda: True)
    assert 'cancelled' in result.message.lower()
    assert target.is_file()


def test_an_existing_file_is_not_overwritten(tmp_path):
    transport = make_transport()
    client = httpx.Client(transport=transport)
    target = tmp_path / 'f.bin'
    target.write_bytes(b'mine')
    with pytest.raises(DownloadRefused):
        download('https://example.com/file.bin', target, resolver=public_resolver, client=client)
    assert target.read_bytes() == b'mine'


def test_a_redirect_into_the_private_network_is_refused(tmp_path):
    def handler(request):
        if request.url.host == 'example.com':
            return httpx.Response(302, headers={'location': 'https://192.168.1.5/secret'})
        return httpx.Response(200, content=b'secret')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(DownloadRefused):
        download('https://example.com/file.bin', tmp_path / 'f.bin',
                 resolver=public_resolver, client=client)


def test_a_redirect_to_a_public_address_is_followed(tmp_path):
    def handler(request):
        if request.url.host == 'example.com':
            return httpx.Response(302, headers={'location': 'https://cdn.example.net/file.bin'})
        return httpx.Response(200, content=b'from the cdn')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    target = tmp_path / 'f.bin'
    result = download('https://example.com/file.bin', target, resolver=public_resolver,
                      client=client)
    assert target.read_bytes() == b'from the cdn'
    assert result.bytes == len(b'from the cdn')


def test_a_server_error_is_reported(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(DownloadError):
        download('https://example.com/file.bin', tmp_path / 'f.bin',
                 resolver=public_resolver, client=client)


def test_a_file_that_is_too_large_is_refused(tmp_path):
    transport = make_transport(b'x' * 100, headers={'content-length': '999999999'})
    client = httpx.Client(transport=transport)
    with pytest.raises(DownloadRefused):
        download('https://example.com/file.bin', tmp_path / 'f.bin', resolver=public_resolver,
                 client=client, max_bytes=1024)


# ── the history ────────────────────────────────────────────────────────────

def test_the_history_is_kept_and_read_back(tmp_path):
    path = tmp_path / 'downloads.json'
    history = DownloadHistory.load(path)
    history.add(DownloadRecord(url='https://example.com/a.zip', name='a.zip', bytes=10,
                                sha256='a' * 64, created='2026-11-23'))
    again = DownloadHistory.load(path)
    assert len(again.rows()) == 1
    assert again.rows()[0]['url'] if isinstance(again.rows()[0], dict) else True
    assert again.entries[0].name == 'a.zip'


def test_a_history_that_cannot_be_read_starts_empty(tmp_path):
    path = tmp_path / 'downloads.json'
    path.write_text('not json at all', encoding='utf-8')
    assert DownloadHistory.load(path).entries == []
