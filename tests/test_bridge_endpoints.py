"""The new bridge endpoints: one job, chat, memory, notifications and audit.

The handler is exercised without a socket, exactly the way the Android
client and the iPhone PWA reach it.
"""
import json

import pytest

from remote.audit import AuditLog, body_digest
from remote.memory import MemoryStore
from remote.notifications import NotificationStore
from remote.pairing import PairingStore
from remote.protocol import KEY_ID, sign
from remote.server import BridgeHandlerError, BridgeRequest, BridgeServer

SECRET = 'shared-secret-for-tests-0123456789abcdef'


def make_server(**kwargs):
    pairing = PairingStore()
    pairing.pair(key_id=KEY_ID, label='phone', secret=SECRET)
    return BridgeServer(pairing, peer_id='windows-test', agent_version='0.3.0', **kwargs)


def signed_request(server, method, path, body='', nonce='nonce-1', timestamp=None,
                   secret=SECRET, remote_addr='127.0.0.1', key_id=KEY_ID):
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


# --------------------------------------------------------------- one job

def test_one_job_can_be_read_back():
    server = make_server()
    submitted = server.handle(signed_request(
        server, 'POST', '/api/jobs', json.dumps({'kind': 'CUSTOM', 'title': 'Nightly report'})))
    assert submitted.status == 200
    job_id = submitted.payload['id']
    fetched = server.handle(signed_request(server, 'GET', '/api/jobs/' + job_id, nonce='n2'))
    assert fetched.status == 200
    assert fetched.payload['title'] == 'Nightly report'
    assert fetched.payload['state'] == 'QUEUED'


def test_an_unknown_job_is_not_found():
    server = make_server()
    response = server.handle(signed_request(server, 'GET', '/api/jobs/nothing', nonce='n2'))
    assert response.status == 404


def test_a_job_path_cannot_reach_another_endpoint():
    server = make_server()
    response = server.handle(signed_request(server, 'GET', '/api/jobs/a/b', nonce='n2'))
    assert response.status == 404


# ----------------------------------------------------------------- chat

def test_chat_is_not_served_until_the_desktop_enables_it():
    server = make_server()
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': 'hello', 'consent': True})))
    assert response.status == 503
    assert 'not enabled' in response.payload['error']


def test_chat_returns_the_desktop_answer():
    server = make_server(chat=lambda message, consent: {
        'text': 'answer for ' + message, 'provider': 'ollama', 'model': 'local'})
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': 'hello', 'consent': True})))
    assert response.status == 200
    assert response.payload['text'] == 'answer for hello'
    assert response.payload['provider'] == 'ollama'


def test_chat_needs_a_message():
    server = make_server(chat=lambda message, consent: {'text': 'x'})
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': '   '}), nonce='n2'))
    assert response.status == 400


def test_chat_rejects_an_unusable_answer():
    server = make_server(chat=lambda message, consent: {'nope': True})
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': 'hi'}), nonce='n2'))
    assert response.status == 502


def test_a_chat_failure_is_reported_without_details():
    def explode(message, consent):
        raise RuntimeError('secret detail 12345')

    server = make_server(chat=explode)
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': 'hi'}), nonce='n2'))
    assert response.status == 502
    assert 'secret detail' not in response.payload['error']


def test_an_oversized_message_is_refused():
    server = make_server(chat=lambda message, consent: {'text': 'x'})
    response = server.handle(signed_request(
        server, 'POST', '/api/chat', json.dumps({'message': 'x' * 9000}), nonce='n2'))
    assert response.status == 400


# --------------------------------------------------------------- memory

def test_a_memory_entry_travels_to_the_desktop():
    server = make_server()
    stored = server.handle(signed_request(
        server, 'POST', '/api/memory', json.dumps({'text': 'Milk', 'source': 'phone'})))
    assert stored.status == 200
    assert stored.payload['text'] == 'Milk'
    assert stored.payload['source'] == 'phone'
    listed = server.handle(signed_request(server, 'GET', '/api/memory', nonce='n2'))
    assert listed.status == 200
    assert [entry['text'] for entry in listed.payload['memory']] == ['Milk']


