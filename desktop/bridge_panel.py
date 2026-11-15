"""The Mobile Bridge page.

Pairing, connection status, remote jobs and owner approval for the phone
bridge. The page owns the listener and the paired device list.

Nothing here grants a permission by itself:

- the listener refuses to start without TLS unless the owner confirms that a
  private tunnel terminates TLS;
- a job that arrives from a phone is recorded as QUEUED and stays there until
  the owner approves it through the same one-use policy gateway that guards
  every other action in the application;
- revoking a key id removes the secret, so the phone is refused on its next
  request.
"""
import platform

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QSizePolicy,
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from agents.gateway import Gateway
from desktop.bridge_chat import BridgeChatService
from desktop.bridge_pairing import (
    DEFAULT_LIFETIME_SECONDS, PairingCodeError, expires_at, pairing_payload, pairing_svg,
)
from desktop.bridge_status import PlatformMetrics
from providers.registry import specs
from remote.certificate import CertificateError, ensure_certificate, fingerprint_from_file
from remote.listener import BridgeListener, ListenerConfig, ListenerError
from remote.pairing import PairingStore
from remote.protocol import KEY_ID
from remote.secrets import VaultSecrets
from remote.server import BridgeServer
from security.policy import Action

#: The key id an iPhone uses. It is different from the Android one, so that
#: revoking one phone does not affect the other.
IPHONE_KEY_ID = 'jarvis-iphone-v1'


def _readable(digest: str) -> str:
    """A fingerprint in groups, so a long value can still wrap on a narrow page."""
    digest = (digest or '').strip()
    return ' '.join(digest[index:index + 8] for index in range(0, len(digest), 8))


