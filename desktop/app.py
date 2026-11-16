import os
from pathlib import Path
import sys
import uuid
import time
from datetime import datetime, timezone

from PySide6.QtCore import QProcess, QThread, Signal, QTimer, Qt, QLockFile, QUrl, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QStackedWidget, QPlainTextEdit, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QDialog, QFileDialog, QScrollArea, QLayout, QGridLayout,
    QProgressBar, QGroupBox,
)
from core.store import Store
from quantum_core.studio_project import STUDIO_URL, studio_update_prompt, validate_studio_url
from desktop.memory_page import MemoryPanel
from memory.memory_service import MemoryService
from desktop.bridge_panel import BridgePanel
from desktop.camera_reader import open_camera_reader
from desktop.update_dialog import ReleaseChecker, open_updates
from desktop.voice_panel import VoicePanel
from desktop.tray import BackgroundControls
from desktop.personal_theme import PERSONAL_STYLE
from desktop.blue_orb import BlueOrb
from desktop.system_metrics import CpuSampler, snapshot, format_snapshot
from desktop.network_diagnostics import NetworkDiagnostics
from desktop.network_metrics import NetworkSampler, format_network
from desktop.voice_commands import parse_voice_command
from desktop.task_routing import match_task
from desktop.video_export import AfterEffectsInputs, PreviewInputs, VideoExportWorker
from video_studio.after_effects import after_effects_render
from video_studio.after_effects_timeline import timeline_executable, timeline_script
from video_studio.capcut import export_capcut
from video_studio.preview import media_tools, render_preview
from security.policy import Policy, Action, Stopped
from security.vault import Vault
from providers.chat import ProviderError, TransientProviderError
from providers.registry import provider_names
from providers.router import ProviderRouter
from providers.stream_fallback import StreamTarget, stream_with_fallback, FallbackBlocked
from automation.windows import APPS, launch_app
from automation.inspection import inspect_windows
from developer_studio.workspace import Workspace
from developer_studio.codex_cli import codex_executable, run_codex
from developer_studio.generation import messages_for_goal, messages_for_repair, prepare_draft
from video_studio.planning import (
    VIDEO_ENGINES, english_srt, flow_instructions, parse_plan, plan_json,
    planning_messages, spoken_brief, suggest_workflow,
)
from business.site_preview import LANGUAGES, WebsiteExport
from business.drafting import TASKS as BUSINESS_TASKS, draft_messages, spoken_business_request
from agents.gateway import Gateway
from agents.queue import TaskQueue
from agents.workflows import WorkflowQueue

