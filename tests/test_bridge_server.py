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


def test_screen_capture_requires_authentication_and_is_never_cached():
    calls = []
    server = make_server(screen_provider=lambda: calls.append(1) or {'image': 'frame'})
    assert server.handle(BridgeRequest('POST', '/api/screen')).status == 403
    assert calls == []
    assert server.handle(signed_request(server, 'GET', '/api/screen')).status == 404
    assert calls == []
    response = server.handle(signed_request(server, 'POST', '/api/screen', nonce='screen-1'))
    assert response.status == 200
    assert response.payload == {'image': 'frame'}
    assert calls == [1]
    assert server.handle(signed_request(server, 'POST', '/api/screen', nonce='screen-2')).status == 200
    assert calls == [1, 1]


def test_screen_request_rejects_body_and_unavailable_provider():
    server = make_server()
    assert server.handle(signed_request(server, 'POST', '/api/screen')).status == 503
    assert server.handle(signed_request(server, 'POST', '/api/screen', '{}', nonce='body')).status == 400


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


def test_invalid_signature_does_not_consume_a_nonce():
    server = make_server()
    forged = signed_request(server, 'GET', '/api/status', secret='wrong-secret')
    assert server.handle(forged).status == 403
    assert server.handle(signed_request(server, 'GET', '/api/status')).status == 200


def test_jobs_can_only_be_read_or_cancelled_by_the_requesting_phone():
    server = make_server()
    second_key = 'second-phone'
    server.pairing.pair(key_id=second_key, label='Second phone', secret=SECRET)
    body = json.dumps({'kind': 'CUSTOM', 'title': 'Disk check',
                       'payload': '{"action":"check_disk_space"}', 'requireApproval': False})
    job = server.handle(signed_request(server, 'POST', '/api/jobs', body)).payload
    assert job['requires_approval'] is True
    assert 'operation' not in job and 'peer_id' not in job

    path = '/api/jobs/' + job['id']
    jobs = server.handle(signed_request(server, 'GET', '/api/jobs', nonce='list', key_id=second_key))
    assert jobs.payload == {'jobs': []}
    request = signed_request(server, 'GET', path, nonce='read', key_id=second_key)
    assert server.handle(request).status == 404
    request = signed_request(server, 'POST', path + '/cancel', nonce='cancel', key_id=second_key)
    assert server.handle(request).status == 404
    assert server.jobs.get(job['id']).state == 'QUEUED'


def test_phone_wake_is_scoped_one_use_and_revocable():
    from remote.protocol import wake_secret
    wakes = []
    server = make_server(wake=lambda: wakes.append(True) or True)
    key = wake_secret(SECRET)
    request = signed_request(server, 'POST', '/api/wake', secret=key)
    assert server.handle(request).payload == {'queued': True}
    assert server.handle(request).status == 403
    assert server.handle(signed_request(server, 'GET', '/api/status', secret=key, nonce='two')).status == 403
    assert server.handle(signed_request(server, 'POST', '/api/wake', body='open app',
                                        secret=key, nonce='three')).status == 400
    server.pairing.revoke(KEY_ID)
    assert server.handle(signed_request(server, 'POST', '/api/wake', secret=key, nonce='four')).status == 403
    assert wakes == [True]