def test_an_empty_memory_entry_is_refused():
    server = make_server()
    response = server.handle(signed_request(
        server, 'POST', '/api/memory', json.dumps({'text': '  '}), nonce='n2'))
    assert response.status == 400


def test_the_memory_store_drops_the_oldest_entries():
    store = MemoryStore(limit=3)
    for index in range(5):
        store.append('entry %d' % index)
    entries = store.entries()
    assert len(entries) == 3
    assert entries[0].text == 'entry 2'


# --------------------------------------------------------- notifications

def test_a_notification_is_delivered_and_acknowledged():
    server = make_server()
    server.notifications.push('Backup finished', 'All files copied', 'info')
    listed = server.handle(signed_request(server, 'GET', '/api/notifications', nonce='n2'))
    assert listed.status == 200
    pending = listed.payload['notifications']
    assert len(pending) == 1
    assert pending[0]['title'] == 'Backup finished'
    acked = server.handle(signed_request(
        server, 'POST', '/api/notifications/' + pending[0]['id'] + '/ack', nonce='n3'))
    assert acked.status == 200
    assert acked.payload['ok'] is True
    again = server.handle(signed_request(server, 'GET', '/api/notifications', nonce='n4'))
    assert again.payload['notifications'] == []


def test_an_unknown_notification_level_is_refused():
    store = NotificationStore()
    with pytest.raises(Exception):
        store.push('Title', 'Body', 'critical')


# ----------------------------------------------------------------- audit

def test_every_request_is_audited():
    server = make_server()
    server.handle(signed_request(server, 'GET', '/api/status'))
    server.handle(signed_request(server, 'GET', '/api/status', nonce='n2'))
    entries = server.audit.entries()
    assert len(entries) == 2
    assert entries[0].key_id == KEY_ID
    assert entries[0].method == 'GET'
    assert entries[0].path == '/api/status'
    assert entries[0].status == 200


def test_the_audit_never_stores_the_body():
    server = make_server()
    body = json.dumps({'message': 'my private question', 'consent': True})
    server.handle(signed_request(server, 'POST', '/api/chat', body))
    entry = server.audit.entries()[0]
    assert 'my private question' not in json.dumps(entry.to_json())
    assert entry.body_digest == body_digest(body)
    assert len(entry.body_digest) == 16


def test_a_refused_request_is_audited_too():
    server = make_server()
    response = server.handle(BridgeRequest('GET', '/api/status', {}, remote_addr='10.0.0.9'))
    assert response.status == 403
    entries = server.audit.entries()
    assert len(entries) == 1
    assert entries[0].status == 403


def test_the_audit_log_is_bounded():
    log = AuditLog(limit=3)
    for index in range(10):
        log.record('key', 'GET', '/api/status', 200)
    assert len(log.entries()) == 3


# ---------------------------------------------------------------- status

def test_the_status_provider_fills_the_machine_numbers():
    server = make_server(status_provider=lambda: {
        'cpu_percent': 12.5, 'memory_percent': 44.0, 'disk_free_gb': 120.5})
    response = server.handle(signed_request(server, 'GET', '/api/status'))
    assert response.status == 200
    assert response.payload['cpu_percent'] == 12.5
    assert response.payload['memory_percent'] == 44.0
    assert response.payload['disk_free_gb'] == 120.5
    assert response.payload['gpu_percent'] is None


def test_a_broken_status_provider_does_not_break_the_call():
    def explode():
        raise RuntimeError('no')

    server = make_server(status_provider=explode)
    response = server.handle(signed_request(server, 'GET', '/api/status'))
    assert response.status == 200
    assert response.payload['cpu_percent'] is None
