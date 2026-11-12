"""Tests for the bridge listener.

The listener is exercised over real HTTP on the loopback interface, so the
request path, the authentication and the refusal rules are all covered.
"""
import json
import time

import httpx
import pytest

from remote.listener import BridgeListener, ListenerConfig, ListenerError
from remote.pairing import PairingStore
from remote.protocol import KEY_ID, sign
from remote.server import BridgeServer

SECRET = 'listener-secret-0123456789abcdefghij'
LOOPBACK = 'http://127.0.0.1'


def make_bridge():
    pairing = PairingStore()
    pairing.pair(key_id=KEY_ID, label='phone', secret=SECRET)
    return BridgeServer(pairing, peer_id='windows-test', agent_version='0.3.0',
                        allowed_hosts=('127.0.0.1', '::1'))


def signed_headers(method, path, body='', nonce='nonce-1'):
    timestamp = str(int(time.time() * 1000))
    return {
        'X-Jarvis-Key-Id': KEY_ID,
        'X-Jarvis-Timestamp': timestamp,
        'X-Jarvis-Nonce': nonce,
        'X-Jarvis-Signature': sign(method, path, timestamp, body, SECRET, nonce),
    }


def test_the_listener_refuses_to_start_without_tls():
    listener = BridgeListener(make_bridge(), ListenerConfig())
    with pytest.raises(ListenerError):
        listener.start()


def test_the_listener_refuses_a_non_loopback_address():
    config = ListenerConfig(host='0.0.0.0', tls_cert='cert.pem', tls_key='key.pem')
    listener = BridgeListener(make_bridge(), config)
    with pytest.raises(ListenerError):
        listener.start()


def test_a_non_loopback_address_needs_an_explicit_opt_in():
    config = ListenerConfig(host='0.0.0.0', tls_cert='cert.pem', tls_key='key.pem',
                            allow_public_bind=True)
    config.validate()


def test_plaintext_needs_an_explicit_opt_in():
    config = ListenerConfig(allow_plaintext=True)
    config.validate()
    assert config.tls_enabled is False


def test_a_signed_request_is_served():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        assert address.startswith(LOOPBACK)
        response = httpx.get(address + '/api/status', headers=signed_headers('GET', '/api/status'))
        assert response.status_code == 200
        assert response.json()['peer_id'] == 'windows-test'
    finally:
        listener.stop()
    assert not listener.running


def test_an_unsigned_request_is_rejected():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        response = httpx.get(address + '/api/status')
        assert response.status_code == 403
        assert 'rejected' in response.json()['error'].lower()
    finally:
        listener.stop()


def test_a_tampered_body_is_rejected():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        headers = signed_headers('POST', '/api/jobs', json.dumps({'kind': 'CUSTOM'}))
        response = httpx.post(address + '/api/jobs', headers=headers,
                              content=json.dumps({'kind': 'WORKFLOW'}))
        assert response.status_code == 403
    finally:
        listener.stop()


def test_a_revoked_device_is_rejected():
    bridge = make_bridge()
    listener = BridgeListener(bridge, ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        assert httpx.get(address + '/api/status',
                         headers=signed_headers('GET', '/api/status')).status_code == 200
        bridge.pairing.revoke(KEY_ID)
        response = httpx.get(address + '/api/status', headers=signed_headers('GET', '/api/status'))
        assert response.status_code == 403
    finally:
        listener.stop()


def test_a_replayed_request_is_rejected():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        headers = signed_headers('GET', '/api/status', nonce='same')
        assert httpx.get(address + '/api/status', headers=headers).status_code == 200
        assert httpx.get(address + '/api/status', headers=headers).status_code == 403
    finally:
        listener.stop()


def test_a_job_submitted_over_the_listener_stays_queued():
    bridge = make_bridge()
    listener = BridgeListener(bridge, ListenerConfig(port=0, allow_plaintext=True))
    address = listener.start()
    try:
        body = json.dumps({'kind': 'CODE_REVIEW', 'title': 'Review', 'payload': '{}',
                           'requireApproval': True})
        headers = signed_headers('POST', '/api/jobs', body)
        response = httpx.post(address + '/api/jobs', headers=headers, content=body)
        assert response.status_code == 200
        payload = response.json()
        assert payload['state'] == 'QUEUED'
        assert payload['requires_approval'] is True
        # The bridge never executes a job by itself.
        assert bridge.jobs.get(payload['id']).state == 'QUEUED'
    finally:
        listener.stop()


def test_stopping_twice_is_safe():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    listener.start()
    listener.stop()
    listener.stop()
    assert not listener.running


def test_starting_twice_is_refused():
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, allow_plaintext=True))
    listener.start()
    try:
        with pytest.raises(ListenerError):
            listener.start()
    finally:
        listener.stop()


def _self_signed_certificate(tmp_path):
    """Create a throwaway certificate so the TLS path is really exercised."""
    import subprocess
    cert = tmp_path / 'cert.pem'
    key = tmp_path / 'key.pem'
    result = subprocess.run(
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
         '-subj', '/CN=127.0.0.1', '-keyout', str(key), '-out', str(cert)],
        capture_output=True)
    if result.returncode != 0:
        pytest.skip('openssl is not available to create a test certificate')
    return str(cert), str(key)


def test_the_listener_serves_over_tls(tmp_path):
    cert, key = _self_signed_certificate(tmp_path)
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, tls_cert=cert, tls_key=key))
    address = listener.start()
    try:
        assert address.startswith('https://')
        with httpx.Client(verify=False) as client:
            response = client.get(address + '/api/status',
                                  headers=signed_headers('GET', '/api/status'))
            assert response.status_code == 200
            assert response.json()['peer_id'] == 'windows-test'
            rejected = client.get(address + '/api/status')
            assert rejected.status_code == 403
    finally:
        listener.stop()


def test_a_broken_certificate_is_refused(tmp_path):
    cert = tmp_path / 'cert.pem'
    key = tmp_path / 'key.pem'
    cert.write_text('not a certificate')
    key.write_text('not a key')
    listener = BridgeListener(make_bridge(), ListenerConfig(port=0, tls_cert=str(cert),
                                                           tls_key=str(key)))
    with pytest.raises(ListenerError):
        listener.start()
