"""Tests for the Mobile Bridge page.

The page is exercised offscreen. The listener is not started on a public
address and no phone is involved: the owner side is what is under test.
"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.bridge_panel import BridgePanel
from remote.pairing import PairingStore
from remote.protocol import KEY_ID
from security.policy import Policy
from test_bridge_server import SECRET, signed_request


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
    result = panel.bridge.jobs.get(job.id)
    assert result.state == 'REJECTED'
    assert result.started_at is None
    assert result.error == 'No supported desktop action was requested.'
    panel.close()


def test_approved_disk_check_reads_real_capacity(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.pairing.pair(key_id=KEY_ID, label='Test phone', secret=SECRET)
    body = json.dumps({'kind': 'CUSTOM', 'title': 'Disk check',
                       'payload': '{"action":"check_disk_space"}', 'requireApproval': False})
    queued = panel.bridge.handle(signed_request(panel.bridge, 'POST', '/api/jobs', body))
    assert queued.status == 200
    assert queued.payload['state'] == 'QUEUED'
    assert queued.payload['requires_approval'] is True
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    request = signed_request(panel.bridge, 'GET', '/api/jobs/' + queued.payload['id'], nonce='result')
    response = panel.bridge.handle(request)
    assert response.status == 200
    result = response.payload
    assert result['state'] == 'SUCCEEDED'
    assert result['started_at'] <= result['finished_at']
    assert result['progress'] == 1.0
    assert len(result['outputs']) == 1 and ' GiB free of ' in result['outputs'][0]
    panel.close()


def test_revoked_phone_cannot_run_a_queued_disk_check(tmp_path):
    app, panel = make_panel(tmp_path)
    pairing = panel.pairing.pair(key_id=KEY_ID, label='Test phone', secret=SECRET)
    job = panel.bridge.jobs.submit('CUSTOM', 'Disk check', '{"action":"check_disk_space"}',
                                   True, peer_id=pairing.device.peer_id)
    panel.pairing.revoke(KEY_ID)
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    result = panel.bridge.jobs.get(job.id)
    assert result.state == 'REJECTED'
    assert result.started_at is None
    assert result.error == 'The requesting phone is no longer paired.'
    panel.close()


def test_failed_disk_check_has_no_output_or_private_error(tmp_path, monkeypatch):
    app, panel = make_panel(tmp_path)
    job = panel.bridge.jobs.submit('CUSTOM', 'Disk check', '{"action":"check_disk_space"}', True)
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)

    def unavailable(path):
        assert panel.bridge.jobs.get(job.id).state == 'RUNNING'
        raise OSError('private test path')

    monkeypatch.setattr('desktop.bridge_panel.shutil.disk_usage', unavailable)
    panel.approve_job()
    result = panel.bridge.jobs.get(job.id)
    assert result.state == 'FAILED'
    assert result.outputs == []
    assert result.error == 'Could not verify disk capacity.'
    assert panel.errors == [result.error]
    panel.close()


def test_cancelled_disk_check_discards_late_output(tmp_path, monkeypatch):
    from collections import namedtuple

    app, panel = make_panel(tmp_path)
    job = panel.bridge.jobs.submit('CUSTOM', 'Disk check', '{"action":"check_disk_space"}', True)
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)

    def cancel_during_check(path):
        assert panel.bridge.jobs.cancel(job.id)
        return namedtuple('Usage', 'total free')(1024, 512)

    monkeypatch.setattr('desktop.bridge_panel.shutil.disk_usage', cancel_during_check)
    panel.approve_job()
    result = panel.bridge.jobs.get(job.id)
    assert result.state == 'CANCELLED'
    assert result.outputs == []
    panel.close()


def test_declining_the_approval_leaves_the_job_queued(tmp_path):
    app, panel = make_panel(tmp_path, confirm=lambda action: False)
    job = panel.bridge.jobs.submit('CUSTOM', 'Disk check', '{"action":"check_disk_space"}', True)
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


def test_the_page_can_make_a_private_certificate_and_show_its_fingerprint(tmp_path):
    """The owner must be able to get a working certificate without a CA."""
    from remote import certificate

    if not certificate.shutil.which('openssl'):
        pytest.skip('OpenSSL is not available on this machine')
    app, panel = make_panel(tmp_path)
    panel.create_certificate()
    assert not panel.errors, panel.errors
    assert panel.certificate.text().endswith('bridge-cert.pem')
    assert panel.key.text().endswith('bridge-key.pem')
    assert os.path.exists(panel.certificate.text())
    assert os.path.exists(panel.key.text())
    # The fingerprint the phone will pin is on the page.
    assert 'SHA-256' in panel.fingerprint_label.text()
    assert panel.certificate_fingerprint() == \
        certificate.fingerprint_from_file(panel.certificate.text())
    panel.close()


def test_the_page_shows_that_no_certificate_has_been_chosen_yet(tmp_path):
    app, panel = make_panel(tmp_path)
    assert 'No certificate' in panel.fingerprint_label.text()
    assert panel.certificate_fingerprint() == ''
    panel.close()


def test_the_owner_can_allow_a_vpn_or_tunnel_peer(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.peer_hosts.setText('10.8.0.2, 192.168.1.9')
    assert panel.allowed_peer_hosts() == ('10.8.0.2', '192.168.1.9')
    panel.peer_hosts.setText('10.8.0.2; 192.168.1.9')
    assert panel.allowed_peer_hosts() == ('10.8.0.2', '192.168.1.9')
    panel.peer_hosts.setText('')
    assert panel.allowed_peer_hosts() == ()
    panel.close()


def test_the_pairing_code_carries_the_certificate_fingerprint(tmp_path):
    """The phone has to know which certificate to trust."""
    from remote import certificate

    if not certificate.shutil.which('openssl'):
        pytest.skip('OpenSSL is not available on this machine')
    app, panel = make_panel(tmp_path)
    panel.create_certificate()
    panel.phone_address.setText('https://pc.example.lan:8765')
    panel.pair_browser_device()
    panel.show_pairing_code()
    assert not panel.errors, panel.errors
    code = panel.code_text.toPlainText()
    assert 'fp=' + panel.certificate_fingerprint() in code
    panel.close()


def test_browser_pairing_issues_a_separate_key_for_each_device(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.phone_address.setText('https://pc.example.lan:8765')
    panel.pair_browser_device()
    first_key = panel.phone_key.text()
    first_secret = panel.pairing.secret_for(first_key)

    panel.pair_browser_device()
    second_key = panel.phone_key.text()
    assert not panel.errors, panel.errors
    assert len(first_key) == 6 and first_key.isdecimal()
    assert len(second_key) == 6 and second_key.isdecimal()
    assert first_key != second_key
    assert first_secret
    assert panel.pairing.secret_for(first_key) == first_secret
    panel.close()


def test_browser_qr_rotates_only_after_a_signed_request(tmp_path):
    app, panel = make_panel(tmp_path)
    panel.phone_address.setText('https://pc.example.lan:8765')
    panel.pair_browser_device()
    first_key = panel.phone_key.text()
    first_code = panel.code_text.toPlainText()
    secret = panel.pairing.secret_for(first_key)

    assert panel.pairing_timer.isActive()
    panel._rotate_confirmed_pairing()
    assert panel.code_text.toPlainText() == first_code

    request = signed_request(panel.bridge, 'GET', '/api/status',
                             secret=secret, key_id=first_key)
    assert panel.bridge.handle(request).status == 200
    panel._rotate_confirmed_pairing()

    second_key = panel.phone_key.text()
    assert second_key != first_key
    assert panel.code_text.toPlainText() != first_code
    assert panel.pairing.secret_for(first_key) == secret
    assert not panel.errors
    panel.close()


def test_qr_pixmap_has_every_module_and_its_quiet_zone(tmp_path):
    from PySide6.QtGui import QColor
    from desktop.bridge_pairing import pairing_matrix

    app, panel = make_panel(tmp_path)
    payload = 'https://pc.example.lan:8765/#pair=sample'
    panel._draw_qr(payload)
    image = panel.code_qr.pixmap().toImage()
    matrix = pairing_matrix(payload, border=4)
    module_size = image.width() // len(matrix)
    assert module_size > 0
    assert image.width() == image.height() == len(matrix) * module_size
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            expected = QColor('black' if dark else 'white')
            assert image.pixelColor(x * module_size, y * module_size) == expected
    panel.close()


def test_phone_open_app_dispatches_only_after_owner_approval(tmp_path, monkeypatch):
    from automation import named_apps

    app, panel = make_panel(tmp_path, lambda _: False)
    dispatched = []

    class InstalledApp:
        Name = 'Notepad'
        Path = 'Notepad.App'

        def InvokeVerb(self):
            dispatched.append(self.Name)

    monkeypatch.setattr(named_apps, 'installed', lambda *_: InstalledApp())
    job = panel.bridge.jobs.submit('CUSTOM', 'Misleading title',
                                   '{"action":"open_installed_app","app":"Notepad"}', False)
    assert job.title == 'Open Notepad'
    assert job.requires_approval
    panel.refresh()
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    assert dispatched == []
    assert panel.bridge.jobs.get(job.id).state == 'QUEUED'
    panel.confirm = lambda _: True
    panel.jobs.setCurrentCell(0, 0)
    panel.approve_job()
    assert dispatched == ['Notepad']
    result = panel.bridge.jobs.get(job.id)
    assert result.state == 'SUCCEEDED'
    assert 'received the launch request' in result.outputs[0]
    panel.close()
