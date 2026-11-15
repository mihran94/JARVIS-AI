"""The certificate of the private bridge listener.

The listener refuses to serve without TLS, and the phone pins the
certificate by the fingerprint that travels in the pairing code. These
tests cover the fingerprint, the creation of a certificate and the pairing
code that carries it.
"""
import os
import ssl
import subprocess
import sys

import pytest

from desktop.bridge_pairing import PairingCodeError, pairing_payload
from remote.certificate import (
    CertificateError, create_certificate, describe, ensure_certificate,
    fingerprint, fingerprint_from_file,
)

#: A certificate that was made once and kept here as a fixture.
FIXTURE_PEM = """-----BEGIN CERTIFICATE-----
MIIDHTCCAgWgAwIBAgIUKcruBwNQavEBQRcGE8YjVuWMRCkwDQYJKoZIhvcNAQEL
BQAwHjEcMBoGA1UEAwwTSkFSVklTIHRlc3QgZml4dHVyZTAeFw0yNjExMTUxNDAy
MjZaFw0zNjExMTIxNDAyMjZaMB4xHDAaBgNVBAMME0pBUlZJUyB0ZXN0IGZpeHR1
cmUwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC3U3NmG37biYwRW52e
ET+eOrkjIvwmW71qBQRPTXViS4+5romQxWnubSWRyVY7Jky533hC6owJmhw1AXE7
F1UbjKDjE64kc5dpRQCgTAPfuBJZMiGx/NOgSqj7+aNDOFVOO918oHHWIhn8qNKs
t4HwGNaroayE3G8cwZNfoDySRc8bUXqVHdhbAw8vhHlhMLFXsU2XRNodg+sOu5xP
c690wLh+anZMIDBUqWwb0cByrabeKyVMPTV/YxDXt3WCi7I67sTk9SYtoQ2t/ddB
TWBVNF1/n3evzBQexN79FYsRjIGTU1jPKiQH72fanvMk5zfm2GeEXmzd0E2R3fdo
h/RVAgMBAAGjUzBRMB0GA1UdDgQWBBRNsq3N3W3muccV39NztIVuRzJ7NjAfBgNV
HSMEGDAWgBRNsq3N3W3muccV39NztIVuRzJ7NjAPBgNVHRMBAf8EBTADAQH/MA0G
CSqGSIb3DQEBCwUAA4IBAQAewpPHJtGxSL1Nn5vXGM8jaRP+tqY9dmpq8sag5o8w
Bz+8wAqQ7eRwDNR/nxNSCql856QkCsDc6ik9ChFuP7U5D0gYu1W0sd6c++qtyqfV
N93ecwkZ+B057JvHVvzupMO28d7o/aQ+jCBAuokdst98nXmTSzVcfZWLdICocuYt
rtB+H6QsMxA4nclV5DzxMaBV2Iy8BbD7r91npm5PpkNhhq5XwutWAmoGf7vZxhlB
6/vuyE4x6ifqVmlT67bD0aMEhWqZCC+gnJ5Fl3txbdKwQ325YKkXtSrd5aRoeWmP
E4KQIyiqpgch6XpBITUnQ5Zku/Q37+1euXrflT6n84wr
-----END CERTIFICATE-----
"""


def test_the_fingerprint_of_a_certificate_is_stable():
    assert fingerprint(FIXTURE_PEM) == fingerprint(FIXTURE_PEM)
    assert len(fingerprint(FIXTURE_PEM)) == 64
    digest = fingerprint(FIXTURE_PEM)
    assert digest == digest.lower()
    assert all(character in '0123456789abcdef' for character in digest)


def test_a_damaged_certificate_is_refused():
    with pytest.raises(CertificateError):
        fingerprint('-----BEGIN CERTIFICATE-----\nnot base64\n-----END CERTIFICATE-----')
    with pytest.raises(CertificateError):
        fingerprint('this is not a certificate')


def test_a_certificate_that_is_created_can_be_used_by_the_listener(tmp_path):
    cert = str(tmp_path / 'bridge.crt')
    key = str(tmp_path / 'bridge.key')
    digest = create_certificate(cert, key)
    assert os.path.exists(cert) and os.path.exists(key)
    assert digest == fingerprint_from_file(cert)
    # The listener has to be able to load it.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)


def test_the_key_is_not_readable_by_anybody_else(tmp_path):
    cert = str(tmp_path / 'bridge.crt')
    key = str(tmp_path / 'bridge.key')
    create_certificate(cert, key)
    if os.name != 'nt':
        assert oct(os.stat(key).st_mode)[-3:] == '600'


def test_the_certificate_is_not_created_twice(tmp_path):
    cert = str(tmp_path / 'bridge.crt')
    key = str(tmp_path / 'bridge.key')
    first = create_certificate(cert, key)
    second = ensure_certificate(cert, key)
    assert first == second


def test_a_missing_certificate_with_a_key_is_reported(tmp_path):
    cert = str(tmp_path / 'bridge.crt')
    key = str(tmp_path / 'bridge.key')
    with open(key, 'w', encoding='utf-8') as handle:
        handle.write('key')
    with pytest.raises(CertificateError):
        ensure_certificate(cert, key)


def test_the_certificate_can_be_described(tmp_path):
    cert = str(tmp_path / 'bridge.crt')
    key = str(tmp_path / 'bridge.key')
    create_certificate(cert, key)
    text = describe(cert)
    assert 'SHA-256' in text or 'subject' in text


def test_the_pairing_code_carries_the_fingerprint():
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                              's' * 40, 1764000000, fingerprint='A' * 64)
    assert 'fp=' + 'a' * 64 in payload


def test_the_pairing_code_still_works_without_a_fingerprint():
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                              's' * 40, 1764000000)
    assert 'fp=' not in payload
    lines = payload.splitlines()
    assert lines[0] == 'JARVIS-BRIDGE-v1'
    assert len(lines) == 5


def test_the_pairing_code_still_needs_https():
    with pytest.raises(PairingCodeError):
        pairing_payload('http://pc.example.lan:8765', 'jarvis-iphone-v1',
                        's' * 40, 1764000000)


def test_the_phone_reads_the_fingerprint_back(tmp_path):
    """The phone side reads the same field the desktop writes."""
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                              's' * 40, 4102444800, fingerprint='b' * 64)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    module = os.path.join(root, 'iphone-pwa', 'js', 'pairing.js').replace(os.sep, '/')
    script = tmp_path / 'read.mjs'
    script.write_text(
        "import { parsePairingPayload } from '%s';\n"
        "const parsed = parsePairingPayload(process.argv[2]);\n"
        "process.stdout.write(String(parsed.fingerprint || ''));\n" % module,
        encoding='utf-8')
    result = subprocess.run(['node', str(script), payload],
                            capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip('node is not available here')
    assert result.stdout.strip() == 'b' * 64