class BridgePanel(QWidget):
    """Owns the bridge listener, the paired devices and the remote jobs."""

    def __init__(self, policy, store, vault, confirm, notify, *, pairing=None, bridge=None,
                 listener=None, router=None):
        super().__init__()
        self.policy, self.store = policy, store
        self.confirm, self.notify = confirm, notify
        self.gateway = Gateway(policy, store)
        self.pairing = pairing if pairing is not None else PairingStore(
            VaultSecrets(vault), metadata_store=store)
        self.bridge = bridge if bridge is not None else BridgeServer(
            self.pairing, peer_id=platform.node() or 'windows',
            agent_version='0.3.0', allowed_hosts=('127.0.0.1', '::1'),
            status_provider=PlatformMetrics().snapshot)
        self.listener = listener if listener is not None else BridgeListener(self.bridge)
        self.chat = BridgeChatService(router, store, vault, policy=policy) if router else None
        if self.chat is not None:
            self.bridge.set_chat(self.chat.answer)
            self.bridge.set_memory_allowed(lambda: self.chat.memory_sync)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 10, 10)
        title = QLabel('Phone Remote')
        title.setStyleSheet('font-size:24px;font-weight:600')
        layout.addWidget(title)
        note = QLabel('Choose iPhone or Android. Use Advanced connection to start the private listener.')
        note.setWordWrap(True)
        layout.addWidget(note)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        listener_box = QGroupBox('Listener')
        listener_layout = QFormLayout(listener_box)
        self.host = QLineEdit('127.0.0.1')
        self.port = QLineEdit('8765')
        self.certificate = QLineEdit()
        self.certificate.setPlaceholderText('Path to the PEM certificate')
        self.key = QLineEdit()
        self.key.setPlaceholderText('Path to the PEM private key')
        self.plaintext = QCheckBox('Use HTTP behind my private TLS tunnel')
        listener_layout.addRow('Bind address', self.host)
        listener_layout.addRow('Port', self.port)
        listener_layout.addRow('TLS certificate', self.certificate)
        listener_layout.addRow('TLS private key', self.key)
        certificate_row = QHBoxLayout()
        self.create_certificate_button = QPushButton('Create cert')
        self.create_certificate_button.setToolTip(
            'Create a self-signed certificate for this private listener. The key '
            'stays on this machine and the phone pins the certificate by its '
            'fingerprint.')
        self.create_certificate_button.clicked.connect(self.create_certificate)
        certificate_row.addWidget(self.create_certificate_button)
        self.certificate_status = QLabel('')
        self.certificate_status.setWordWrap(True)
        self.certificate_status.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        certificate_row.addWidget(self.certificate_status, 1)
        listener_layout.addRow(certificate_row)
        listener_layout.addRow(self.plaintext)
        row = QHBoxLayout()
        self.start_button = QPushButton('Start listener')
        self.start_button.clicked.connect(self.start_listener)
        row.addWidget(self.start_button)
        self.stop_button = QPushButton('Stop listener')
        self.stop_button.clicked.connect(self.stop_listener)
        row.addWidget(self.stop_button)
        listener_layout.addRow(row)
        self.listener_status = QLabel('Stopped')
        self.listener_status.setWordWrap(True)
        listener_layout.addRow('Status', self.listener_status)

        pairing_box = QGroupBox('Android pairing and paired devices')
        pairing_layout = QVBoxLayout(pairing_box)
        pairing_row = QHBoxLayout()
        android_help = QLabel('Enter your private HTTPS address and the pairing secret in the Android app, then tap Pair and Refresh.')
        android_help.setWordWrap(True)
        pairing_layout.addWidget(android_help)
        self.pair_button = QPushButton('Pair Android')
        self.pair_button.clicked.connect(self.pair_device)
        pairing_row.addWidget(self.pair_button)
        pairing_layout.addLayout(pairing_row)
        self.secret_display = QPlainTextEdit()
        self.secret_display.setReadOnly(True)
        self.secret_display.setMaximumHeight(80)
        self.secret_display.setMinimumHeight(64)
        self.secret_display.setPlaceholderText(
            'The shared secret of a newly paired phone is shown here once. '
            'Transfer it to the phone and it is never displayed again.')
        pairing_layout.addWidget(self.secret_display)
        self.devices = QTableWidget(0, 3)
        self.devices.setMinimumHeight(125)
        self.devices.setHorizontalHeaderLabels(['Key id', 'Label', 'State'])
        self.devices.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.devices.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.devices.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        pairing_layout.addWidget(self.devices)
        self.revoke_button = QPushButton('Revoke the selected phone')
        self.revoke_button.clicked.connect(self.revoke_device)
        pairing_layout.addWidget(self.revoke_button)

        code_box = QGroupBox('Pairing code for the iPhone')
        code_layout = QFormLayout(code_box)
        iphone_help = QLabel('Open your private HTTPS remote URL in Safari. Use the code below to pair, then refresh PC status.')
        iphone_help.setWordWrap(True)
        code_layout.addRow(iphone_help)
        self.phone_address = QLineEdit()
        self.phone_address.setPlaceholderText(
            'The HTTPS address the phone reaches this PC on, for example '
            'https://pc.example.lan:8765')
        code_layout.addRow('Address for the phone', self.phone_address)
        self.phone_key = QLineEdit(IPHONE_KEY_ID)
        code_layout.addRow('Device key id', self.phone_key)
        code_row = QHBoxLayout()
        self.pair_iphone_button = QPushButton('Pair iPhone')
        self.pair_iphone_button.clicked.connect(self.pair_iphone)
        code_row.addWidget(self.pair_iphone_button)
        self.code_button = QPushButton('Show code')
        self.code_button.clicked.connect(self.show_pairing_code)
        code_row.addWidget(self.code_button)
        code_layout.addRow(code_row)
        self.code_qr = QLabel()
        self.code_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_qr.setMinimumHeight(180)
        self.code_qr.hide()
        code_layout.addRow(self.code_qr)
        self.code_fingerprint = QLabel('')
        self.code_fingerprint.setWordWrap(True)
        self.code_fingerprint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        code_layout.addRow('Certificate', self.code_fingerprint)
        self.code_text = QPlainTextEdit()
        self.code_text.setReadOnly(True)
        self.code_text.setMaximumHeight(110)
        self.code_text.setMinimumHeight(75)
        self.code_text.setPlaceholderText(
            'The pairing code appears here. It holds a one time secret, so it '
            'is shown only once.')
        code_layout.addRow(self.code_text)

        chat_box = QGroupBox('Chat and memory for paired devices')
        chat_layout = QFormLayout(chat_box)
        self.chat_provider = QComboBox()
        for name, spec in specs().items():
            self.chat_provider.addItem(name + (' (local)' if spec.local else ''), name)
        chat_layout.addRow('Provider for the phone', self.chat_provider)
        self.chat_paid = QCheckBox('Allow paid AI for paired phones')
        self.chat_paid.setToolTip('Provider charges may apply.')
        chat_layout.addRow(self.chat_paid)
        self.chat_memory = QCheckBox('Allow paired phones to sync memory')
        chat_layout.addRow(self.chat_memory)
        chat_row = QHBoxLayout()
        self.chat_save_button = QPushButton('Save the bridge settings')
        self.chat_save_button.clicked.connect(self.save_chat_settings)
        chat_row.addWidget(self.chat_save_button)
        chat_layout.addRow(chat_row)
        chat_note = QLabel(
            'A paired phone sends a message to this PC and the PC answers with '
            'the provider key it already holds. The phone never holds a key. '
            'Paid providers may charge and need consent on the phone.')
        chat_note.setWordWrap(True)
        chat_layout.addRow(chat_note)

        jobs_box = QGroupBox('Jobs from a phone')
        jobs_layout = QVBoxLayout(jobs_box)
        self.jobs = QTableWidget(0, 4)
        self.jobs.setMinimumHeight(145)
        self.jobs.setHorizontalHeaderLabels(['Job', 'Title', 'State', 'Needs approval'])
        self.jobs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        jobs_layout.addWidget(self.jobs)
        job_row = QHBoxLayout()
        self.approve_button = QPushButton('Approve job')
        self.approve_button.clicked.connect(self.approve_job)
        job_row.addWidget(self.approve_button)
        self.reject_button = QPushButton('Reject job')
        self.reject_button.clicked.connect(self.reject_job)
        job_row.addWidget(self.reject_button)
        jobs_layout.addLayout(job_row)
        for label, panels in (
            ('Set up iPhone', (code_box,)),
            ('Set up Android', (pairing_box,)),
            ('Advanced connection', (listener_box, chat_box)),
            ('Job approvals', (jobs_box,)),
        ):
            content = QWidget()
            column = QVBoxLayout(content)
            column.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            for panel in panels:
                column.addWidget(panel)
            column.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(content)
            tabs.addTab(scroll, label)

    # ---------------------------------------------------------------- actions

    def start_listener(self):
        def operation():
            try:
                port = int(self.port.text().strip() or '0')
            except ValueError:
                raise ValueError('Enter a valid port number.') from None
            config = ListenerConfig(
                host=self.host.text().strip() or '127.0.0.1',
                port=port,
                tls_cert=self.certificate.text().strip(),
                tls_key=self.key.text().strip(),
                allow_plaintext=self.plaintext.isChecked(),
                allowed_hosts=('127.0.0.1', '::1'),
            )
            self.listener._config = config
            address = self.listener.start()
            self.refresh()
            return 'Bridge listener started on ' + address
        self.notify(operation)

    def create_certificate(self):
        """Create a certificate for the private listener when there is none."""
        def operation():
            cert = self.certificate.text().strip()
            key = self.key.text().strip()
            if not cert or not key:
                raise ValueError('Give the certificate and key a place first.')
            digest = ensure_certificate(cert, key)
            self.certificate_status.setText('SHA-256 ' + _readable(digest))
            self.certificate_status.setToolTip(digest)
            return ('Certificate ready. Its SHA-256 fingerprint is ' + digest +
                    '. The pairing code carries it, so the phone pins this exact '
                    'certificate.')
        self.notify(operation)

    def stop_listener(self):
        def operation():
            self.listener.stop()
            self.refresh()
            return 'Bridge listener stopped.'
        self.notify(operation)

    def pair_device(self):
        def operation():
            pairing = self.pairing.pair(key_id=KEY_ID, label='phone')
            self.secret_display.setPlainText(pairing.secret)
            self.refresh()
            return ('Phone paired. Copy the shared secret below into the phone. '
                    'It is shown once and stored only in the Windows vault.')
        self.notify(operation)

    def pair_iphone(self):
        """Pair an iPhone under its own key id and show its pairing code."""
        def operation():
            key_id = self.phone_key.text().strip() or IPHONE_KEY_ID
            pairing = self.pairing.pair(key_id=key_id, label='iphone')
            self.secret_display.setPlainText(pairing.secret)
            self.refresh()
            return ('iPhone paired as ' + key_id + '. Show the pairing code and '
                    'scan it with the phone.')
        self.notify(operation)

    def show_pairing_code(self):
        """Build the pairing code and draw it as a QR code."""
        def operation():
            address = self.phone_address.text().strip()
            key_id = self.phone_key.text().strip() or IPHONE_KEY_ID
            secret = self.pairing.secret_for(key_id)
            if not secret:
                raise ValueError('Pair this phone first, then show the pairing code.')
            digest = ''
            cert = self.certificate.text().strip()
            if cert:
                try:
                    digest = fingerprint_from_file(cert)
                except CertificateError:
                    digest = ''
            payload = pairing_payload(address, key_id, secret,
                                      expires_at(lifetime_seconds=DEFAULT_LIFETIME_SECONDS),
                                      fingerprint=digest)
            self.code_text.setPlainText(payload)
            self.code_fingerprint.setText(
                'SHA-256 ' + _readable(digest) if digest else
                'No certificate is set, so the code carries no fingerprint.')
            self.code_fingerprint.setToolTip(digest)
            self._draw_qr(payload)
            if self.chat is not None:
                self.chat.configure(self.chat_provider.currentData(),
                                    paid_consent=self.chat_paid.isChecked(),
                                    memory_sync=self.chat_memory.isChecked())
            return ('Pairing code ready. Scan it with the iPhone, or copy the '
                    'text. The secret in it stops working in '
                    f'{DEFAULT_LIFETIME_SECONDS // 60} minutes.')
        self.notify(operation)

    def _draw_qr(self, payload):
        """Draw the pairing code as a picture."""
        self.code_qr.show()
        try:
            svg = pairing_svg(payload)
        except Exception as error:
            self.code_qr.setText('The pairing code could not be drawn: ' + str(error))
            return
        renderer = QSvgRenderer(bytearray(svg.encode('utf-8')))
        picture = QPixmap(240, 240)
        picture.fill()
        renderer.render(picture)
        self.code_qr.setPixmap(picture)

    def save_chat_settings(self):
        """Record what the owner allowed for the paired devices."""
        def operation():
            if self.chat is None:
                raise ValueError('No provider router is available for the bridge.')
            self.chat.configure(self.chat_provider.currentData(),
                                paid_consent=self.chat_paid.isChecked(),
                                memory_sync=self.chat_memory.isChecked())
            return 'The bridge settings were saved.'
        self.notify(operation)

    def revoke_device(self):
        def operation():
            row = self.devices.currentRow()
            item = self.devices.item(row, 0) if row >= 0 else None
            if item is None:
                raise ValueError('Select a paired phone first.')
            key_id = item.text()
            if not self.confirm(Action('revoke_bridge_device', key_id)):
                return
            self.pairing.revoke(key_id)
            self.refresh()
            return 'Phone revoked. Its next request is refused.'
        self.notify(operation)

    def approve_job(self):
        def operation():
            job = self._selected_job()
            if job.state in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED'):
                raise ValueError('That job has already finished.')
            action = Action('approve_bridge_job', job.id,
                            job.title + ' / ' + job.kind)
            result = self.gateway.run(action, self.confirm,
                                      lambda: self.bridge.jobs.approve(job.id))
            self.refresh()
            return 'Job approved: ' + str(result.state)
        self.notify(operation)

    def reject_job(self):
        def operation():
            job = self._selected_job()
            if not self.confirm(Action('reject_bridge_job', job.id, job.title)):
                return
            self.bridge.jobs.cancel(job.id)
            self.refresh()
            return 'Job rejected.'
        self.notify(operation)

    def _selected_job(self):
        row = self.jobs.currentRow()
        item = self.jobs.item(row, 0) if row >= 0 else None
        if item is None:
            raise ValueError('Select a job first.')
        job = self.bridge.jobs.get(item.text())
        if job is None:
            raise ValueError('That job is no longer known.')
        return job

    # --------------------------------------------------------------- refresh

    def refresh(self):
        if self.chat is not None:
            provider = self.chat.provider
            if provider:
                index = self.chat_provider.findData(provider)
                if index >= 0:
                    self.chat_provider.setCurrentIndex(index)
            self.chat_paid.setChecked(self.chat.paid_consent)
            self.chat_memory.setChecked(self.chat.memory_sync)
        running = self.listener.running
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self.listener_status.setText('Listening on ' + self.listener.address)
        else:
            self.listener_status.setText('Stopped')

        self.devices.setRowCount(0)
        for device in self.pairing.devices():
            row = self.devices.rowCount()
            self.devices.insertRow(row)
            self.devices.setItem(row, 0, QTableWidgetItem(device.key_id))
            self.devices.setItem(row, 1, QTableWidgetItem(device.label))
            self.devices.setItem(row, 2, QTableWidgetItem(
                'revoked' if device.revoked else 'active'))

        self.jobs.setRowCount(0)
        for job in self.bridge.jobs.list():
            row = self.jobs.rowCount()
            self.jobs.insertRow(row)
            self.jobs.setItem(row, 0, QTableWidgetItem(job.id))
            self.jobs.setItem(row, 1, QTableWidgetItem(job.title))
            self.jobs.setItem(row, 2, QTableWidgetItem(job.state))
            self.jobs.setItem(row, 3, QTableWidgetItem('yes' if job.requires_approval else 'no'))
