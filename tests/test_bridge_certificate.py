"""The bridge certificate: the fingerprint the phone pins, and the key.

WHAT IS COVERED
    * The fingerprint is the SHA-256 of the DER form of the certificate, so
      the same certificate always reads as the same fingerprint.
    * A certificate can be created without a certificate authority, and
      the key is only readable by the owner of the machine.
    * A half-present pair is refused rather than quietly overwritten: the
      owner may have moved one of the two files on purpose, and a key is
      not something to replace without saying so.
    * The fingerprint travels in the pairing code, so the phone knows
      which certificate to trust before it sends the secret.
    * The owner can allow a VPN or tunnel peer, and the loopback
      addresses stay allowed whatever they type.
"""
import os
import stat
import subprocess

import pytest

from desktop.bridge_pairing import PairingCodeError, pairing_payload
from remote import certificate
from remote.server import BridgeServer


def make_certificate(tmp_path):
    """A real self-signed certificate, made with OpenSSL."""
    cert_path = tmp_path / 'bridge-cert.pem'
    key_path = tmp_path / 'bridge-key.pem'
    pin = certificate.create_certificate(str(cert_path), str(key_path))
    return cert_path, key_path, pin


@pytest.mark.skipif(not certificate.shutil.which('openssl'),
                    reason='OpenSSL is not available on this machine')
def test_a_certificate_can_be_created_without_a_certificate_authority(tmp_path):
    cert_path, key_path, pin = make_certificate(tmp_path)
    assert cert_path.exists()
    assert key_path.exists()
    assert len(pin) == 64
    assert all(character in '0123456789abcdef' for character in pin)


@pytest.mark.skipif(not certificate.shutil.which('openssl'),
                    reason='OpenSSL is not available on this machine')
def test_the_key_is_only_readable_by_the_owner(tmp_path):
    _, key_path, _ = make_certificate(tmp_path)
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    assert mode & 0o077 == 0, 'the private key is readable by other users'


@pytest.mark.skipif(not certificate.shutil.which('openssl'),
                    reason='OpenSSL is not available on this machine')
def test_the_same_certificate_always_reads_as_the_same_fingerprint(tmp_path):
    cert_path, _, pin = make_certificate(tmp_path)
    assert certificate.fingerprint_from_file(str(cert_path)) == pin
    assert certificate.fingerprint(cert_path.read_bytes()) == pin


def test_a_file_that_is_not_a_certificate_is_refused(tmp_path):
    broken = tmp_path / 'broken.pem'
    broken.write_text('this is not a certificate', encoding='utf-8')
    with pytest.raises(certificate.CertificateError):
        certificate.fingerprint_from_file(str(broken))


def test_a_damaged_certificate_is_refused(tmp_path):
    damaged = tmp_path / 'damaged.pem'
    damaged.write_text(
        '-----BEGIN CERTIFICATE-----\nnot base64 at all\n-----END CERTIFICATE-----\n',
        encoding='utf-8')
    with pytest.raises(certificate.CertificateError):
        certificate.fingerprint_from_file(str(damaged))


def test_a_certificate_that_is_there_is_not_replaced(tmp_path):
    cert_path, _, pin = make_certificate(tmp_path)
    again = certificate.ensure_certificate(str(cert_path), str(cert_path))
    assert again == pin


@pytest.mark.skipif(not certificate.shutil.which('openssl'),
                    reason='OpenSSL is not available on this machine')
def test_a_key_without_its_certificate_is_not_overwritten(tmp_path):
    key_path = tmp_path / 'bridge-key.pem'
    key_path.write_text('-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n',
                        encoding='utf-8')
    with pytest.raises(certificate.CertificateError) as error:
        certificate.ensure_certificate(str(tmp_path / 'missing.pem'), str(key_path))
    assert 'key is there' in str(error.value)
    # The key the owner had is still there.
    assert key_path.exists()


def test_the_fingerprint_travels_in_the_pairing_code():
    pin = 'a' * 64
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                              'x' * 40, 1764000000, fingerprint=pin)
    assert 'fp=' + pin in payload


def test_a_pairing_code_without_a_certificate_still_pairs():
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                              'x' * 40, 1764000000)
    assert 'fp=' not in payload


def test_a_damaged_fingerprint_is_left_out_rather_than_sent_wrong():
    with pytest.raises(PairingCodeError):
        pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1',
                        'x' * 40, 1764000000, fingerprint='not-a-fingerprint')


def test_the_owner_can_allow_a_vpn_or_tunnel_peer():
    from remote.pairing import PairingStore

    bridge = BridgeServer(PairingStore(), peer_id='test')
    bridge.set_allowed_hosts(['10.8.0.2'])
    allowed = bridge.allowed_hosts()
    assert '10.8.0.2' in allowed
    # The loopback addresses stay allowed whatever the owner types.
    assert '127.0.0.1' in allowed
    assert '::1' in allowed


def test_allowing_a_peer_never_removes_the_loopback():
    from remote.pairing import PairingStore

    bridge = BridgeServer(PairingStore(), peer_id='test')
    bridge.set_allowed_hosts(['10.8.0.2'])
    bridge.set_allowed_hosts([])
    allowed = bridge.allowed_hosts()
    assert '127.0.0.1' in allowed
    assert '10.8.0.2' not in allowed
