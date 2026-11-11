"""Behaviour of the desktop bridge handler.

The handler is exercised without any socket: requests are signed exactly the
way the Android client signs them and are handed to `BridgeServer.handle`.
"""
import json

from remote.pairing import PairingStore
from remote.protocol import KEY_ID, sign
from remote.server import BridgeRequest, BridgeServer

SECRET = 'shared-secret-for-tests-0123456789abcdef'


def make_server(**kwargs):
    pairing = PairingStore()
    pairing.pair(key_id=KEY_ID, label='phone', secret=SECRET)
    return BridgeServer(pairing, peer_id='windows-test', agent_version='0.3.0', **kwargs)


def signed_request(server, method, path, body='', nonce='nonce-1', timestamp=None,
                   secret=SECRET, remote_addr='127.0.0.1', key_id=KEY_ID):
    """Build a request signed the way BridgeClient.kt signs it."""
    moment = timestamp or str(int(server._now() * 1000))
    signature = sign(method, path, moment, body, secret, nonce)
    return BridgeRequest(
        method=method,
        path=path,
        headers={
            'X-Jarvis-Key-Id': key_id,
            'X-Jarvis-Timestamp': moment,
            'X-Jarvis-Nonce': nonce,
            'X-Jarvis-Signature': signature,
        },
        body=body,
        remote_addr=remote_addr,
    )


def test_status_reports_the_fields_the_android_client_reads():
    server = make_server()
    response = server.handle(signed_request(server, 'GET', '/api/status'))
    assert response.status == 200
    assert response.payload['peer_id'] == 'windows-test'
    assert response.payload['state'] == 'online'
    assert response.payload['agent_version'] == '0.3.0'
    assert response.payload['queued_jobs'] == 0
    assert response.payload['running_jobs'] == 0
    assert response.payload['detail'] == 'JARVIS AI bridge'


def test_an_unsigned_request_is_rejected():
    server = make_server()
    response = server.handle(BridgeRequest('GET', '/api/status', {}))
    assert response.status == 403


def test_a_tampered_body_is_rejected():
    server = make_server()
    request = signed_request(server, 'POST', '/api/jobs', json.dumps({'kind': 'CUSTOM'}))
    tampered = BridgeRequest('POST', '/api/jobs', request.headers, json.dumps({'kind': 'WORKFLOW'}))
    assert server.handle(tampered).status == 403


def test_a_request_with_a_wrong_secret_is_rejected():
    server = make_server()
    request = signed_request(server, 'GET', '/api/status', secret='wrong-secret')
    assert server.handle(request).status == 403


def test_an_unknown_key_id_is_rejected():
    server = make_server()
    request = signed_request(server, 'GET', '/api/status', key_id='jarvis-blue-mobile-v2')
    assert server.handle(request).status == 403


def test_a_revoked_device_is_rejected():
    server = make_server()
    server.pairing.revoke(KEY_ID)
    request = signed_request(server, 'GET', '/api/status')
    assert server.handle(request).status == 403


def test_a_replayed_request_is_rejected():
    server = make_server()
    request = signed_request(server, 'GET', '/api/status', nonce='same-nonce')
    assert server.handle(request).status == 200
    assert server.handle(request).status == 403


def test_a_request_outside_the_clock_window_is_rejected():
    server = make_server()
    request = signed_request(server, 'GET', '/api/status', timestamp='1000000000000')
    assert server.handle(request).status == 403


def test_a_request_from_a_public_address_is_rejected():
    server = make_server()
    request = signed_request(server, 'GET', '/api/status', remote_addr='203.0.113.10')
    assert server.handle(request).status == 403


def test_an_unknown_endpoint_is_not_exposed():
    server = make_server()
    request = signed_request(server, 'GET', '/api/secret')
    assert server.handle(request).status == 404


def test_a_submitted_job_is_queued_and_needs_approval():
    server = make_server()
    body = json.dumps({'kind': 'CODE_REVIEW', 'title': 'Review the bridge',
                       'payload': '{}', 'requireApproval': True})
    response = server.handle(signed_request(server, 'POST', '/api/jobs', body))
    assert response.status == 200
    assert response.payload['kind'] == 'CODE_REVIEW'
    assert response.payload['state'] == 'QUEUED'
    assert response.payload['requires_approval'] is True
    assert response.payload['error'] is None


def test_the_job_list_reports_the_submitted_job():
    server = make_server()
    body = json.dumps({'kind': 'PYTHON_PROJECT', 'title': 'Build a project',
                       'payload': '{}', 'requireApproval': False})
    server.handle(signed_request(server, 'POST', '/api/jobs', body))
    response = server.handle(signed_request(server, 'GET', '/api/jobs', nonce='nonce-2'))
    assert response.status == 200
    assert len(response.payload['jobs']) == 1
    assert response.payload['jobs'][0]['title'] == 'Build a project'


def test_a_job_can_be_cancelled():
    server = make_server()
    body = json.dumps({'kind': 'CUSTOM', 'title': 'Cancel me', 'payload': '{}'})
    created = server.handle(signed_request(server, 'POST', '/api/jobs', body)).payload
    cancel = signed_request(server, 'POST', f"/api/jobs/{created['id']}/cancel", '{}',
                             nonce='nonce-3')
    response = server.handle(cancel)
    assert response.status == 200
    assert response.payload['ok'] is True
    assert server.jobs.get(created['id']).state == 'CANCELLED'


def test_an_invalid_job_kind_is_refused():
    server = make_server()
    body = json.dumps({'kind': 'NOT_A_KIND', 'title': 'x', 'payload': '{}'})
    assert server.handle(signed_request(server, 'POST', '/api/jobs', body)).status == 400


def test_an_invalid_json_body_is_refused():
    server = make_server()
    assert server.handle(signed_request(server, 'POST', '/api/jobs', 'not json')).status == 400
