import os
from pathlib import Path
import sys
import uuid
import time
from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QLockFile
from PySide6.QtGui import QFont, QTextCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QStackedWidget, QPlainTextEdit, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox,
)
from core.store import Store
from desktop.bridge_panel import BridgePanel
from desktop.update_dialog import open_updates
from desktop.voice_panel import VoicePanel
from desktop.tray import BackgroundControls
from desktop.blue_theme import FUTURISTIC_BLUE
from desktop.blue_orb import BlueOrb
from desktop.system_metrics import CpuSampler, snapshot, format_snapshot
from desktop.network_metrics import NetworkSampler, format_network
from security.policy import Policy, Action, Stopped
from security.vault import Vault
from providers.chat import ProviderError, TransientProviderError
from providers.registry import provider_names
from providers.router import ProviderRouter
from providers.stream_fallback import StreamTarget, stream_with_fallback, FallbackBlocked
from automation.windows import APPS, launch_app
from automation.inspection import inspect_windows
from developer_studio.workspace import Workspace
from developer_studio.generation import messages_for_goal, messages_for_repair, prepare_draft
from agents.gateway import Gateway
from agents.queue import TaskQueue
from agents.workflows import WorkflowQueue

STYLE = """
QWidget { background:#0a101c; color:#dce9f9; font-family:'Segoe UI'; font-size:14px; }
QMainWindow { background:#0a101c; }
QLabel#title { font-size:29px; font-weight:700; color:#65d9ff; }
QLabel#subtitle { color:#839ab5; font-size:13px; }
QPushButton { background:#153047; border:1px solid #285675; border-radius:7px; padding:10px 15px; }
QPushButton:hover { background:#214a66; }
QPushButton:disabled { color:#536478; background:#14202d; }
QPushButton#stop { background:#6d2035; border:1px solid #f16c85; font-weight:700; }
QPlainTextEdit, QLineEdit, QComboBox, QTableWidget {
 background:#101c2d; border:1px solid #263b54; border-radius:6px; padding:8px; selection-background-color:#235c85;
}
QListWidget { background:#0e1828; border:0; padding:10px; min-width:210px; }
QListWidget::item { padding:16px 8px; margin:3px 0; }
QListWidget::item:selected { background:#17344c; color:#65d9ff; border-radius:6px; }
QHeaderView::section { background:#183047; padding:9px; border:0; }
"""
# One visual theme for the unified desktop; the existing owner-controlled
# voice, mobile bridge and provider routing remain the same application.
STYLE = FUTURISTIC_BLUE


class ChatWorker(QThread):
    chunk = Signal(str)
    result = Signal(str, str, object)

    def __init__(self, router, provider, model, key, messages, policy, ticket, backup=None):
        super().__init__()
        self.router, self.provider, self.model, self.key = router, provider, model, key
        self.messages, self.policy, self.ticket = messages, policy, ticket
        self.backup = backup

    def check(self):
        self.policy.check(self.ticket)
        if self.isInterruptionRequested():
            raise Stopped('Chat cancelled.')

    def run(self):
        metrics = {'provider': self.provider, 'model': self.model}
        started = time.monotonic()
        try:
            def attempt(provider, model, key, messages, check, emit):
                metrics.clear()
                metrics.update(provider=provider, model=model)
                return self.router.stream(self.router.spec(provider), model, key, messages,
                                          check, emit, metrics=metrics)
            if self.backup is None:
                answer = attempt(self.provider, self.model, self.key, self.messages,
                                 self.check, self.chunk.emit)
            else:
                _, answer = stream_with_fallback(
                    StreamTarget(self.provider, self.model, self.key), self.backup,
                    self.messages, self.check, self.chunk.emit, attempt,
                    consent_to_backup=True, retryable_errors=(TransientProviderError,))
            status, text = 'completed', answer
        except Stopped:
            status, text = 'cancelled', 'Chat cancelled. Partial output was not added to model context.'
        except (ProviderError, FallbackBlocked) as error:
            status, text = 'failed', str(error)
        except Exception:
            status, text = 'failed', 'Unexpected provider failure. No credentials were logged.'
        finally:
            self.key = ''
            self.backup = None
        metrics['duration_ms'] = round((time.monotonic() - started) * 1000)
        self.result.emit(status, text, metrics)