STYLE = PERSONAL_STYLE


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
        self.memory_service = MemoryService(self.root / 'history.sqlite3')
        self.router = ProviderRouter()
        self.policy = Policy()
        self.vault = Vault()
        self.gateway = Gateway(self.policy, self.store)
        self.queue = TaskQueue(self.store, self.gateway)
        self.workflows = WorkflowQueue(self.store, self.gateway)
        self.worker_kind = "chat"
        self.ai_visual_state = "idle"
        self.active_provider = None
        self.active_model = None
        self.workspace = Workspace(self.root / 'workspace')
        self.video_plan = None
        self.site_export = None
        self.site_draft = None
        self.site_preview_path = None
        self.worker = None
        self.close_when_done = False
        self.session = self.store.get('session') or uuid.uuid4().hex
        self.store.set('session', self.session)
        self.chat_task = None
        self.chat_ticket = None
        self.voice_rearm_timer = QTimer(self)
        self.voice_rearm_timer.setSingleShot(True)
        self.voice_rearm_timer.timeout.connect(self.rearm_local_voice)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        header = QHBoxLayout()
        brand = QLabel('JARVIS AI')
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
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(174)
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
        self.voice_panel.cycle_finished.connect(self.schedule_local_voice_rearm)
        self.voice_panel.speech_finished.connect(self.schedule_local_voice_rearm)
        self.add_page('Voice / Hey Jarvis', self.voice_panel)
        self.add_page('Phone Remote', self.bridge_page())
        self.add_page('Settings & Safety', self.permissions_page())
        self.add_page('Video Editor', self.video_page())
        self.add_page('Business', self.business_page())
        self.add_page('Memory', MemoryPanel(service=self.memory_service))
        self.add_page('Command Center', self.dashboard(), primary=False)
        self.voice_panel.activity_changed.connect(self.refresh_voice_hud)
        self.voice_panel.recognition_failed.connect(lambda: self.hands_free_voice.setChecked(False))
        self.voice_panel.feedback.connect(lambda message: self.statusBar().showMessage(message, 10000))
        self.refresh_voice_hud()
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
        self.fullscreen_shortcut = QShortcut(QKeySequence('F11'), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self.refresh_system_metrics()
        self.refresh_history()
        self.render_chat()
        self.background_controls = BackgroundControls(self)
        self.release_checker = ReleaseChecker(self)

    def add_page(self, name, page, *, primary=True):
        index = self.pages.count()
        self.page_indices[name] = index
        if name != 'Phone Remote':
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            if page.layout() is not None:
                page.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            scroller.setWidget(page)
            page = scroller
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

    def local_voice_allowed(self):
        """Hands-free calls are allowed only to local, non-billable Ollama."""
        return (
            self.hands_free_voice.isChecked()
            and not self.policy.stopped
            and self.voice_panel.consent.listening
            and self.chat_provider.currentText() == 'Ollama'
            and self.router.spec('Ollama').local
            and not self.backup_consent.isChecked()
            and not self.close_when_done
        )

    def set_local_hands_free(self, enabled):
        """An explicit, session-only microphone and local-provider opt-in."""
        if enabled:
            busy_voice = (self.voice_panel.worker is not None
                          and self.voice_panel.worker.isRunning())
            if (self.policy.stopped or not self.voice_panel.consent.listening
                    or self.chat_provider.currentText() != 'Ollama'
                    or not self.router.spec('Ollama').local
                    or self.backup_consent.isChecked() or self.worker is not None
                    or busy_voice):
                self.hands_free_voice.blockSignals(True)
                self.hands_free_voice.setChecked(False)
                self.hands_free_voice.blockSignals(False)
                self.statusBar().showMessage(
                    'Hands-free needs allowed microphone, idle voice and Ollama selected; '
                    'cloud providers and backups are not supported.', 20000)
                return
            # The user opted in to the local dialogue session. No cloud key
            # is read; no other provider can be used for automatic messages.
            self.read_replies.setChecked(True)
            self.voice_panel.stop_continuous()
            self.voice_panel.listen('dialogue')
            self.statusBar().showMessage(
                'Hands-free LOCAL Ollama active. Say Hey Jarvis, then your question. '
                'Uncheck to stop; PC actions still require approval.', 20000)
        else:
            self.voice_rearm_timer.stop()
            if hasattr(self, 'voice_panel') and self.voice_panel.worker is not None:
                if self.voice_panel.worker._mode == 'dialogue':
                    self.voice_panel.cancel_listening()

    def guard_local_voice_provider(self):
        if (self.hands_free_voice.isChecked()
                and (self.chat_provider.currentText() != 'Ollama'
                     or self.backup_consent.isChecked())):
            self.hands_free_voice.setChecked(False)
            self.statusBar().showMessage(
                'Local hands-free stopped: provider or backup settings changed.', 15000)

    def schedule_local_voice_rearm(self):
        # Do not reopen the microphone while speech is still playing.
        speaking = self.voice_panel.speaker_worker
        if (self.local_voice_allowed() and self.worker is None
                and (speaking is None or not speaking.isRunning())):
            self.voice_rearm_timer.start(350)

    def rearm_local_voice(self):
        """Only listen again after the previous answer and speech have ended."""
        if not self.local_voice_allowed() or self.worker is not None:
            return
        speaking = self.voice_panel.speaker_worker
        if speaking is not None and speaking.isRunning():
            return
        current = self.voice_panel.worker
        if current is not None and current.isRunning():
            return
        self.voice_panel.listen('dialogue')

    def on_wake_detected(self, transcript, command):
        if self.policy.stopped or not self.voice_panel.consent.listening:
            return
        text = (command or '').strip()[:4000]
        if text:
            self.show_hud_text('Heard: ' + text)
        if self.answer_spoken_system_command(text) or self.route_task(text):
            return
        self.open_section('JARVIS Chat')
        if (text and self.local_voice_allowed() and self.worker is None
                and not self.prompt.toPlainText().strip()):
            # Exact opt-in, local model only: no cloud API charges, no shell
            # execution, no implicit PC action approval, no model fallback.
            self.prompt.setPlainText(text)
            self.send(allow_notes=False)
            return
        if text:
            self.on_voice_transcript(text)
        else:
            self.prompt.setFocus()
            self.statusBar().showMessage(
                'Hello! Say your request after Hey Jarvis. '
                'PC actions always need approval.', 15000)

    def on_voice_transcript(self, transcript):
        """Draft spoken text on the main screen; never automatically send."""
        if self.policy.stopped or not self.voice_panel.consent.listening:
            return
        text = (transcript or '').strip()[:4000]
        if not text:
            return
        self.show_hud_text('Heard: ' + text)
        if self.answer_spoken_system_command(text) or self.route_task(text):
            return
        self.open_section('JARVIS Chat')
        existing = self.prompt.toPlainText().strip()
        self.prompt.setPlainText((existing + '\n' if existing else '') + text)
        self.prompt.setFocus()
        self.statusBar().showMessage(
            'I heard you. Please review and press Ask JARVIS. No action ran.', 15000)

    def route_task(self, text):
        return (self.route_video_brief(text) or self.route_business_brief(text)
                or self.route_natural_task(text))

    def route_natural_task(self, text):
        task = match_task(text)
        video_commands = {
            'after_effects_render': 'render after effects',
            'after_effects_timeline': 'build after effects timeline',
            'mp4_preview': 'assemble mp4 preview',
            'capcut_export': 'export for capcut',
        }
        business_tasks = {
            'fiverr_reply': 'Fiverr client reply',
            'fiverr_gig': 'Fiverr gig',
            'fiverr_delivery': 'Fiverr delivery or revision',
            'website_draft': 'Website content update',
        }
        if task in video_commands:
            return self.route_video_brief(video_commands[task])
        if task == 'higgsfield_plan':
            return self.open_video_brief(text, engine='Higgsfield')
        if task == 'video_plan':
            engine = 'Google Flow' if 'google flow' in text.casefold() else None
            return self.open_video_brief(text, engine=engine)
        if task in business_tasks:
            return self.open_business_request(business_tasks[task], text)
        return False

    def route_video_brief(self, text):
        command = text.casefold().strip(' .!?')
        if command == 'export for capcut':
            self.open_section('Video Editor')
            self.capcut_button.setFocus()
            self.video_status.setText('Generate a shot plan, then select Export for CapCut Desktop.')
            return True
        if command in ('render after effects', 'after effects render பண்ணு'):
            self.open_section('Video Editor')
            self.after_effects_button.setFocus()
            self.video_status.setText('Select Render After Effects to set up a composition render.')
            return True
        if command in ('build after effects timeline', 'after effects timeline தயார் செய்'):
            self.open_section('Video Editor')
            self.after_effects_timeline_button.setFocus()
            self.video_status.setText('Generate a shot plan, then select Build After Effects timeline.')
            return True
        if command in ('assemble mp4 preview', 'இந்த clips-ஐ இணைத்து mp4 செய்', 'mp4 export பண்ணு'):
            self.open_section('Video Editor')
            self.video_render_button.setFocus()
            self.video_status.setText('Generate a shot plan, then select Assemble MP4 preview and choose your clips.')
            return True
        brief = spoken_brief(text)
        if brief is None:
            return False
        engine = next((name for name in VIDEO_ENGINES if name.casefold() in brief.casefold()), None)
        return self.open_video_brief(brief, engine=engine)

    def open_video_brief(self, brief, *, engine=None):
        self.open_section('Video Editor')
        if self.video_brief.isReadOnly():
            self.statusBar().showMessage('A shot plan is already generating.', 10000)
            return True
        if engine is not None:
            self.video_engine.setCurrentText(engine)
        self.video_brief.setPlainText(brief)
        self.video_brief.setFocus()
        self.video_status.setText('Review the brief and select Generate with Gemini.')
        return True

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
        page, layout = self.page('Command Center', 'Live system metrics for this computer.')
        header = QHBoxLayout()
        self.hud_clock = QLabel()
        self.hud_clock.setObjectName('hudClock')
        header.addWidget(self.hud_clock)
        header.addStretch()
        self.fullscreen_button = self.button(header, 'Full screen', self.toggle_fullscreen)
        self.fullscreen_button.setToolTip('Toggle full screen (F11)')
        layout.addLayout(header)

        voice_row = QHBoxLayout()
        self.hud_orb = BlueOrb(page)
        self.hud_orb.setFixedSize(76, 76)
        voice_row.addWidget(self.hud_orb)
        voice_details = QVBoxLayout()
        self.hud_voice_status = QLabel('STANDBY')
        self.hud_voice_status.setObjectName('hudClock')
        voice_details.addWidget(self.hud_voice_status)
        self.hud_voice_reply = QLabel()
        self.hud_voice_reply.setTextFormat(Qt.TextFormat.PlainText)
        self.hud_voice_reply.setWordWrap(True)
        self.hud_voice_reply.hide()
        voice_details.addWidget(self.hud_voice_reply)
        voice_row.addLayout(voice_details, 1)
        layout.addLayout(voice_row)
        voice_controls = QHBoxLayout()
        self.hud_talk = self.button(voice_controls, 'Talk once', self.listen_to_user)
        self.button(voice_controls, 'Voice settings', lambda: self.open_section('Voice / Hey Jarvis'))
        read_replies = QCheckBox('Read replies')
        read_replies.setChecked(self.read_replies.isChecked())
        read_replies.toggled.connect(self.read_replies.setChecked)
        self.read_replies.toggled.connect(read_replies.setChecked)
        voice_controls.addWidget(read_replies)
        layout.addLayout(voice_controls)

        meters = QHBoxLayout()
        self.hud_meters = {}
        for label, key in (('CPU', 'cpu_usage_percent'), ('RAM', 'ram_usage_percent')):
            card = QGroupBox(label)
            card_layout = QVBoxLayout(card)
            value = QLabel('Collecting…')
            value.setObjectName('hudValue')
            card_layout.addWidget(value)
            meter = QProgressBar()
            meter.setRange(0, 1000)
            meter.setTextVisible(False)
            card_layout.addWidget(meter)
            self.hud_meters[key] = (value, meter)
            meters.addWidget(card, 1)
        layout.addLayout(meters)
        self.dashboard_metrics = QLabel()
        self.dashboard_metrics.setWordWrap(True)
        self.dashboard_metrics.setObjectName('systemMetrics')
        layout.addWidget(self.dashboard_metrics)
        self.button(layout, 'Local network diagnostics', self.open_network_diagnostics)
        for name in ('Video Editor', 'Coding Assistant', 'Business', 'Phone Remote', 'Task Queue'):
            self.button(layout, name, lambda checked=False, section=name: self.open_section(section))
        self.button(layout, 'Back to JARVIS Chat',
                    lambda: self.open_section('JARVIS Chat'))
        layout.addStretch()
        return page

    def open_network_diagnostics(self):
        if not self.policy.stopped:
            dialog = NetworkDiagnostics(self)
            try:
                dialog.exec()
            finally:
                dialog.deleteLater()

    def toggle_fullscreen(self):
        self.setWindowState(self.windowState() ^ Qt.WindowState.WindowFullScreen)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.fullscreen_button.setText('Exit full screen' if self.isFullScreen() else 'Full screen')

    def refresh_system_metrics(self):
        """Refresh the HUD and cache the same snapshot for local chat commands."""
        data = snapshot(self.root, self.cpu_sampler)
        data['network_status'] = format_network(self.network_sampler.sample())
        self.system_summary = format_snapshot(data)
        self.system_metrics_label.setText(self.system_summary)
        self.dashboard_metrics.setText(self.system_summary)
        self.hud_clock.setText(datetime.now().strftime('%H:%M'))
        for key, (value, meter) in self.hud_meters.items():
            percent = data[key]
            value.setText(f'{percent:.1f}%' if percent is not None else 'Unavailable')
            meter.setVisible(percent is not None)
            if percent is not None:
                meter.setValue(round(percent * 10))

    def local_system_reply(self, text):
        command = ' '.join(text.casefold().split()).strip('?!.,')
        if command in ('time', '/time', 'current time', 'what time is it', 'what is the time', "what's the time",
                       'இப்போ நேரம் என்ன', 'நேரம்',
                       'quelle heure est-il'):
            return datetime.now().astimezone().strftime('%H:%M %Z')
        if command in ('status', '/status', 'system status', 'system stats', 'cpu', 'ram',
                       'கணினி நிலை', 'état du système'):
            phone_status = 'Running' if self.bridge.listener.running else 'Stopped'
            return f'{self.state.text()}\nPhone Remote: {phone_status}\n\n{self.system_summary}'
        return None

    def set_ai_visual_state(self, state):
        """Keep model work separate from microphone and playback activity."""
        self.ai_visual_state = state
        self.refresh_voice_hud()

    def refresh_voice_hud(self):
        if not self.voice_panel.consent.listening and self.hands_free_voice.isChecked():
            self.hands_free_voice.setChecked(False)
        if self.policy.stopped:
            state = 'stopped'
        elif self.voice_panel.speaking:
            state = 'speaking'
        elif self.ai_visual_state != 'idle':
            state = self.ai_visual_state
        elif self.voice_panel.listening:
            state = 'listening'
        else:
            state = 'idle'
        label = {
            'idle': 'STANDBY', 'listening': 'LISTENING', 'thinking': 'PROCESSING',
            'responding': 'RESPONDING', 'speaking': 'SPEAKING', 'stopped': 'STOPPED',
        }[state]
        self.orb.set_state(state)
        self.hud_orb.set_state(state)
        self.orb_status.setText('JARVIS  /  ' + label)
        self.hud_voice_status.setText(label)
        self.hud_talk.setEnabled(state not in ('stopped', 'listening', 'speaking')
                                 and not self.voice_panel.playback_busy)

    def answer_spoken_system_command(self, command):
        if self.worker is not None:
            return False
        reply = self.local_system_reply(command)
        if reply is None:
            return False
        self.show_local_system_reply(command, reply)
        return True

    def show_local_system_reply(self, command, reply):
        self.store.message(self.session, 'local command', command)
        self.store.message(self.session, 'system', reply)
        self.render_chat()
        self.refresh_archives()
        self.show_hud_text(reply)
        if self.read_replies.isChecked():
            self.voice_panel.speak_response(reply)

    def show_hud_text(self, text):
        self.hud_voice_reply.setText(text if len(text) <= 600 else text[:600] + '…')
        self.hud_voice_reply.show()

    def chat_page(self):
        page, layout = self.page('Home & Chat', 'Ask in Tamil, Tanglish, English or French.')
        hero = QHBoxLayout()
        self.orb = BlueOrb(page)
        self.orb.setFixedSize(52, 52)
        hero.addWidget(self.orb)
        details = QVBoxLayout()
        self.orb_status = QLabel('JARVIS  /  STANDBY')
        details.addWidget(self.orb_status)
        self.system_metrics_label = QLabel('SYSTEM  /  Collecting local metrics...')
        self.system_metrics_label.setWordWrap(True)
        self.system_metrics_label.setObjectName('systemMetrics')
        self.system_metrics_label.hide()
        hero.addLayout(details, 1)
        layout.addLayout(hero)
        shortcuts = QGridLayout()
        for index, (label, section) in enumerate([
            ('Video', 'Video Editor'), ('Coding', 'Coding Assistant'),
            ('Phone', 'Phone Remote'), ('Camera', 'PC Control'),
            ('Commands', 'Command Center'),
        ]):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, section=section: self.open_section(section))
            shortcuts.addWidget(button, index // 3, index % 3)
        layout.addLayout(shortcuts)
        row = QHBoxLayout()
        self.chat_provider = QComboBox()
        self.chat_provider.addItems(provider_names())
        self.chat_provider.setCurrentText('Gemini')
        self.chat_provider.currentTextChanged.connect(self.guard_local_voice_provider)
        row.addWidget(self.chat_provider)
        self.new_chat_button = self.button(row, 'New chat', self.new_chat)
        layout.addLayout(row)
        options = QCheckBox('Chat options')
        layout.addWidget(options)
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings.hide()
        options.toggled.connect(settings.setVisible)
        layout.addWidget(settings)
        self.backup_consent = QCheckBox('Allow one backup attempt')
        self.backup_consent.setToolTip('Shares the full conversation with the backup provider. Charges may apply.')
        self.backup_consent.toggled.connect(lambda enabled: self.guard_local_voice_provider() if enabled else None)
        settings_layout.addWidget(self.backup_consent)
        self.use_notes = QCheckBox('Include notes once')
        self.use_notes.setToolTip(
            'Send matching local notes to the selected provider and any approved backup '
            'for this message. The reply is saved in chat history.'
        )
        settings_layout.addWidget(self.use_notes)
        self.backup_provider = QComboBox()
        self.backup_provider.addItems(provider_names())
        self.backup_provider.setCurrentIndex(1)
        settings_layout.addWidget(self.backup_provider)
        archives = QHBoxLayout()
        self.archives = QComboBox()
        archives.addWidget(self.archives, 1)
        self.archive_button = self.button(archives, 'Open saved chat', self.open_chat)
        settings_layout.addLayout(archives)
        self.refresh_archives()
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setMinimumHeight(158)
        layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText('Ask JARVIS… தமிழ் / English / Français')
        self.prompt.setFixedHeight(78)
        layout.addWidget(self.prompt)
        self.read_replies = QCheckBox('Read replies aloud')
        settings_layout.addWidget(self.read_replies)
        self.hands_free_voice = QCheckBox('Hands-free Hey Jarvis')
        self.hands_free_voice.setToolTip(
            'Requires microphone permission and Ollama. Each wake phrase plus '
            'question sends a message ONLY to your local model; never to cloud '
            'providers. No PC actions run without separate approval.')
        self.hands_free_voice.toggled.connect(self.set_local_hands_free)
        settings_layout.addWidget(self.hands_free_voice)
        settings_actions = QHBoxLayout()
        settings_layout.addLayout(settings_actions)
        self.clear_button = self.button(settings_actions, 'Delete chat', self.clear_chat)
        self.review_pc_action_button = self.button(
            settings_actions, 'Review PC action', self.review_chat_pc_action)
        composer_actions = QHBoxLayout()
        layout.addLayout(composer_actions)
        self.button(composer_actions, 'Speak', self.listen_to_user)
        composer_actions.addStretch()
        self.send_button = self.button(composer_actions, 'Ask JARVIS', self.send)
        self.send_button.setObjectName('primary')
        return page

    def bridge_page(self):
        self.bridge = BridgePanel(self.policy, self.store, self.vault, self.confirm, self.notify,
                                  router=self.router)
        return self.bridge

    def automation_page(self):
        page, layout = self.page('Windows Automation',
            'Open approved apps, inspect windows, or read text from a connected camera.')
        self.app_choice = QComboBox()
        self.app_choice.addItems(APPS)
        layout.addWidget(self.app_choice)
        self.button(layout, 'Review and launch', self.launch)
        self.button(layout, 'Review visible window titles (read only)', self.inspect_visible_windows)
        self.button(layout, 'Watch & read connected camera',
                    lambda: self.notify(lambda: open_camera_reader(self)))
        layout.addStretch()
        return page

    def video_page(self):
        page, layout = self.page(
            'Video Editor',
            'Plan a 30-second vertical reel for Google Flow or Higgsfield. Say “Hey Jarvis, '
            'Video editor” followed by your brief, or type it below. '
            'Generate sends the displayed brief to Gemini and may incur API charges.')
        self.video_brief = QPlainTextEdit()
        self.video_brief.setPlaceholderText(
            'AI Mystery World episode, topic, opening shot, look, music, logo…')
        self.video_brief.setMaximumHeight(120)
        self.video_brief.textChanged.connect(self.invalidate_video_plan)
        layout.addWidget(self.video_brief)
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel('Video engine'))
        self.video_engine = QComboBox()
        self.video_engine.addItems(VIDEO_ENGINES)
        engine_row.addWidget(self.video_engine, 1)
        layout.addLayout(engine_row)
        self.video_generate_button = self.button(layout, 'Generate with Gemini', self.generate_video_plan)
        self.button(layout, 'Suggest workflow', self.show_workflow_suggestion)
        self.video_status = QLabel('Subtitle timing is estimated. Review it against the recorded voiceover.')
        self.video_status.setWordWrap(True)
        layout.addWidget(self.video_status)
        self.video_preview = QPlainTextEdit()
        self.video_preview.setReadOnly(True)
        layout.addWidget(self.video_preview, 1)
        flow_link = QLabel()
        flow_link.setOpenExternalLinks(True)
        layout.addWidget(flow_link)
        links = (
            '<a href="https://labs.google/fx/tools/flow">Open Google Flow</a>',
            '<a href="https://higgsfield.ai/">Open Higgsfield</a>',
        )
        flow_link.setText(links[0])
        self.video_engine.currentIndexChanged.connect(lambda index: flow_link.setText(links[index]))
        self.video_engine.currentIndexChanged.connect(self.invalidate_video_plan)
        row = QHBoxLayout()
        self.video_export_buttons = (
            self.button(row, 'Save shot plan (JSON)', lambda: self.save_video_draft('json')),
            self.button(row, 'Save English subtitles (SRT)', lambda: self.save_video_draft('srt')),
        )
        for button in self.video_export_buttons:
            button.setEnabled(False)
        layout.addLayout(row)
        render_row = QHBoxLayout()
        self.video_render_button = self.button(render_row, 'Assemble MP4 preview', self.assemble_video)
        self.video_render_button.setEnabled(False)
        self.capcut_button = self.button(layout, 'Export for CapCut Desktop',
                                         lambda: self.assemble_video(capcut=True))
        self.capcut_button.setEnabled(False)
        self.after_effects_button = self.button(render_row, 'Render After Effects', self.render_after_effects)
        self.video_cancel_render = self.button(render_row, 'Cancel export', self.cancel_video_export)
        self.video_cancel_render.hide()
        layout.addLayout(render_row)
        self.after_effects_timeline_button = self.button(
            layout, 'Build After Effects timeline', self.build_after_effects_timeline)
        self.after_effects_timeline_button.setEnabled(False)
        return page

    def show_workflow_suggestion(self):
        QMessageBox.information(
            self, 'Suggested video workflow',
            suggest_workflow(self.video_brief.toPlainText(), self.video_engine.currentText()),
        )

    def generate_video_plan(self):
        if self.worker is not None or self.policy.stopped:
            return

        def operation():
            engine = self.video_engine.currentText()
            messages = planning_messages(self.video_brief.toPlainText(), engine)
            provider = 'Gemini'
            spec = self.router.spec(provider)
            key = self.get_key(provider)
            model = self.store.get('model:' + provider, spec.default_model)
            self.chat_ticket = self.policy.ticket()
            self.invalidate_video_plan()
            self.video_status.setText(f'Generating a {engine} shot plan with Gemini…')
            self.start_worker(provider, model, key, messages, 'video_plan')

        self.notify(operation)

    def invalidate_video_plan(self):
        self.video_plan = None
        self.video_preview.clear()
        self.refresh_draft_buttons()

    def save_video_draft(self, extension):
        if self.video_plan is None or self.worker is not None or self.policy.stopped:
            return
        folder, plan = self.video_plan
        name = f'video-plans/{folder}/' + (
            'shot-plan.json' if extension == 'json' else 'english.srt')
        content = plan_json(plan) if extension == 'json' else english_srt(plan)
        self.notify(lambda: self.gateway.run(
            Action('save_file', name, Workspace.digest(content)),
            self.confirm, lambda: self.workspace.save(name, content)))

    def assemble_video(self, *, capcut=False):
        if self.video_plan is None or self.worker is not None or self.policy.stopped:
            return
        selection = self.video_plan
        _, plan = selection

        def operation():
            media_tools()
            dialog = PreviewInputs(plan, self, capcut=capcut)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.video_plan is not selection or self.worker is not None:
                raise ValueError('The current task changed. Open the export dialog again.')
            clips = [field.text() for field in dialog.clips]
            output = dialog.target.text()
            narration = dialog.narration.text() or None
            exporter = export_capcut if capcut else render_preview
            label = 'Preparing CapCut export…' if capcut else 'Assembling local MP4 preview…'
            self.gateway.run(
                Action('export_for_capcut' if capcut else 'start_video_preview', output), self.confirm,
                lambda: self.start_video_export(
                    output, label,
                    lambda check: exporter(plan, clips, output, check, narration=narration)))

        self.notify(operation)

    def build_after_effects_timeline(self):
        if self.video_plan is None or self.worker is not None or self.policy.stopped:
            return
        folder, plan = self.video_plan

        def operation():
            if sys.platform != 'win32':
                raise ValueError('After Effects timeline handoff requires Windows.')
            dialog = PreviewInputs(plan, self, timeline=True)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.video_plan != (folder, plan) or self.worker is not None:
                raise ValueError('The shot plan changed. Open the timeline dialog again.')
            executable = timeline_executable(dialog.target.text())
            clips = [field.text() for field in dialog.clips]
            narration = dialog.narration.text() or None
            script = timeline_script(plan, clips, narration)
            name = f'video-plans/{folder}/after-effects-timeline-{uuid.uuid4().hex}.jsx'

            def handoff():
                self.workspace.save(name, script)
                # Adobe processes -r in its open application. The dispatch does
                # not tell JARVIS whether the composition was created.
                started, _ = QProcess.startDetached(
                    str(executable), ['-r', str(self.workspace.path(name))])
                if not started:
                    raise ValueError('After Effects could not start. The timeline script was saved in the workspace.')
                return 'Timeline command sent. Check the composition in After Effects.'

            target = '\n'.join([str(executable), *clips, *([narration] if narration else [])])
            result = self.gateway.run(
                Action('build_after_effects_timeline', target, Workspace.digest(script)), self.confirm, handoff)
            self.video_status.setText(result)

        self.notify(operation)

    def render_after_effects(self):
        if self.worker is not None or self.policy.stopped:
            return

        def operation():
            dialog = AfterEffectsInputs(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            renderer, project, composition, template, output = dialog.values()
            target = f'{project}\nComposition: {composition}\nTemplate: {template}\nOutput: {output}\nRenderer: {renderer}'
            self.gateway.run(
                Action('start_after_effects_render', target), self.confirm,
                lambda: self.start_video_export(
                    output, 'Rendering After Effects composition…',
                    lambda check: after_effects_render(renderer, project, composition, template, output, check)))

        self.notify(operation)

    def start_video_export(self, output, message, operation):
        if self.worker is not None:
            raise ValueError('Wait for the current request to finish.')
        self.worker_kind = 'video_export'
        self.chat_task = self.store.task('video_export', Path(output).name)
        self.store.finish(self.chat_task, 'running')
        self.worker = VideoExportWorker(operation, self)
        self.worker.result.connect(self.on_video_export_result)
        self.worker.finished.connect(self.on_finished)
        self.video_status.setText(message)
        self.video_cancel_render.setEnabled(True)
        self.video_cancel_render.show()
        self.refresh_draft_buttons()
        self.worker.start()

    def cancel_video_export(self):
        if self.worker is not None and self.worker_kind == 'video_export':
            self.worker.requestInterruption()
            self.video_cancel_render.setEnabled(False)

    def on_video_export_result(self, status, detail):
        self.store.finish(self.chat_task, status)
        self.video_status.setText('Video saved to ' + detail if status == 'completed' else detail)
        self.refresh_history()

    def business_page(self):
        page, layout = self.page(
            'Business', 'Open AI Creative Studio in Google AI Studio or prepare a business draft. '
            'Generate business draft uses your Gemini settings.')
        website_row = QHBoxLayout()
        self.website_project_url = QLineEdit(self.store.get('website_ai_studio_url', '') or STUDIO_URL)
        self.website_project_url.setPlaceholderText('Paste your Google AI Studio project URL')
        website_row.addWidget(self.website_project_url, 1)
        self.button(website_row, 'Open in AI Studio', self.open_website_project)
        layout.addLayout(website_row)
        self.business_task = QComboBox()
        self.business_task.addItems(BUSINESS_TASKS)
        layout.addWidget(self.business_task)
        self.business_brief = QPlainTextEdit()
        self.business_brief.setPlaceholderText(
            'Describe the gig or paste the client brief. For website work, include the '
            'site name, page and requested changes.')
        layout.addWidget(self.business_brief)
        self.business_generate = self.button(layout, 'Generate business draft', self.generate_business)
        studio_row = QHBoxLayout()
        self.button(studio_row, 'Prepare site update prompt', self.prepare_website_update)
        self.business_copy = self.button(studio_row, 'Copy draft', self.copy_business_draft)
        self.business_copy.setEnabled(False)
        layout.addLayout(studio_row)
        preview_row = QHBoxLayout()
        self.site_language = QComboBox()
        for code, label in LANGUAGES.items():
            self.site_language.addItem(label, code)
        preview_row.addWidget(self.site_language)
        self.site_generate = self.button(preview_row, 'Generate website preview', self.generate_site_preview)
        layout.addLayout(preview_row)
        export_row = QHBoxLayout()
        self.site_open_preview = self.button(export_row, 'Open preview', self.open_site_preview)
        self.site_save = self.button(export_row, 'Save updated site ZIP', self.save_site_draft)
        self.site_open_preview.setEnabled(False)
        self.site_save.setEnabled(False)
        layout.addLayout(export_row)
        self.business_status = QLabel('Review and copy the draft into Fiverr or your website editor.')
        self.business_status.setWordWrap(True)
        layout.addWidget(self.business_status)
        self.business_preview = QPlainTextEdit()
        self.business_preview.setReadOnly(True)
        self.business_preview.textChanged.connect(
            lambda: self.business_copy.setEnabled(bool(self.business_preview.toPlainText().strip())))
        layout.addWidget(self.business_preview, 2)
        self.business_task.currentTextChanged.connect(self.clear_business_draft)
        self.business_brief.textChanged.connect(self.clear_business_draft)
        self.website_project_url.textChanged.connect(self.clear_business_draft)
        self.site_language.currentIndexChanged.connect(self.clear_business_draft)
        return page

    def generate_site_preview(self):
        if self.worker is not None or self.policy.stopped:
            return
        brief = self.business_brief.toPlainText().strip()
        if not brief:
            self.business_status.setText('Enter the homepage copy change to preview.')
            return
        source, _ = QFileDialog.getOpenFileName(
            self, 'Select your AI Studio website source ZIP', '', 'Website ZIP (*.zip)')
        if not source:
            return

        def operation():
            website = WebsiteExport.load(source, self.site_language.currentData())
            messages = website.messages(brief)
            provider = 'Gemini'
            model = self.store.get('model:' + provider, self.router.spec(provider).default_model)
            key = self.get_key(provider)
            self.chat_ticket = self.policy.ticket()
            self.clear_business_draft()
            self.site_export = website
            self.business_status.setText('Generating homepage copy with Gemini…')
            self.start_worker(provider, model, key, messages, 'website_preview')

        self.notify(operation)

    def store_site_preview(self, response):
        draft = self.site_export.draft(response)
        draft.updated_files()
        folder = self.root / 'website-previews'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (uuid.uuid4().hex + '.html')
        path.write_text(draft.preview_html(), encoding='utf-8')
        self.site_draft = draft
        self.site_preview_path = path
        self.business_preview.setPlainText('\n\n'.join(
            field + '\n' + value for field, value in draft.changes.items()))
        self.business_status.setText('Open the before-and-after preview, then save the updated website ZIP.')
        self.site_open_preview.setEnabled(True)
        self.site_save.setEnabled(True)

    def open_site_preview(self):
        if self.site_preview_path is not None and not self.policy.stopped:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.site_preview_path.resolve()))):
                self.business_status.setText('Could not open the browser preview.')

    def save_site_draft(self):
        if self.site_draft is None or self.policy.stopped:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, 'Save updated website source', 'AI-Creative-Studio-draft.zip', 'Website ZIP (*.zip)')
        if destination:
            self.notify(lambda: self.save_site_draft_to(destination))

    def save_site_draft_to(self, destination):
        self.site_draft.export_zip(destination)
        self.business_status.setText('Updated source ZIP saved.')
        return 'Updated source ZIP saved.'

    def open_website_project(self):
        def operation():
            self.policy.ticket()
            url = validate_studio_url(self.website_project_url.text())
            self.store.set('website_ai_studio_url', url)
            if not QDesktopServices.openUrl(QUrl(url)):
                raise ValueError('Project URL saved. Windows could not open your browser.')
            return 'AI Studio project URL saved.'

        self.notify(operation)

    def prepare_website_update(self):
        if self.business_brief.isReadOnly():
            return

        def operation():
            self.policy.ticket()
            prompt = studio_update_prompt(
                self.business_brief.toPlainText(), self.website_project_url.text())
            self.business_preview.setPlainText(prompt)
            self.business_status.setText('Copy the prompt and paste it into AI Studio Build.')
            return 'AI Studio update prompt prepared.'

        self.notify(operation)

    def copy_business_draft(self):
        if not self.policy.stopped:
            draft = self.business_preview.toPlainText()
            if draft.strip():
                QApplication.clipboard().setText(draft)
                self.statusBar().showMessage('Business draft copied.', 5000)

    def clear_business_draft(self):
        self.site_draft = None
        self.site_preview_path = None
        self.site_open_preview.setEnabled(False)
        self.site_save.setEnabled(False)
        self.business_preview.clear()
        self.business_status.setText('Review the brief and select Generate business draft.')

    def route_business_brief(self, text):
        request = spoken_business_request(text)
        if request is None:
            return False
        return self.open_business_request(*request)

    def open_business_request(self, task, brief):
        self.open_section('Business')
        if self.business_brief.isReadOnly():
            self.statusBar().showMessage('A business draft is already generating.', 10000)
            return True
        self.business_task.setCurrentText(task)
        self.business_brief.setPlainText(brief)
        self.business_brief.setFocus()
        return True

    def generate_business(self):
        if self.worker is not None or self.policy.stopped:
            return

        def operation():
            messages = draft_messages(
                self.business_task.currentText(), self.business_brief.toPlainText())
            provider = 'Gemini'
            spec = self.router.spec(provider)
            key = self.get_key(provider)
            model = self.store.get('model:' + provider, spec.default_model)
            self.chat_ticket = self.policy.ticket()
            self.clear_business_draft()
            self.business_status.setText('Generating draft with Gemini…')
            self.start_worker(provider, model, key, messages, 'business_draft')

        self.notify(operation)

    def editor_page(self):
        page, layout = self.page('Developer Studio',
            'Draft Python, repair code from an error, or ask Codex to review a project.')
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel('Coding AI'))
        self.coding_provider = QComboBox()
        self.coding_provider.addItems(['Use chat provider', 'MiniMax'])
        saved_provider = self.store.get('coding_provider')
        if saved_provider == 'MiniMax':
            self.coding_provider.setCurrentText(saved_provider)
        self.coding_provider.currentTextChanged.connect(
            lambda provider: self.store.set('coding_provider', provider))
        provider_row.addWidget(self.coding_provider, 1)
        self.button(provider_row, 'MiniMax API settings', self.open_minimax_settings)
        layout.addLayout(provider_row)
        self.code_goal = QLineEdit()
        self.code_goal.setPlaceholderText('Describe the Python program you want to create…')
        layout.addWidget(self.code_goal)
        actions = QHBoxLayout()
        self.generate_button = self.button(actions, 'Generate Python draft', self.generate_code)
        self.codex_button = self.button(actions, 'Ask Codex about a project', self.ask_codex)
        layout.addLayout(actions)
        self.code_status = QLabel('Enter a task to generate a draft, or paste an error below to repair the editor code.')
        self.code_status.setWordWrap(True)
        layout.addWidget(self.code_status)
        self.code_error = QPlainTextEdit()
        self.code_error.setPlaceholderText('Paste the Python error here. Remove keys and private data before sharing.')
        self.code_error.setMaximumHeight(70)
        layout.addWidget(self.code_error)
        self.repair_button = self.button(layout, 'Draft a code fix', self.repair_code)
        self.code_preview = QPlainTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setMaximumHeight(160)
        layout.addWidget(self.code_preview)
        self.codex_response = QPlainTextEdit()
        self.codex_response.setReadOnly(True)
        self.codex_response.setPlaceholderText('Codex project response')
        self.codex_response.hide()
        layout.addWidget(self.codex_response, 1)
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

    def open_minimax_settings(self):
        self.provider.setCurrentText('MiniMax')
        self.open_section('AI Providers')
        self.secret.setFocus()

    def selected_coding_provider(self):
        choice = self.coding_provider.currentText()
        return self.chat_provider.currentText() if choice == 'Use chat provider' else choice

    def coding_key(self, provider):
        try:
            return self.get_key(provider)
        except ValueError:
            if provider != 'MiniMax':
                raise
            raise ValueError('Open MiniMax API settings and save your MiniMax key, then retry.') from None

    def ask_codex(self):
        if self.worker is not None or self.policy.stopped:
            return

        def operation():
            ticket = self.policy.ticket()
            prompt = self.code_goal.text().strip()
            if not prompt or len(prompt) > 12_000:
                raise ValueError('Enter a coding request of 1–12,000 characters.')
            executable = codex_executable()
            selected = QFileDialog.getExistingDirectory(self, 'Select the project Codex can inspect')
            if not selected:
                return
            project = Path(selected).resolve(strict=True)
            self.policy.check(ticket)
            if self.worker is not None:
                return
            action = Action('codex_project_review',
                            f'{project}\n\nCodex can read project context for this request.\n\n{prompt}')

            def start():
                if self.worker is not None:
                    raise ValueError('Wait for the current task to finish.')
                self.chat_ticket = ticket
                self.worker_kind = 'codex_review'
                self.active_provider = None
                self.chat_task = self.store.task('codex_review', 'Codex CLI project review')
                self.store.finish(self.chat_task, 'running')
                self.codex_response.clear()
                self.codex_response.show()
                self.code_status.setText('Codex is reviewing the project…')
                self.worker = VideoExportWorker(
                    lambda check: run_codex(executable, project, prompt, check), self)
                self.worker.result.connect(self.on_codex_result)
                self.worker.finished.connect(self.on_finished)
                self.refresh_draft_buttons()
                self.set_ai_visual_state('thinking')
                self.worker.start()

            if self.confirm(action):
                self.policy.check(ticket)
                start()

        self.notify(operation)

    def on_codex_result(self, status, response):
        try:
            self.policy.check(self.chat_ticket)
        except Stopped:
            status, response = 'cancelled', 'Codex review cancelled by Emergency Stop.'
        self.store.finish(self.chat_task, status)
        if status == 'completed':
            self.codex_response.setPlainText(response)
            self.code_status.setText('Codex review ready.')
        else:
            self.code_status.setText('Codex review cancelled.' if status == 'cancelled' else response)
        self.refresh_history()

    def generate_code(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            messages = messages_for_goal(self.code_goal.text())
            provider = self.selected_coding_provider()
            model = self.store.get('model:' + provider) or self.router.spec(provider).default_model
            key = self.coding_key(provider)
            if not self.confirm(Action('send_coding_goal', provider + ' / ' + model + ' (API charges may apply)')):
                return
            self.policy.check(ticket)
            self.chat_ticket = ticket
            self.code_preview.clear()
            self.code_status.setText(f'{provider} is drafting your code…')
            self.start_worker(provider, model, key, messages, 'code_generation')
        self.notify(operation)

    def repair_code(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            messages = messages_for_repair(self.editor.toPlainText(), self.code_error.toPlainText())
            provider = self.selected_coding_provider()
            model = self.store.get('model:' + provider) or self.router.spec(provider).default_model
            key = self.coding_key(provider)
            action = Action('send_editor_code_and_error',
                            provider + ' / ' + model + ' (shares editor code and pasted error; API charges may apply)',
                            Workspace.digest(messages[-1]['content']))
            if not self.confirm(action):
                return
            self.policy.check(ticket)
            self.chat_ticket = ticket
            self.code_preview.clear()
            self.code_status.setText(f'{provider} is drafting a fix for review…')
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
        self.refresh_draft_buttons()
        if kind == 'video_plan':
            self.video_brief.setReadOnly(True)
        if kind in ('business_draft', 'website_preview'):
            self.business_brief.setReadOnly(True)
            self.business_task.setEnabled(False)
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

    def review_chat_pc_action(self):
        """Turn only an exact, allowlisted instruction into an approval request.

        This is a deterministic local parser, not a model-to-shell bridge.
        Unrecognized instructions are refused. No PC action occurs without
        the same one-use approval dialog used by the PC Control page.
        """
        if self.policy.stopped:
            return
        name = parse_voice_command(self.prompt.toPlainText())
        if name not in APPS:
            self.statusBar().showMessage(
                'No action ran. Say: open notepad or open calculator '
                '(Tamil phrases also supported).', 15000)
            return
        self.notify(lambda: self.gateway.run(
            Action('launch_app', name), self.confirm, lambda: launch_app(name)))

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

    def send(self, *, allow_notes=True):
        if self.policy.stopped or self.worker is not None or not self.prompt.toPlainText().strip():
            return
        text = self.prompt.toPlainText().strip()
        use_notes = allow_notes and self.use_notes.isChecked()
        if allow_notes:
            self.use_notes.setChecked(False)
        local_reply = self.local_system_reply(text)
        if local_reply is not None:
            self.prompt.clear()
            self.show_local_system_reply(text, local_reply)
            return
        if self.route_task(text):
            self.prompt.clear()
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
            messages = [message for message in self.store.messages(self.session)
                        if message['role'] in ('user', 'assistant')]
            messages.append({'role': 'user', 'content': prompt})
            notes = self.memory_service.as_context(prompt) if use_notes else ''
            if notes:
                messages[-1]['content'] = (
                    prompt + '\n\nRelated notes from my local memory, for reference only:\n' + notes
                )
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
        if self.ai_visual_state == 'thinking':
            self.set_ai_visual_state('responding')
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
        elif self.worker_kind == 'video_plan':
            if status == 'completed':
                try:
                    plan = parse_plan(text)
                except ValueError as error:
                    status = 'failed'
                    self.video_status.setText(str(error) + ' Try generating again.')
                else:
                    plan['engine'] = self.video_engine.currentText()
                    self.video_plan = uuid.uuid4().hex, plan
                    self.video_preview.setPlainText(flow_instructions(plan))
                    self.video_status.setText(
                        'Shot plan ready. Verify historical details and sync captions to the recorded voiceover.')
            else:
                self.video_status.setText(status + ': ' + text)
        elif self.worker_kind == 'website_preview':
            if status == 'completed':
                try:
                    self.store_site_preview(text)
                except (OSError, ValueError) as error:
                    status = 'failed'
                    self.business_status.setText(str(error))
            else:
                self.business_status.setText(status + ': ' + text)
        elif self.worker_kind == 'business_draft':
            if status == 'completed' and text.strip():
                self.business_preview.setPlainText(text.strip())
                self.business_status.setText('Draft ready to review and copy.')
            elif status == 'completed':
                status = 'failed'
                self.business_status.setText('Gemini returned an empty draft. Try again.')
            else:
                self.business_status.setText(status + ': ' + text)
        elif self.worker_kind == 'chat':
            if status == 'completed':
                self.store.message(self.session, 'assistant', text)
                self.show_hud_text(text)
                if self.read_replies.isChecked() and not self.policy.stopped:
                    self.voice_panel.speak_response(text[:600])
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
        self.video_cancel_render.hide()
        self.video_brief.setReadOnly(False)
        self.business_brief.setReadOnly(False)
        self.business_task.setEnabled(True)
        self.refresh_draft_buttons()
        self.set_ai_visual_state('stopped' if self.policy.stopped else 'idle')
        for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button, self.repair_button):
            button.setEnabled(not self.policy.stopped)
        self.chat_provider.setEnabled(True)
        self.backup_provider.setEnabled(True)
        self.backup_consent.setEnabled(True)
        self.schedule_local_voice_rearm()
        if self.close_when_done:
            self.close()

    def refresh_draft_buttons(self):
        ready = not self.policy.stopped and self.worker is None
        self.codex_button.setEnabled(ready)
        self.coding_provider.setEnabled(ready)
        self.video_generate_button.setEnabled(ready)
        self.video_engine.setEnabled(ready)
        self.business_generate.setEnabled(ready)
        self.site_generate.setEnabled(ready)
        self.site_language.setEnabled(ready)
        self.site_open_preview.setEnabled(ready and self.site_preview_path is not None)
        self.site_save.setEnabled(ready and self.site_draft is not None)
        for button in self.video_export_buttons:
            button.setEnabled(ready and self.video_plan is not None)
        self.video_render_button.setEnabled(ready and self.video_plan is not None)
        self.capcut_button.setEnabled(ready and self.video_plan is not None)
        self.after_effects_button.setEnabled(ready)
        self.after_effects_timeline_button.setEnabled(ready and self.video_plan is not None)

    def stop(self):
        self.policy.stop()
        self.refresh_draft_buttons()
        self.voice_rearm_timer.stop()
        self.hands_free_voice.setChecked(False)
        self.voice_panel.stop_voice()
        self.set_ai_visual_state('stopped')
        self.queue.cancel_pending()
        self.workflows.cancel_pending()
        if self.worker:
            self.worker.requestInterruption()
        self.state.setText('● STOPPED')
        self.resume_button.setEnabled(True)
        self.send_button.setEnabled(False)
        self.review_pc_action_button.setEnabled(False)
        ident = self.store.task('emergency_stop', 'All outstanding approvals invalidated')
        self.store.finish(ident, 'completed')
        self.statusBar().showMessage('STOPPED. No new actions. In-flight network reads may need up to 30 seconds.')
        self.refresh_history()

    def resume(self):
        self.policy.resume()
        self.refresh_draft_buttons()
        self.set_ai_visual_state('idle' if self.worker is None else 'thinking')
        self.resume_button.setEnabled(False)
        self.state.setText('● READY · MANUAL APPROVAL')
        if self.worker is None:
            for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button, self.repair_button):
                button.setEnabled(True)
        self.review_pc_action_button.setEnabled(True)

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
            self.statusBar().showMessage('Waiting for the current task to exit safely…')
            event.ignore()
        else:
            self.voice_rearm_timer.stop()
            self.hands_free_voice.setChecked(False)
            self.voice_panel.stop_voice()
            self.voice_panel.wait_for_workers()
            self.bridge.listener.stop()
            event.accept()


def voice_runtime_smoke_test():
    """Validate packaged Windows speech imports without a microphone or AI key.

    This is a packaging check, not proof that the user's speech language pack
    or physical microphone works. No audio is captured and nothing is spoken.
    """
    if sys.platform != 'win32':
        return 21
    # Distinct exit codes reveal *which dependency stage* failed without
    # printing private paths, credentials, or raw COM exception details.
    try:
        import clr
    except Exception:
        return 31
    try:
        from voice.windows_stt import load_system_speech
        load_system_speech()
    except Exception:
        return 32
    try:
        from System.Speech.Recognition import Grammar
    except Exception:
        return 33
    try:
        import win32com.client
    except Exception:
        return 34
    try:
        voice = win32com.client.Dispatch('SAPI.SpVoice')
    except Exception:
        return 35
    return 0 if Grammar is not None and voice is not None else 36


def launch_arguments(argv):
    """Strip the explicit offline smoke flag before invoking Qt."""
    smoke = '--smoke-test' in argv[1:]
    return [arg for arg in argv if arg != '--smoke-test'], smoke


def main():
    args, smoke = launch_arguments(sys.argv)
    if '--check-voice-runtime' in args[1:]:
        return voice_runtime_smoke_test()
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
