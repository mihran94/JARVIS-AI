"""Tests for the Mobile Bridge page.

The page is exercised offscreen. The listener is not started on a public
address and no phone is involved: the owner side is what is under test.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.bridge_panel import BridgePanel
from remote.pairing import PairingStore
from remote.protocol import KEY_ID
from security.policy import Policy


class FakeVault:
    """Stands in for the Windows credential vault on a non Windows system."""

    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name, '')

    def put(self, name, secret):
        self.values[name] = secret

    def delete(self, name):
        self.values.pop(name, None)


def make_panel(tmp_path, confirm=None):
    """Build the page with a fake vault and a notify that records failures."""
    app = QApplication.instance() or QApplication([])
    policy = Policy()
    from core.store import Store
    store = Store(tmp_path / 'history.sqlite3')
    vault = FakeVault()
    errors = []

    def notify(operation):
        try:
            operation()
        except Exception as error:
            errors.append(str(error))

    panel = BridgePanel(policy, store, vault,
                        confirm if confirm is not None else (lambda action: True),
                        notify)
    panel.errors = errors
    return app, panel


def test_the_listener_is_off_by_default(tmp_path):
    app, panel = make_panel(tmp_path)
    assert not panel.listener.running
    assert 'Stopped' in panel.listener_status.text()
    assert panel.start_button.isEnabled()
    assert not panel.stop_button.isEnabled()
    panel.close()


def test_pairing_shows_the_secret_once_and_lists_the_device(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.pair_device()
    secret = panel.secret_display.toPlainText()
    assert len(secret) >= 32
    assert panel.devices.rowCount() == 1
    assert panel.devices.item(0, 0).text() == KEY_ID
    assert panel.devices.item(0, 2).text() == 'active'
    # The secret is stored in the vault, never in the panel state.
    assert panel.pairing.secret_for(KEY_ID) == secret
    panel.close()


def test_revoking_a_phone_removes_its_secret(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.pair_device()
    panel.devices.setCurrentCell(0, 0)
    panel.revoke_device()
    assert panel.pairing.secret_for(KEY_ID) is None
    assert panel.devices.item(0, 2).text() == 'revoked'
    panel.close()


def test_a_remote_job_waits_for_the_owner(tmp_path):
    app, panel = make_panel(tmp_path)
    job = panel.bridge.jobs.submit('CODE_REVIEW', 'Review the bridge', '{}', True)
    panel.refresh()
    assert panel.jobs.rowCount() == 1
    assert panel.bridge.jobs.get(job.id).state == 'QUEUED'
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    assert panel.bridge.jobs.get(job.id).state == 'RUNNING'
    panel.close()


def test_declining_the_approval_leaves_the_job_queued(tmp_path):
    app, panel = make_panel(tmp_path, confirm=lambda action: False)
    job = panel.bridge.jobs.submit('CODE_REVIEW', 'Review the bridge', '{}', True)
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    assert panel.bridge.jobs.get(job.id).state == 'QUEUED'
    panel.close()


def test_the_listener_refuses_to_start_without_tls(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.host.setText('127.0.0.1')
    panel.port.setText('0')
    panel.plaintext.setChecked(False)
    errors = []

    def notify(operation):
        try:
            operation()
        except Exception as error:
            errors.append(str(error))

    panel.notify = notify
    panel.start_listener()
    assert errors and 'TLS' in errors[0]
    assert not panel.listener.running
    panel.close()


def test_the_listener_starts_on_the_loopback_interface(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.host.setText('127.0.0.1')
    panel.port.setText('0')
    panel.plaintext.setChecked(True)
    panel.start_listener()
    try:
        assert panel.listener.running
        assert panel.listener.address.startswith('http://127.0.0.1')
        assert 'Listening on' in panel.listener_status.text()
    finally:
        panel.stop_listener()
    assert not panel.listener.running
    panel.close()