class Window(QMainWindow):
    def __init__(self, data_root):
        super().__init__()
        self.setWindowTitle('JARVIS AI • Your Windows Assistant')
        self.resize(1180, 790)
        self.root = Path(data_root)
        self.store = Store(self.root / 'history.sqlite3')
        self.router = ProviderRouter()
        self.policy = Policy()
        self.vault = Vault()
        self.gateway = Gateway(self.policy, self.store)
        self.queue = TaskQueue(self.store, self.gateway)
        self.workflows = WorkflowQueue(self.store, self.gateway)
        self.worker_kind = "chat"
        self.active_provider = None
        self.active_model = None
        self.workspace = Workspace(self.root / 'workspace')
        self.worker = None
        self.close_when_done = False
        self.session = self.store.get('session') or uuid.uuid4().hex
        self.store.set('session', self.session)
        self.chat_task = None
        self.chat_ticket = None

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        header = QHBoxLayout()
        brand = QLabel('J A R V I S   /   AI')
        brand.setObjectName('title')
        header.addWidget(brand)
        header.addStretch()
        self.state = QLabel('● READY · MANUAL APPROVAL')
        header.addWidget(self.state)
        self.resume_button = QPushButton('Resume')
        self.resume_button.clicked.connect(self.resume)
        self.resume_button.setEnabled(False)
        header.addWidget(self.resume_button)
        stop = QPushButton('EMERGENCY STOP')
        stop.setObjectName('stop')
        stop.clicked.connect(self.stop)
        header.addWidget(stop)
        outer.addLayout(header)
        subtitle = QLabel('YOUR WINDOWS ASSISTANT   /   PC ACTIONS NEED YOUR APPROVAL   /   PHONE IS A REMOTE')
        subtitle.setObjectName('subtitle')
        outer.addWidget(subtitle)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setMaximumWidth(250)
        self.pages = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        # One main UI: specialized tools remain available under Settings.
        self.page_indices = {}
        self.add_page('JARVIS Chat', self.chat_page())
        self.add_page('PC Control', self.automation_page())
        self.add_page('Coding Assistant', self.editor_page())
        self.voice_panel = VoicePanel()
        self.voice_panel.wake_detected.connect(self.on_wake_detected)
        self.voice_panel.utterance_detected.connect(self.on_voice_transcript)
        self.add_page('Voice / Hey Jarvis', self.voice_panel)
        self.add_page('Phone Remote', self.bridge_page())
        self.add_page('Settings & Safety', self.permissions_page())
        self.add_page('Command Center', self.dashboard(), primary=False)
        self.add_page('Task Queue', self.queue_page(), primary=False)
        self.add_page('Step Workflows', self.workflow_page(), primary=False)
        self.add_page('Task History', self.history_page(), primary=False)
        self.add_page('AI Providers', self.provider_page(), primary=False)
        self.add_page('System & Usage', self.usage_page(), primary=False)
        self.nav.currentRowChanged.connect(self.show_primary_page)
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage('Local history • Bridge listener is off by default • Keys configured on your PC')
        self.shortcut = QShortcut(QKeySequence('Ctrl+Alt+J'), self)
        self.shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut.activated.connect(self.stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_history)
        self.timer.start(1500)
        self.cpu_sampler = CpuSampler()
        self.network_sampler = NetworkSampler()
        self.system_timer = QTimer(self)
        self.system_timer.setInterval(5000)
        self.system_timer.timeout.connect(self.refresh_system_metrics)
        self.system_timer.start()
        self.refresh_system_metrics()
        self.refresh_history()
        self.render_chat()
        self.background_controls = BackgroundControls(self)

    def add_page(self, name, page, *, primary=True):
        index = self.pages.count()
        self.page_indices[name] = index
        self.pages.addWidget(page)
        if primary:
            self.nav.addItem(name)
            self.nav.item(self.nav.count() - 1).setData(
                Qt.ItemDataRole.UserRole, index)

    def show_primary_page(self, row):
        item = self.nav.item(row)
        if item is not None:
            self.pages.setCurrentIndex(item.data(Qt.ItemDataRole.UserRole))

    def open_section(self, name):
        index = self.page_indices[name]
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.ItemDataRole.UserRole) == index:
                self.nav.setCurrentRow(row)
                break
        self.pages.setCurrentIndex(index)

    def on_wake_detected(self, transcript, command):
        # Wake phrase recognition is not permission to spend API credits or
        # execute Windows actions. Only populate a human-reviewable draft.
        if self.policy.stopped or not self.voice_panel.consent.listening:
            return
        if command:
            self.on_voice_transcript(command)
        else:
            self.open_section('JARVIS Chat')
            self.prompt.setFocus()
            self.statusBar().showMessage(
                'Hello! I am listening. Say what you need, then review your message.', 15000)

    def on_voice_transcript(self, transcript):
        """Draft spoken text on the main screen; never automatically send."""
        if self.policy.stopped or not self.voice_panel.consent.listening:
            return
        text = (transcript or '').strip()[:4000]
        if not text:
            return
        self.open_section('JARVIS Chat')
        existing = self.prompt.toPlainText().strip()
        self.prompt.setPlainText((existing + '\n' if existing else '') + text)
        self.prompt.setFocus()
        self.statusBar().showMessage(
            'I heard you. Please review and press Ask JARVIS. No action ran.', 15000)

    def listen_to_user(self):
        """One click in Chat; microphone permission always belongs to Voice."""
        if self.policy.stopped:
            return
        if not self.voice_panel.consent.listening:
            self.open_section('Voice / Hey Jarvis')
            self.statusBar().showMessage(
                'Turn on Allow the microphone, then choose Talk once.', 15000)
            return
        self.voice_panel.listen('once')

    def page(self, title, note=''):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 10, 10)
        label = QLabel(title)
        label.setStyleSheet('font-size:24px;font-weight:600')
        layout.addWidget(label)
        if note:
            label = QLabel(note)
            label.setWordWrap(True)
            layout.addWidget(label)
        return page, layout

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def dashboard(self):
        page, layout = self.page('System overview',
            'JARVIS runs on your Windows PC. The phone is only a remote.')
        self.button(layout, 'Back to JARVIS Chat',
                    lambda: self.open_section('JARVIS Chat'))
        layout.addStretch()
        return page

    def refresh_system_metrics(self):
        """Read-only hardware counters; never opens a network connection."""
        if hasattr(self, 'system_metrics_label'):
            try:
                data = snapshot(self.root, self.cpu_sampler)
                data['network_status'] = format_network(self.network_sampler.sample())
                self.system_metrics_label.setText(format_snapshot(data))
            except (OSError, ValueError):
                self.system_metrics_label.setText('System metrics unavailable.')

    def set_ai_visual_state(self, state):
        """Show actual chat worker activity, not microphone or AI permissions."""
        if hasattr(self, 'orb'):
            self.orb.set_state(state)
            self.orb_status.setText('AI STATUS  /  ' + state.upper())

    def chat_page(self):
        page, layout = self.page('Hello! I am JARVIS.',
            'Chat in Tamil, English or French. I help with coding and '
            'supervised Windows tasks. You decide which actions run.')
        hero = QHBoxLayout()
        self.orb = BlueOrb(page)
        self.orb.setMaximumHeight(145)
        hero.addWidget(self.orb)
        details = QVBoxLayout()
        self.orb_status = QLabel('AI STATUS  /  IDLE')
        details.addWidget(self.orb_status)
        self.system_metrics_label = QLabel('SYSTEM  /  Collecting local metrics...')
        self.system_metrics_label.setWordWrap(True)
        self.system_metrics_label.setObjectName('systemMetrics')
        details.addWidget(self.system_metrics_label)
        hero.addLayout(details, 1)
        layout.addLayout(hero)
        shortcuts = QHBoxLayout()
        for label, section in [('PC Control', 'PC Control'),
                               ('Coding', 'Coding Assistant'),
                               ('Talk', 'Voice / Hey Jarvis'),
                               ('Phone Remote', 'Phone Remote')]:
            self.button(shortcuts, label,
                        lambda checked=False, section=section: self.open_section(section))
        self.button(shortcuts, 'Speak to JARVIS', self.listen_to_user)
        layout.addLayout(shortcuts)
        row = QHBoxLayout()
        self.chat_provider = QComboBox()
        self.chat_provider.addItems(provider_names())
        row.addWidget(self.chat_provider)
        self.new_chat_button = self.button(row, 'New chat', self.new_chat)
        self.clear_button = self.button(row, 'Delete this conversation', self.clear_chat)
        layout.addLayout(row)
        self.backup_consent = QCheckBox('Allow one backup attempt for this message (shares full conversation; charges may apply)')
        layout.addWidget(self.backup_consent)
        self.backup_provider = QComboBox()
        self.backup_provider.addItems(provider_names())
        self.backup_provider.setCurrentIndex(1)
        layout.addWidget(self.backup_provider)
        archives = QHBoxLayout()
        self.archives = QComboBox()
        archives.addWidget(self.archives, 1)
        self.archive_button = self.button(archives, 'Open saved chat', self.open_chat)
        layout.addLayout(archives)
        self.refresh_archives()
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText('Ask JARVIS… தமிழ் / English / Français')
        self.prompt.setMaximumHeight(120)
        layout.addWidget(self.prompt)
        self.read_replies = QCheckBox('Read replies aloud on this PC (optional; uses Windows speech)')
        layout.addWidget(self.read_replies)
        self.send_button = self.button(layout, 'Ask JARVIS', self.send)
        return page

    def bridge_page(self):
        self.bridge = BridgePanel(self.policy, self.store, self.vault, self.confirm, self.notify,
                                  router=self.router)
        return self.bridge

    def automation_page(self):
        page, layout = self.page('Windows Automation',
            'Fixed allowlisted applications only. Each launch requires approval. No arbitrary shell or AI command execution.')
        self.app_choice = QComboBox()
        self.app_choice.addItems(APPS)
        layout.addWidget(self.app_choice)
        self.button(layout, 'Review and launch', self.launch)
        self.button(layout, 'Review visible window titles (read only)', self.inspect_visible_windows)
        layout.addStretch()
        return page

    def editor_page(self):
        page, layout = self.page('Developer Studio',
            'Local UTF-8 editor. Code is never executed. Saves need approval; overwritten contents are retained in .revisions.')
        self.code_goal = QLineEdit()
        self.code_goal.setPlaceholderText('Describe the Python program you want to create…')
        layout.addWidget(self.code_goal)
        self.generate_button = self.button(layout, 'Generate Python draft with selected chat provider', self.generate_code)
        self.code_status = QLabel('Generate sends your task. Repair sends editor code and pasted error after approval.')
        self.code_status.setWordWrap(True)
        layout.addWidget(self.code_status)
        self.code_error = QPlainTextEdit()
        self.code_error.setPlaceholderText('Paste the Python error here. Remove keys and private data before sharing.')
        self.code_error.setMaximumHeight(70)
        layout.addWidget(self.code_error)
        self.repair_button = self.button(layout, 'Review and request code repair', self.repair_code)
        self.code_preview = QPlainTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setMaximumHeight(160)
        layout.addWidget(self.code_preview)
        self.button(layout, 'Review and copy draft to editor', self.apply_code_draft)
        self.filename = QLineEdit('hello.py')
        layout.addWidget(self.filename)
        row = QHBoxLayout()
        self.button(row, 'Open workspace file', self.open_file)
        self.button(row, 'Review and save', self.save_file)
        self.button(row, 'Check Python syntax', self.check_syntax)
        layout.addLayout(row)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont('Consolas', 12))
        self.editor.setPlainText('# Your code stays local until you choose to share it.\nprint("Hello, Mihran!")\n')
        layout.addWidget(self.editor, 1)
        location = QLabel('Workspace: ' + str(self.workspace.root))
        location.setWordWrap(True)
        layout.addWidget(location)
        return page

    def generate_code(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            messages = messages_for_goal(self.code_goal.text())
            provider = self.chat_provider.currentText()
            model = self.store.get('model:' + provider) or self.router.spec(provider).default_model
            key = self.get_key(provider)
            if not self.confirm(Action('send_coding_goal', provider + ' / ' + model + ' (API charges may apply)')):
                return
            self.policy.check(ticket)
            self.chat_ticket = ticket
            self.code_preview.clear()
            self.code_status.setText('Generating draft… Emergency stop cancels this request.')
            self.start_worker(provider, model, key, messages, 'code_generation')
        self.notify(operation)

    def repair_code(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            messages = messages_for_repair(self.editor.toPlainText(), self.code_error.toPlainText())
            provider = self.chat_provider.currentText()
            model = self.store.get('model:' + provider) or self.router.spec(provider).default_model
            key = self.get_key(provider)
            action = Action('send_editor_code_and_error',
                            provider + ' / ' + model + ' (shares editor code and pasted error; API charges may apply)',
                            Workspace.digest(messages[-1]['content']))
            if not self.confirm(action):
                return
            self.policy.check(ticket)
            self.chat_ticket = ticket
            self.code_preview.clear()
            self.code_status.setText('Requesting repair… Editor remains unchanged until you approve replacement.')
            self.start_worker(provider, model, key, messages, 'code_repair')
        self.notify(operation)

    def apply_code_draft(self):
        def operation():
            draft = self.code_preview.toPlainText()
            if not draft:
                raise ValueError('Generate a complete draft first.')
            action = Action('replace_editor_with_draft', self.filename.text(), Workspace.digest(draft))
            def apply():
                self.editor.setPlainText(draft)
                self.editor.document().setModified(True)
                return 'Draft copied to editor. Review and save separately.'
            return self.gateway.run(action, self.confirm, apply)
        self.notify(operation)

    def history_page(self):
        page, layout = self.page('Task History', 'Latest 200 actions. Full history is retained in the local SQLite database.')
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(['Created (UTC)', 'Action', 'Status', 'Details'])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history)
        return page

    def provider_page(self):
        page, layout = self.page('API Provider Manager',
            'Keys are stored only in Windows Credential Manager. Leave the key blank to retain it. '
            'Choose a provider and enter only your key. A model is preselected; Advanced settings are optional. '
            'OpenRouter routes requests to downstream providers. Claude uses the Anthropic Messages API. '
            'Ollama runs on this computer, needs no key and never reaches the network.')
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItems(provider_names())
        self.model = QLineEdit()
        self.model.setPlaceholderText("Enter the exact model ID from your provider account")
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText('Enter key locally; never paste it in chat')
        self.endpoint = QLabel()
        self.endpoint.setWordWrap(True)
        self.key_status = QLabel()
        form.addRow('Provider', self.provider)
        form.addRow('API key', self.secret)
        form.addRow('Credential status', self.key_status)
        layout.addLayout(form)
        self.advanced_provider = QCheckBox('Advanced settings (optional)')
        layout.addWidget(self.advanced_provider)
        self.provider_advanced_panel = QWidget()
        advanced_form = QFormLayout(self.provider_advanced_panel)
        advanced_form.addRow('Model ID', self.model)
        advanced_form.addRow('HTTPS endpoint', self.endpoint)
        self.button(advanced_form, 'Use recommended model', self.reset_provider_model)
        layout.addWidget(self.provider_advanced_panel)
        self.provider_advanced_panel.hide()
        self.advanced_provider.toggled.connect(self.provider_advanced_panel.setVisible)
        self.button(layout, 'Save API key', self.save_provider)
        self.button(layout, 'Remove stored key', self.remove_key)
        self.probe_button = self.button(layout, 'Test saved provider connection (uses API)', self.test_connection)
        self.provider_health = QLabel()
        self.provider_health.setWordWrap(True)
        layout.addWidget(self.provider_health)
        self.provider.currentTextChanged.connect(self.load_provider)
        self.load_provider()
        layout.addStretch()
        return page

    def queue_page(self):
        page, layout = self.page('Agent Task Queue',
            'Prepare app-launch jobs now. Select a job and review it to run once. '
            'No background execution, automatic retry, or approval after restart.')
        row = QHBoxLayout()
        self.queue_app = QComboBox()
        self.queue_app.addItems(APPS)
        row.addWidget(self.queue_app)
        self.button(row, 'Add to queue', self.enqueue)
        self.button(row, 'Review and run selected', self.run_queued)
        self.button(row, 'Cancel selected', self.cancel_queued)
        layout.addLayout(row)
        self.jobs_table = QTableWidget(0, 4)
        self.jobs_table.setHorizontalHeaderLabels(['Created (UTC)', 'Application', 'Status', 'Details'])
        self.jobs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.jobs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.jobs_table)
        return page


    def workflow_page(self):
        page, layout = self.page('Step Workflows',
            'Create 1–10 manual Notepad/Calculator steps separated by commas. '
            'Every step requires a new approval. Failed or interrupted runs never restart.')
        row = QHBoxLayout()
        self.workflow_apps = QLineEdit()
        self.workflow_apps.setPlaceholderText('Notepad, Calculator, Notepad')
        row.addWidget(self.workflow_apps, 1)
        self.button(row, 'Create workflow', self.add_workflow)
        layout.addLayout(row)
        actions = QHBoxLayout()
        self.button(actions, 'Review and run selected', self.run_workflow)
        self.button(actions, 'Cancel selected', self.cancel_workflow)
        layout.addLayout(actions)
        self.workflow_table = QTableWidget(0, 4)
        self.workflow_table.setHorizontalHeaderLabels(['Created (UTC)', 'Steps', 'Status', 'Details'])
        self.workflow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.workflow_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.workflow_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.workflow_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.workflow_table)
        return page

    def selected_workflow(self):
        row = self.workflow_table.currentRow()
        item = self.workflow_table.item(row, 0) if row >= 0 else None
        if item is None:
            raise ValueError('Select a workflow first.')
        return item.data(Qt.ItemDataRole.UserRole)

    def add_workflow(self):
        def operation():
            items = [item.strip() for item in self.workflow_apps.text().split(',')]
            ident = self.workflows.add(items)
            self.workflow_apps.clear()
            return 'Workflow created: ' + ident[:8] + '. It will not start without approval.'
        self.notify(operation)

    def run_workflow(self):
        self.notify(lambda: self.workflows.run(self.selected_workflow(), self.confirm))

    def cancel_workflow(self):
        self.notify(lambda: 'Workflow cancelled.' if self.workflows.cancel(self.selected_workflow())
                    else 'Only waiting/reviewing workflows can be cancelled.')

    def inspect_visible_windows(self):
        def operation():
            def observation():
                windows = inspect_windows()
                visible = windows[:12]
                lines = [f"{item['title']} (PID {item['pid']})" for item in visible]
                if len(windows) > len(visible):
                    lines.append(f'...and {len(windows) - len(visible)} more windows')
                return '\n'.join(lines) or 'No visible titled windows were found.'
            details = self.gateway.run(
                Action('inspect_visible_windows', 'Read visible window titles and process IDs'),
                self.confirm, observation)
            QMessageBox.information(self, 'Visible windows (read only)', details)
            return 'Window inspection completed. No windows were controlled.'
        self.notify(operation)

    def selected_job(self):
        row = self.jobs_table.currentRow()
        item = self.jobs_table.item(row, 0) if row >= 0 else None
        if not item:
            raise ValueError('Select a queued job first.')
        return item.data(Qt.ItemDataRole.UserRole)

    def enqueue(self):
        def operation():
            self.queue.add(self.queue_app.currentText())
            return 'Job queued. Review and approve it when ready.'
        self.notify(operation)

    def run_queued(self):
        self.notify(lambda: self.queue.run(self.selected_job(), self.confirm))

    def cancel_queued(self):
        self.notify(lambda: 'Job cancelled.' if self.queue.cancel(self.selected_job())
                    else 'Only queued jobs awaiting approval can be cancelled.')

    def usage_page(self):
        page, layout = self.page('Usage & Health',
            'Latest 200 API attempts. Token counts come from provider responses. '
            'Unknown does not mean zero or free. Check your provider dashboard for billed costs. '
            'Duration is the local request time; checks are user-triggered, never background probes.')
        self.usage_table = QTableWidget(0, 7)
        self.usage_table.setHorizontalHeaderLabels(
            ['Provider / Model', 'Status', 'Seconds', 'Input', 'Output', 'Total', 'Created (UTC)'])
        self.usage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.usage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.usage_table)
        return page

    def refresh_archives(self):
        self.archives.clear()
        for row in self.store.sessions():
            title = row['title'] or 'Conversation'
            self.archives.addItem(title + ' · ' + row['session'][:8], row['session'])
        index = self.archives.findData(self.session)
        if index >= 0:
            self.archives.setCurrentIndex(index)

    def open_chat(self):
        if self.worker is not None:
            return
        session = self.archives.currentData()
        if session:
            self.session = session
            self.store.set('session', session)
            self.render_chat()

    def test_connection(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            provider = self.provider.currentText()
            model = self.store.get('model:' + provider, self.router.spec(provider).default_model)
            if self.secret.text() or self.model.text().strip() != model:
                raise ValueError('Save the provider configuration before testing.')
            if not self.confirm(Action('provider_check',
                                       provider + ' / ' + model + ' — sends a short API prompt; may incur charges')):
                return
            self.policy.check(ticket)
            key = self.get_key(provider)
            self.chat_ticket = ticket
            self.start_worker(provider, model, key,
                              [{'role': 'user', 'content': 'Reply with the word OK only.'}], 'provider_check')
            return 'Testing saved provider configuration…'
        self.notify(operation)

    def get_key(self, provider):
        if self.router.spec(provider).local:
            # A local model needs no key and must never be given one.
            return ''
        try:
            key = self.vault.get(provider)
        except Exception:
            raise RuntimeError('Windows Credential Manager is unavailable.') from None
        if not key:
            raise ValueError('Add your key in API Providers first.')
        return key

    def start_worker(self, provider, model, key, messages, kind, backup=None):
        self.worker_kind = kind
        self.active_provider, self.active_model = provider, model
        self.chat_task = self.store.task(kind, provider + ' / ' + model)
        self.store.finish(self.chat_task, 'running')
        self.worker = ChatWorker(self.router, provider, model, key, messages, self.policy,
                                 self.chat_ticket,
                                 backup=backup if kind == "chat" else None)
        self.worker.chunk.connect(self.on_chunk)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.on_finished)
        for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button, self.repair_button):
            button.setEnabled(False)
        self.chat_provider.setEnabled(False)
        self.backup_provider.setEnabled(False)
        self.backup_consent.setEnabled(False)
        self.set_ai_visual_state('thinking')
        self.worker.start()

    def permissions_page(self):
        page, layout = self.page('Settings and safety',
            'Only essential tools are in the main navigation. '
            'Every computer action needs your explicit approval.')
        self.button(layout, 'Updates & rollback', lambda: open_updates(self))
        advanced = QHBoxLayout()
        for label, name in [
            ('AI providers', 'AI Providers'),
            ('Tasks', 'Task Queue'),
            ('Workflows', 'Step Workflows'),
            ('History', 'Task History'),
            ('Usage', 'System & Usage'),
        ]:
            self.button(advanced, label,
                        lambda checked=False, name=name: self.open_section(name))
        layout.addLayout(advanced)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            'ACTIVE MODE: MANUAL\n\n'
            'App launches, workflow steps, inspection and file saves require confirmation.\n'
            'Send is explicit approval to transmit this chat to the chosen provider.\n'
            'Model output and stored memory cannot grant permissions.\n'
            'No arbitrary shell execution, remote listener or plugin auto-loading.\n\n'
            'EMERGENCY STOP\n'
            'Click the red button or press Ctrl+Alt+J while JARVIS has focus.\n'
            'Blocks new actions, invalidates approvals and cancels accepting chat output.\n'
            'An in-flight network read may take up to 30 seconds to return.\n'
            'Already launched apps remain open. Already sent requests may be billed.\n'
            'Resume never restarts cancelled work.\n\n'
            'DATA\n'
            'Keys: Windows Credential Manager. Chat/history/code: local plaintext files.\n'
            'Deleting a conversation removes app records, not forensic disk remnants.\n\n'
            'NOT YET AVAILABLE\n'
            'Unrestricted desktop control, self-executing model commands, RAG,\n'
            'isolated code execution and end-to-end physical device acceptance.\n\n'
            'AVAILABLE NOW\n'
            'Eight providers including Claude and the local Ollama model. A local model\n'
            'never falls back to a paid endpoint and never leaves this computer.\n\n'
            'CURRENT: Manual workflows and read-only window title inspection.\n'
            'NEXT: Windows acceptance tests and live provider checks.\n'
            'See docs/ARCHITECTURE.md and docs/WINDOWS_ACCEPTANCE.md.'
        )
        layout.addWidget(text)
        return page

    def confirm(self, action):
        extra = ('\nContent SHA-256: ' + action.digest) if action.digest else ''
        return QMessageBox.question(self, 'Approve one action?',
            f'{action.kind}: {action.target}{extra}\n\nApprove this action once?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def notify(self, operation):
        try:
            result = operation()
            if result:
                self.statusBar().showMessage(str(result), 15000)
        except Exception as error:
            QMessageBox.warning(self, 'Action unavailable', str(error))
        self.refresh_history()

    def launch(self):
        name = self.app_choice.currentText()
        self.notify(lambda: self.gateway.run(Action('launch_app', name), self.confirm,
                                              lambda: launch_app(name)))

    def open_file(self):
        def operation():
            if self.editor.document().isModified():
                if not self.confirm(Action('discard_unsaved_editor_changes', self.filename.text())):
                    return
            self.policy.ticket()
            self.editor.setPlainText(self.workspace.read(self.filename.text()))
            self.editor.document().setModified(False)
        self.notify(operation)

    def save_file(self):
        name, content = self.filename.text(), self.editor.toPlainText()
        def operation():
            self.workspace.path(name)
            result = self.gateway.run(Action('save_file', name, Workspace.digest(content)),
                                      self.confirm, lambda: self.workspace.save(name, content))
            self.editor.document().setModified(False)
            return result
        self.notify(operation)

    def check_syntax(self):
        def operation():
            self.policy.ticket()
            return Workspace.check_python(self.editor.toPlainText())
        self.notify(operation)

    def reset_provider_model(self):
        self.model.setText(self.router.spec(self.provider.currentText()).default_model)

    def load_provider(self):
        provider = self.provider.currentText()
        spec = self.router.spec(provider)
        self.model.setText(self.store.get('model:' + provider) or spec.default_model)
        self.endpoint.setText(spec.endpoint)
        self.secret.clear()
        health = self.store.get('health:' + provider + ':' + self.model.text())
        self.provider_health.setText('Last explicit check: ' + (health['summary'] if health else 'Not tested'))
        if spec.local:
            self.key_status.setText('Not required: this model runs on this computer')
            return
        try:
            self.key_status.setText('Stored in Windows vault' if self.vault.get(provider) else 'Not configured')
        except Exception:
            self.key_status.setText('Windows vault unavailable on this system')

    def save_provider(self):
        def operation():
            self.policy.ticket()
            provider = self.provider.currentText()
            spec = self.router.spec(provider)
            model = self.model.text().strip() or spec.default_model
            if spec.local:
                if self.secret.text():
                    raise ValueError('The local model does not use an API key.')
                self.store.set('model:' + provider, model)
                self.load_provider()
                self.chat_provider.setCurrentText(provider)
                return 'Local model saved. Ready for chat; connection has not been tested.'
            if self.secret.text():
                try:
                    self.vault.put(provider, self.secret.text())
                except Exception:
                    raise RuntimeError('Could not save the key to Windows Credential Manager.') from None
                finally:
                    self.secret.clear()
            self.store.set('model:' + provider, model)
            self.load_provider()
            self.chat_provider.setCurrentText(provider)
            return 'Provider saved. Ready for chat; connection has not been tested.'
        self.notify(operation)

    def remove_key(self):
        def operation():
            self.policy.ticket()
            provider = self.provider.currentText()
            if self.confirm(Action('remove_key', provider)):
                try:
                    self.vault.delete(provider)
                except Exception:
                    raise RuntimeError('Could not remove the key from Windows Credential Manager.') from None
                self.load_provider()
        self.notify(operation)

    def render_chat(self):
        self.transcript.setPlainText('\n\n'.join(
            f'{m["role"].upper()}\n{m["content"]}' for m in self.store.messages(self.session)))
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)

    def new_chat(self):
        if self.worker is not None:
            return
        self.session = uuid.uuid4().hex
        self.store.set('session', self.session)
        self.render_chat()
        self.refresh_archives()
        self.statusBar().showMessage('New conversation. Open older conversations from the saved chat list.')

    def clear_chat(self):
        if self.worker is not None:
            return
        if self.confirm(Action('delete_conversation', self.session)):
            self.store.clear_messages(self.session)
            self.render_chat()
            self.refresh_archives()

    def send(self):
        if self.worker is not None or not self.prompt.toPlainText().strip():
            return
        def operation():
            self.chat_ticket = self.policy.ticket()
            provider = self.chat_provider.currentText()
            key = self.get_key(provider)
            model = self.store.get('model:' + provider, self.router.spec(provider).default_model)
            backup = None
            if self.backup_consent.isChecked():
                name = self.backup_provider.currentText()
                if name == provider:
                    raise ValueError('Choose a different backup provider.')
                if self.router.spec(provider).local:
                    # A local model never falls through to a paid cloud provider.
                    raise ValueError('The local model never falls back to a cloud provider.')
                backup = StreamTarget(name, self.store.get('model:' + name, self.router.spec(name).default_model),
                                      self.get_key(name))
            prompt = self.prompt.toPlainText().strip()
            messages = self.store.messages(self.session) + [{'role': 'user', 'content': prompt}]
            if sum(len(m['content']) for m in messages) > 90000:
                raise ValueError('Conversation is too long. Start a new chat.')
            self.store.message(self.session, 'user', prompt)
            self.render_chat()
            self.transcript.appendPlainText('\nJARVIS\n')
            self.prompt.clear()
            system = {'role': 'system', 'content':
                'You are JARVIS, a helpful assistant. Reply in the user language. '
                'You cannot execute tools or control this computer. Never claim actions were executed.'}
            self.start_worker(provider, model, key, [system] + messages, 'chat', backup=backup)
            self.backup_consent.setChecked(False)
        self.notify(operation)

    def on_chunk(self, text):
        if self.worker_kind != 'chat':
            return
        try:
            self.policy.check(self.chat_ticket)
        except Stopped:
            return
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)
        self.transcript.insertPlainText(text)

    def on_result(self, status, text, metrics=None):
        try:
            self.policy.check(self.chat_ticket)
        except Stopped:
            status, text = 'cancelled', 'Cancelled by emergency stop.'
        if self.worker_kind in ('code_generation', 'code_repair'):
            if status == 'completed':
                try:
                    draft, report = prepare_draft(text)
                    self.code_preview.setPlainText(draft)
                    self.code_status.setText(report)
                except ValueError:
                    status = 'failed'
                    self.code_status.setText('Invalid code draft. Nothing was changed.')
            else:
                self.code_status.setText(status + ': ' + text)
        elif self.worker_kind == 'chat':
            if status == 'completed':
                self.store.message(self.session, 'assistant', text)
                if self.read_replies.isChecked() and not self.policy.stopped:
                    self.voice_panel.speak_text.setText(text[:600])
                    self.voice_panel.speak()
            else:
                self.transcript.appendPlainText('\n[' + status.upper() + '] ' + text)
            self.refresh_archives()
        else:
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            summary = status + ' · ' + timestamp + ' · ' + (
                'Model returned a complete text response.' if status == 'completed' else text)
            self.store.set('health:' + self.active_provider + ':' + self.active_model,
                           {'summary': summary, 'status': status})
            self.provider_health.setText(self.active_provider + ' / ' + self.active_model + ': ' + summary)
            self.statusBar().showMessage(summary, 20000)
        self.store.finish(self.chat_task, status)
        if self.active_provider:
            actual_provider = (metrics or {}).get('provider', self.active_provider)
            actual_model = (metrics or {}).get('model', self.active_model)
            if actual_provider != self.active_provider:
                self.transcript.appendPlainText('\n[Backup attempted: ' + actual_provider + ' / ' + actual_model + ']')
            self.store.record_usage(self.chat_task, actual_provider, actual_model,
                                    status, metrics or {})
        self.refresh_history()

    def on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_ai_visual_state('stopped' if self.policy.stopped else 'idle')
        for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button, self.repair_button):
            button.setEnabled(not self.policy.stopped)
        self.chat_provider.setEnabled(True)
        self.backup_provider.setEnabled(True)
        self.backup_consent.setEnabled(True)
        if self.close_when_done:
            self.close()

    def stop(self):
        self.policy.stop()
        self.voice_panel.stop_voice()
        self.set_ai_visual_state('stopped')
        self.queue.cancel_pending()
        self.workflows.cancel_pending()
        if self.worker:
            self.worker.requestInterruption()
        self.state.setText('● STOPPED')
        self.resume_button.setEnabled(True)
        self.send_button.setEnabled(False)
        ident = self.store.task('emergency_stop', 'All outstanding approvals invalidated')
        self.store.finish(ident, 'completed')
        self.statusBar().showMessage('STOPPED. No new actions. In-flight network reads may need up to 30 seconds.')
        self.refresh_history()

    def resume(self):
        self.policy.resume()
        self.set_ai_visual_state('idle' if self.worker is None else 'thinking')
        self.resume_button.setEnabled(False)
        self.state.setText('● READY · MANUAL APPROVAL')
        if self.worker is None:
            for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button, self.repair_button):
                button.setEnabled(True)

    def refresh_history(self):
        rows = self.store.tasks()
        self.history.setRowCount(len(rows))
        for index, task in enumerate(rows):
            for column, key in enumerate(('created', 'kind', 'status', 'detail')):
                self.history.setItem(index, column, QTableWidgetItem(str(task[key])))

        selected = None
        current = self.jobs_table.currentRow()
        if current >= 0 and self.jobs_table.item(current, 0):
            selected = self.jobs_table.item(current, 0).data(Qt.ItemDataRole.UserRole)
        jobs = self.queue.rows()
        self.jobs_table.setRowCount(len(jobs))
        for index, job in enumerate(jobs):
            for column, key in enumerate(('created', 'app', 'status', 'detail')):
                item = QTableWidgetItem(str(job[key]))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job['id'])
                self.jobs_table.setItem(index, column, item)
            if job['id'] == selected:
                self.jobs_table.selectRow(index)
        workflow_selected = None
        current = self.workflow_table.currentRow()
        if current >= 0 and self.workflow_table.item(current, 0):
            workflow_selected = self.workflow_table.item(current, 0).data(Qt.ItemDataRole.UserRole)
        workflows = self.workflows.rows()
        self.workflow_table.setRowCount(len(workflows))
        for index, workflow in enumerate(workflows):
            for column, key in enumerate(('created', 'summary', 'status', 'detail')):
                item = QTableWidgetItem(str(workflow[key]))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, workflow['id'])
                self.workflow_table.setItem(index, column, item)
            if workflow['id'] == workflow_selected:
                self.workflow_table.selectRow(index)
        attempts = self.store.usage_rows()
        self.usage_table.setRowCount(len(attempts))
        for index, attempt in enumerate(attempts):
            values = [attempt['provider'] + ' / ' + attempt['model'], attempt['status'],
                      f"{attempt['duration_ms'] / 1000:.2f}",
                      *[attempt[k] if attempt[k] is not None else 'Unknown'
                        for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')],
                      attempt['created']]
            for column, value in enumerate(values):
                self.usage_table.setItem(index, column, QTableWidgetItem(str(value)))

    def closeEvent(self, event):
        if not self.close_when_done and self.editor.document().isModified():
            if not self.confirm(Action('discard_unsaved_editor_changes', self.filename.text())):
                event.ignore()
                return
        if self.worker is not None:
            self.close_when_done = True
            self.stop()
            self.statusBar().showMessage('Waiting for cancelled chat to exit safely…')
            event.ignore()
        else:
            self.voice_panel.stop_voice()
            self.bridge.listener.stop()
            event.accept()


def launch_arguments(argv):
    """Strip the explicit offline smoke flag before invoking Qt."""
    smoke = '--smoke-test' in argv[1:]
    return [arg for arg in argv if arg != '--smoke-test'], smoke


def main():
    args, smoke = launch_arguments(sys.argv)
    app = QApplication(args)
    app.setStyleSheet(STYLE)
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'JarvisAI'
    base.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(base / 'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, 'JARVIS AI', 'JARVIS is already running for this user.')
        return 1
    window = Window(base)
    window.show()
    if smoke:
        # Offline native smoke test: no provider calls or remote listener.
        def finish_smoke():
            if window.isVisible():
                app.quit()
            else:
                app.exit(10)
        QTimer.singleShot(1000, finish_smoke)
    return app.exec()
