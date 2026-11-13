"""Tests for restart-stable device metadata and vault-only HMAC secrets."""
import json

from core.store import Store
from remote.pairing import PairingError, PairingStore, PAIRING_METADATA_KEY
from remote.protocol import KEY_ID, sign
from remote.secrets import VaultSecrets
from remote.server import BridgeRequest, BridgeServer


class FakeVault:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name, '')

    def put(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


def test_pairing_survives_restart_and_signed_request(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    original = PairingStore(VaultSecrets(vault), metadata_store=store)
    first = original.pair(key_id=KEY_ID, label='Android')
    saved = store.get(PAIRING_METADATA_KEY)
    assert saved[0]['key_id'] == KEY_ID
    assert saved[0]['label'] == 'Android'
    assert first.secret not in json.dumps(saved)
    assert 'secret' not in json.dumps(saved).lower()

    restarted = PairingStore(VaultSecrets(vault), metadata_store=Store(store.path))
    assert restarted.device(KEY_ID) == first.device
    assert restarted.secret_for(KEY_ID) == first.secret
    server = BridgeServer(restarted)
    timestamp = str(int(server._now() * 1000))
    nonce = 'post-restart'
    signed = BridgeRequest('GET', '/api/status', headers={
        'X-Jarvis-Key-Id': KEY_ID, 'X-Jarvis-Timestamp': timestamp,
        'X-Jarvis-Nonce': nonce,
        'X-Jarvis-Signature': sign('GET', '/api/status', timestamp, '', first.secret, nonce),
    })
    assert server.handle(signed).status == 200


def test_revocation_survives_restart_and_erases_vault_key(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store)
    pairing.pair(key_id=KEY_ID)
    pairing.revoke(KEY_ID)
    restarted = PairingStore(VaultSecrets(vault), metadata_store=Store(store.path))
    assert restarted.device(KEY_ID) is None
    assert restarted.secret_for(KEY_ID) is None
    assert restarted.devices()[0].revoked
    assert 'bridge:' + KEY_ID not in vault.values
    assert restarted.revoke(KEY_ID).revoked


def test_iphone_remains_paired_when_android_revoked(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store)
    android = pairing.pair(key_id=KEY_ID)
    iphone = pairing.pair(key_id='jarvis-iphone-v1', label='iPhone')
    pairing.revoke(KEY_ID)
    reloaded = PairingStore(VaultSecrets(vault), metadata_store=Store(store.path))
    assert reloaded.secret_for(KEY_ID) is None
    assert reloaded.secret_for('jarvis-iphone-v1') == iphone.secret
    assert android.secret not in json.dumps(store.get(PAIRING_METADATA_KEY))
    assert iphone.secret not in json.dumps(store.get(PAIRING_METADATA_KEY))


def test_vault_secret_is_needed_even_when_record_persisted(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    original = PairingStore(VaultSecrets(FakeVault()), metadata_store=store)
    original.pair(key_id=KEY_ID)
    lost_vault = PairingStore(VaultSecrets(FakeVault()), metadata_store=store)
    assert lost_vault.device(KEY_ID) is not None
    assert lost_vault.secret_for(KEY_ID) is None
    assert BridgeServer(lost_vault).handle(BridgeRequest('GET', '/api/status')).status == 403


def test_failed_persistence_cleans_new_key_and_raises_sanitized_error():
    class BrokenMetadata:
        def get(self, key, default=None):
            return default

        def set(self, key, value):
            raise OSError('private disk path')

    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=BrokenMetadata())
    try:
        pairing.pair(key_id=KEY_ID)
    except PairingError as exc:
        assert 'save' in str(exc)
        assert 'private disk path' not in str(exc)
    else:
        raise AssertionError('Pairing must fail if metadata cannot be saved')
    assert pairing.devices() == []
    assert vault.values == {}


def test_invalid_saved_record_fails_closed(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    store.set(PAIRING_METADATA_KEY, [{'key_id': KEY_ID, 'peer_id': 'one',
                                     'revoked': 'false', 'secret': 'bad'}])
    assert PairingStore(VaultSecrets(vault), metadata_store=store).devices() == []
    store.set(PAIRING_METADATA_KEY, [{'key_id': 'a', 'peer_id': 'b'}] * 33)
    assert PairingStore(VaultSecrets(vault), metadata_store=store).devices() == []


def test_repairing_a_revoked_device_creates_new_identity(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store)
    first = pairing.pair(key_id=KEY_ID)
    pairing.revoke(KEY_ID)
    second = pairing.pair(key_id=KEY_ID)
    assert first.secret != second.secret
    assert first.device.peer_id != second.device.peer_id
    reloaded = PairingStore(VaultSecrets(vault), metadata_store=store)
    assert not reloaded.device(KEY_ID).revoked
    assert reloaded.secret_for(KEY_ID) == second.secret
