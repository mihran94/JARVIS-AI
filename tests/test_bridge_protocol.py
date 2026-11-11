"""Cross-implementation vectors for the desktop/mobile bridge protocol.

The Android client signs requests in `core/windows/BridgeClient.kt`
(jarvis-blue-android). The vectors below are the same ones asserted by
`BridgeSignatureTest.kt` on that side. If either implementation changes the
canonical scheme, these tests fail and the two halves stop interoperating.
"""
import pytest

from remote.pairing import PairingError, PairingStore
from remote.protocol import (
    KEY_ID,
    ProtocolError,
    canonical_string,
    check_timestamp,
    sha256_hex,
    sign,
    verify,
)
from remote.replay import ReplayGuard

SECRET = 'test-secret'
NONCE = 'nonce-123'
TIMESTAMP = '1700000000000'


def test_sha256_of_empty_body_matches_the_android_reference():
    assert sha256_hex('') == ('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')


def test_hmac_signature_matches_the_android_reference():
    signature = sign('GET', '/api/status', TIMESTAMP, '', SECRET, NONCE)
    assert signature == '5a0eff83c8875fc160be921c708461920dfa3f9775821784555822eb38d32a3d'


def test_canonical_string_keeps_the_agreed_field_order():
    assert canonical_string('get', '/api/status', TIMESTAMP, NONCE, '') == '\n'.join([
        'GET',
        '/api/status',
        TIMESTAMP,
        NONCE,
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    ])


def test_different_nonces_produce_different_signatures():
    first = sign('GET', '/api/status', TIMESTAMP, '', SECRET, 'nonce-a')
    second = sign('GET', '/api/status', TIMESTAMP, '', SECRET, 'nonce-b')
    assert first != second


def test_body_is_part_of_the_signature_so_payloads_cannot_be_swapped():
    first = sign('POST', '/api/jobs', TIMESTAMP, '{"a":1}', SECRET, 'nonce')
    second = sign('POST', '/api/jobs', TIMESTAMP, '{"a":2}', SECRET, 'nonce')
    assert first != second


def test_verify_accepts_a_matching_signature():
    signature = sign('GET', '/api/status', TIMESTAMP, '', SECRET, NONCE)
    verify('GET', '/api/status', TIMESTAMP, '', SECRET, NONCE, signature)


def test_verify_rejects_a_wrong_signature():
    signature = sign('GET', '/api/status', TIMESTAMP, '', SECRET, NONCE)
    with pytest.raises(ProtocolError):
        verify('GET', '/api/jobs', TIMESTAMP, '', SECRET, NONCE, signature)


def test_verify_rejects_a_missing_signature():
    with pytest.raises(ProtocolError):
        verify('GET', '/api/status', TIMESTAMP, '', SECRET, NONCE, '')


def test_signing_refuses_an_empty_secret():
    with pytest.raises(ValueError):
        sign('GET', '/api/status', TIMESTAMP, '', '', NONCE)


def test_timestamp_outside_the_window_is_rejected():
    with pytest.raises(ProtocolError):
        check_timestamp('1700000000000', now=1700000000 + 600)
    with pytest.raises(ProtocolError):
        check_timestamp('1700000000000', now=1700000000 - 600)


def test_timestamp_inside_the_window_is_accepted():
    check_timestamp('1700000000000', now=1700000000 + 10)


def test_malformed_timestamp_is_rejected():
    with pytest.raises(ProtocolError):
        check_timestamp('not-a-timestamp', now=1700000000)


def test_a_nonce_can_only_be_used_once():
    guard = ReplayGuard()
    guard.check('nonce-a')
    with pytest.raises(ProtocolError):
        guard.check('nonce-a')


def test_nonce_guard_forgets_old_nonces():
    clock = {'now': 1000.0}
    guard = ReplayGuard(ttl_seconds=10, now=lambda: clock['now'])
    guard.check('nonce-a')
    clock['now'] = 1011.0
    guard.check('nonce-a')


def test_paired_device_secret_is_not_disclosed():
    store = PairingStore()
    pairing = store.pair(key_id=KEY_ID, label='phone')
    assert pairing.secret not in repr(pairing)
    assert pairing.secret not in repr(store.device(KEY_ID))
    assert store.secret_for(KEY_ID) == pairing.secret


def test_revoking_a_device_removes_its_secret():
    store = PairingStore()
    store.pair(key_id=KEY_ID, label='phone')
    store.revoke(KEY_ID)
    assert store.device(KEY_ID) is None
    assert store.secret_for(KEY_ID) is None


def test_a_key_id_cannot_be_paired_twice():
    store = PairingStore()
    store.pair(key_id=KEY_ID)
    with pytest.raises(PairingError):
        store.pair(key_id=KEY_ID)


def test_revoking_an_unknown_key_id_is_refused():
    store = PairingStore()
    with pytest.raises(PairingError):
        store.revoke('never-paired')
