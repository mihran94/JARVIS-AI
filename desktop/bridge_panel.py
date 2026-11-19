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

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QLayout, QSizePolicy,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from agents.gateway import Gateway
from desktop.bridge_chat import BridgeChatService
from desktop.bridge_pairing import (
    DEFAULT_LIFETIME_SECONDS, PairingCodeError, expires_at, pairing_payload, pairing_svg,
)
from desktop.bridge_status import PlatformMetrics
from providers.registry import specs
from remote import certificate
from remote.listener import BridgeListener, ListenerConfig, ListenerError
from remote.pairing import PairingStore
from remote.protocol import KEY_ID
from remote.secrets import VaultSecrets
from remote.server import BridgeServer
from security.policy import Action

#: The key id an iPhone uses. It is different from the Android one, so that
#: revoking one phone does not affect the other.
IPHONE_KEY_ID = 'jarvis-iphone-v1'


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
        self.certificate.textChanged.connect(self.refresh_fingerprint)
        self.plaintext = QCheckBox('Use HTTP behind my private TLS tunnel')
        listener_layout.addRow('Bind address', self.host)
        listener_layout.addRow('Port', self.port)
        listener_layout.addRow('TLS certificate', self.certificate)
        listener_layout.addRow('TLS private key', self.key)
        self.create_certificate_button = QPushButton('Create a private certificate')
        self.create_certificate_button.setToolTip(
            'Make a self-signed certificate for this PC. The phone pins it by '
            'fingerprint, so it does not need a certificate authority. The key '
            'stays on this computer.')
        self.create_certificate_button.clicked.connect(self.create_certificate)
        # A long label on a button sets a wide minimum on the whole tab, and a
        # tab that asks for more width than the window has asks to scroll
        # sideways. The button keeps its natural width whenever there is room
        # and gives some of it back when there is not.
        self.create_certificate_button.setMinimumWidth(60)
        self.create_certificate_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        listener_layout.addRow('Certificate', self.create_certificate_button)
        self.fingerprint_label = QLabel('')
        self.fingerprint_label.setWordWrap(True)
        self.fingerprint_label.setMinimumWidth(0)
        self.fingerprint_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        listener_layout.addRow('Fingerprint', self.fingerprint_label)
        self.peer_hosts = QLineEdit()
        self.peer_hosts.setMinimumWidth(60)
        self.peer_hosts.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.peer_hosts.setPlaceholderText(
            'Extra peer addresses, separated by commas')
        self.peer_hosts.setToolTip(
            'The addresses a phone may reach this PC from, for example the '
            'address of your VPN or private tunnel. The loopback addresses '
            'are always allowed.')
        listener_layout.addRow('Allowed peer addresses', self.peer_hosts)
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
        self.pair_iphone_button = QPushButton('Pair this iPhone')
        self.pair_iphone_button.clicked.connect(self.pair_iphone)
        # Two buttons side by side set a wide minimum on the whole row. On a
        # machine whose default font is wider, that minimum was larger than
        # the tab, so the tab asked for sideways scrolling. The buttons keep
        # their natural width whenever there is room and shrink only when
        # there is not.
        self.pair_iphone_button.setMinimumWidth(60)
        code_row.addWidget(self.pair_iphone_button)
        self.code_button = QPushButton('Show the pairing code')
        self.code_button.clicked.connect(self.show_pairing_code)
        self.code_button.setMinimumWidth(60)
        code_row.addWidget(self.code_button)
        code_layout.addRow(code_row)
        self.code_qr = QLabel()
        self.code_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_qr.setMinimumHeight(180)
        self.code_qr.hide()
        code_layout.addRow(self.code_qr)
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

    def create_certificate(self):
        """Make a self-signed certificate for the private listener.

        The key is written with owner-only permissions and never leaves
        this computer. The phone pins the certificate by its fingerprint,
        so it does not have to be signed by a certificate authority.
        """
        def operation():
            folder = self.store.path.parent / 'bridge'
            cert_path = folder / 'bridge-cert.pem'
            key_path = folder / 'bridge-key.pem'
            try:
                pin = certificate.ensure_certificate(str(cert_path), str(key_path))
            except certificate.CertificateError as error:
                raise ValueError(str(error)) from None
            self.certificate.setText(str(cert_path))
            self.key.setText(str(key_path))
            self.refresh_fingerprint()
            return ('A private certificate was created. Its SHA-256 fingerprint is '
                    'shown next to the certificate, and it travels in the pairing '
                    'code so the phone pins exactly this certificate.')
        self.notify(operation)

    def refresh_fingerprint(self):
        """Show the fingerprint of the certificate the owner chose."""
        if not hasattr(self, 'fingerprint_label'):
            return
        path = self.certificate.text().strip()
        if not path:
            self.fingerprint_label.setText('No certificate chosen yet.')
            return
        try:
            self.fingerprint_label.setText(certificate.describe(path))
        except (OSError, certificate.CertificateError) as error:
            self.fingerprint_label.setText('The certificate could not be read: ' + str(error))

    def allowed_peer_hosts(self):
        """The extra peer addresses the owner allowed, as a tuple."""
        raw = self.peer_hosts.text() if hasattr(self, 'peer_hosts') else ''
        return tuple(part.strip() for part in raw.replace(';', ',').split(',')
                     if part.strip())

    def start_listener(self):
        def operation():
            try:
                port = int(self.port.text().strip() or '0')
            except ValueError:
                raise ValueError('Enter a valid port number.') from None
            peers = self.allowed_peer_hosts()
            config = ListenerConfig(
                host=self.host.text().strip() or '127.0.0.1',
                port=port,
                tls_cert=self.certificate.text().strip(),
                tls_key=self.key.text().strip(),
                allow_plaintext=self.plaintext.isChecked(),
                allowed_hosts=('127.0.0.1', '::1') + peers,
            )
            self.listener._config = config
            # The peer list lives on the bridge, so a request from an
            # allowed VPN or tunnel peer is not refused.
            self.bridge.set_allowed_hosts(peers)
            address = self.listener.start()
            self.refresh()
            return 'Bridge listener started on ' + address
        self.notify(operation)

    def stop_listener(self):
        def operation():
            self.listener.stop()
            self.refresh()
            return 'Bridge listener stopped.'
        self.notify(operation)

    def pair_device(self):
        def operation():
            pairing = self.pairing.pair(key_id=KEY_ID, label='phone',
                                        expires_epoch_ms=self._pairing_deadline())
            self.secret_display.setPlainText(pairing.secret)
            self.refresh()
            return ('Phone paired. Copy the shared secret below into the phone. '
                    'It is shown once and stored only in the Windows vault.')
        self.notify(operation)

    def pair_iphone(self):
        """Pair an iPhone under its own key id and show its pairing code."""
        def operation():
            key_id = self.phone_key.text().strip() or IPHONE_KEY_ID
            pairing = self.pairing.pair(key_id=key_id, label='iphone',
                                        expires_epoch_ms=self._pairing_deadline())
            self.secret_display.setPlainText(pairing.secret)
            self.refresh()
            return ('iPhone paired as ' + key_id + '. Show the pairing code and '
                    'scan it with the phone.')
        self.notify(operation)

    def _pairing_deadline(self) -> int:
        """The moment a pairing code stops being usable, in milliseconds."""
        return expires_at(lifetime_seconds=DEFAULT_LIFETIME_SECONDS) * 1000

    def show_pairing_code(self):
        """Build the pairing code and draw it as a QR code."""
        def operation():
            address = self.phone_address.text().strip()
            key_id = self.phone_key.text().strip() or IPHONE_KEY_ID
            # Asking for the code again means the owner is about to put it
            # on the phone, so the deadline moves with it, and the record
            # and the code carry the same moment.
            expires_ms = self.pairing.extend_deadline(key_id, self._pairing_deadline())
            secret = self.pairing.secret_for(key_id)
            if not secret:
                raise ValueError('Pair this phone first, then show the pairing code.')
            payload = pairing_payload(address, key_id, secret,
                                      expires_ms // 1000,
                                      fingerprint=self.certificate_fingerprint())
            self.code_text.setPlainText(payload)
            self._draw_qr(payload)
            if self.chat is not None:
                self.chat.configure(self.chat_provider.currentData(),
                                    paid_consent=self.chat_paid.isChecked(),
                                    memory_sync=self.chat_memory.isChecked())
            return ('Pairing code ready. Scan it with the iPhone, or copy the '
                    'text. If the phone has not paired with it in '
                    f'{DEFAULT_LIFETIME_SECONDS // 60} minutes, the secret in it '
                    'stops working.')
        self.notify(operation)

    def certificate_fingerprint(self):
        """The fingerprint of the chosen certificate, or '' when there is none.

        A code without a fingerprint still pairs, but the phone then
        trusts whatever certificate the bridge presents, so the owner is
        told which case they are in.
        """
        path = self.certificate.text().strip()
        if not path:
            return ''
        try:
            return certificate.fingerprint_from_file(path)
        except (OSError, certificate.CertificateError):
            return ''

    def _draw_qr(self, payload):
        """Draw the pairing code as a picture."""
        self.code_qr.show()
        try:
            svg = pairing_svg(payload)
        except Exception as error:
            self.code_qr.setText('The pairing code could not be drawn: ' + str(error))
            return
        renderer = QSvgRenderer(bytearray(svg.encode('utf-8')))
        if not renderer.isValid():
            self.code_qr.setText('The pairing code could not be drawn: '
                                  'the picture was not understood.')
            return
        picture = QPixmap(240, 240)
        picture.fill()
        # Qt draws an SVG through a painter. Rendering straight into a
        # pixmap was removed from PySide6, so the pairing code never
        # reached the phone because the drawing raised instead.
        painter = QPainter(picture)
        try:
            renderer.render(painter, QRectF(0, 0, 240, 240))
        finally:
            painter.end()
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
        self.refresh_fingerprint()
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
