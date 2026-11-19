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

def test_desktop_bridge_panel_reuses_pairing_after_reopen(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from desktop.bridge_panel import BridgePanel
    from security.policy import Policy

    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    notify = lambda callback: callback()
    first = BridgePanel(Policy(), store, vault, lambda action: True, notify)
    first.pair_device()
    original_secret = first.pairing.secret_for(KEY_ID)
    assert len(original_secret) >= 32
    first.close()

    restarted = BridgePanel(Policy(), Store(store.path), vault,
                            lambda action: True, notify)
    assert restarted.devices.rowCount() == 1
    assert restarted.devices.item(0, 2).text() == 'active'
    assert restarted.secret_display.toPlainText() == ''
    assert restarted.pairing.secret_for(KEY_ID) == original_secret
    restarted.devices.setCurrentCell(0, 0)
    restarted.revoke_device()
    restarted.close()

    final = BridgePanel(Policy(), Store(store.path), vault,
                        lambda action: True, notify)
    assert final.devices.item(0, 2).text() == 'revoked'
    assert final.pairing.secret_for(KEY_ID) is None
    final.close()


# --------------------------------------------------------------------------
# The fifteen minute rule
#
# The desktop tells the owner that the secret in a pairing code stops
# working after fifteen minutes. It used to be true only on the phone, which
# checked the code when it was scanned. The desktop kept the secret for
# ever, so a code that was never transferred, or one that leaked, stayed
# usable until the owner noticed and revoked it by hand.
# --------------------------------------------------------------------------


def a_clock_at(seconds):
    return lambda: seconds


def test_a_pairing_code_that_is_never_used_stops_working(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    pairing = PairingStore(VaultSecrets(FakeVault()), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    assert pairing.secret_for(KEY_ID) is not None
    # Twenty minutes later the window has passed.
    pairing._now = a_clock_at(1_000.0 + 1_200)
    assert pairing.secret_for(KEY_ID) is None
    assert pairing.device(KEY_ID) is not None, 'the record is still there'


def test_the_deadline_survives_a_restart(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    reloaded = PairingStore(VaultSecrets(vault), metadata_store=Store(store.path),
                             now=a_clock_at(1_000.0 + 1_200))
    assert reloaded.secret_for(KEY_ID) is None


def test_asking_for_the_code_again_moves_the_deadline(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    pairing = PairingStore(VaultSecrets(FakeVault()), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    pairing._now = a_clock_at(1_000.0 + 1_200)
    assert pairing.secret_for(KEY_ID) is None
    deadline = pairing.extend_deadline(KEY_ID, 2_000_000 + 900_000)
    assert deadline == 2_000_000 + 900_000
    assert pairing.secret_for(KEY_ID) is not None


def test_a_device_that_has_proved_itself_keeps_working(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    pairing = PairingStore(VaultSecrets(FakeVault()), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    pairing.confirm(KEY_ID)
    pairing._now = a_clock_at(1_000.0 + 86_400)
    assert pairing.secret_for(KEY_ID) is not None


def test_a_request_does_not_move_the_deadline(tmp_path):
    """Seeing the device must not give the pending code a fresh life."""
    store = Store(tmp_path / 'history.sqlite3')
    pairing = PairingStore(VaultSecrets(FakeVault()), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    pairing.touch(KEY_ID)
    assert pairing.devices()[0].expires_epoch_ms == 1_000_000 + 900_000
    pairing._now = a_clock_at(1_000.0 + 1_200)
    assert pairing.secret_for(KEY_ID) is None


def _a_signed_request(server, secret, nonce):
    timestamp = str(int(server._now() * 1000))
    return BridgeRequest('GET', '/api/status', headers={
        'X-Jarvis-Key-Id': KEY_ID, 'X-Jarvis-Timestamp': timestamp,
        'X-Jarvis-Nonce': nonce,
        'X-Jarvis-Signature': sign('GET', '/api/status', timestamp, '', secret, nonce),
    })


def test_the_bridge_refuses_a_device_whose_code_expired(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    # Twenty minutes later the window has passed, for the store and for the
    # server, which share the clock.
    pairing._now = a_clock_at(1_000.0 + 1_200)
    server = BridgeServer(pairing, now=a_clock_at(1_000.0 + 1_200))
    assert server.handle(_a_signed_request(server, vault.get('bridge:' + KEY_ID),
                                            'late')).status == 403


def test_the_bridge_trusts_a_device_that_has_made_a_request(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store,
                            now=a_clock_at(1_000.0))
    pairing.pair(key_id=KEY_ID, expires_epoch_ms=1_000_000 + 900_000)
    server = BridgeServer(pairing, now=a_clock_at(1_000.0))
    secret = vault.get('bridge:' + KEY_ID)
    assert server.handle(_a_signed_request(server, secret, 'first')).status == 200
    # The device proved itself, so the deadline no longer applies to it.
    pairing._now = a_clock_at(1_000.0 + 86_400)
    later = BridgeServer(pairing, now=a_clock_at(1_000.0 + 86_400))
    assert later.handle(_a_signed_request(later, secret, 'second')).status == 200


def test_a_device_without_a_deadline_is_unaffected(tmp_path):
    """A record made before the deadline existed keeps working."""
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    pairing = PairingStore(VaultSecrets(vault), metadata_store=store)
    pairing.pair(key_id=KEY_ID)
    assert pairing.secret_for(KEY_ID) is not None
    assert pairing.devices()[0].confirmed is False
    assert pairing.devices()[0].expires_epoch_ms == 0

