import os
from pathlib import Path
import sys
import uuid
import time
from datetime import datetime, timezone
from hashlib import sha256

from PySide6.QtCore import QProcess, QThread, Signal, QTimer, Qt, QLockFile, QUrl, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QPushButton, QListWidget, QStackedWidget, QPlainTextEdit, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QDialog, QFileDialog, QScrollArea, QLayout,
    QProgressBar, QGroupBox, QSizePolicy, QInputDialog,
)
from dataclasses import replace

from core.store import Store
from core.conversation import (ASSISTANT_GUIDANCE, SUGGESTION_GUIDANCE,
                               addressed_request, mission_argument,
                               suggestion_argument)
from desktop.conversation_plan import (ConversationPlan, Step, extract_suggested_plan,
                                       parse_plan as parse_conversation_plan)
from desktop.browser_control import BrowserControl
from developer_studio.inspection import inspect_project
from core.assistant_capabilities import (conversation_context, summary as capability_summary,
                                       system_context as capability_context)
from quantum_core.studio_project import STUDIO_URL, studio_update_prompt, validate_studio_url
from desktop import documents
from desktop import local_commands
from desktop.document_search import search_folder, search_result_text, summary_export
from desktop.attachments import (AttachmentError, as_untrusted_context,
                                 stage_files, stage_folder)
from desktop.studio_inbox import StudioInboxDialog
from memory.memory_service import MemoryService
from desktop.bridge_panel import BridgePanel
from desktop.memory_page import MemoryPanel
from desktop.history_backup_settings import HistoryBackupPanel
from desktop.cybersecurity_panel import CybersecurityPanel
from desktop.camera_reader import open_camera_reader
from desktop.update_dialog import ReleaseChecker, open_updates
from desktop.voice_panel import VoicePanel
from desktop.azure_voice_settings import AzureVoiceSettings
from desktop.audio_test import AudioTest
from desktop.tray import BackgroundControls
from desktop.global_hotkey import DEFAULT_SHORTCUT, GlobalHotkey
from desktop.background import ImprovementWorker, SourceCheckWorker
from desktop.review_panel import ReviewPanel
from desktop.startup import (StartupError, set_start_at_signin, start_at_signin_enabled,
                             supported as startup_supported)
from core.candidates import read_candidate
from core.coding_tasks import prepared as prepared_tasks, resumable as resumable_tasks
from core.development import DevelopmentError, maintenance_goal
from core.updates import installation_root, read_state, release_path
from providers import routing
from providers import task_brain
from providers import pricing
from desktop import prime_theme
from desktop.omega_visuals import DEFAULT_THEME, THEMES as OMEGA_THEMES, theme_sheet
from desktop.blue_orb import BlueOrb
from desktop.omega import Omega
from desktop.mission_panel import MissionPanel
from desktop.mission_controller import MissionController
from desktop.system_metrics import CpuSampler, snapshot, format_snapshot
from desktop.network_diagnostics import NetworkDiagnostics
from desktop.news_panel import NewsPanel
from news.briefing import fallback_text, fetch_headlines, prompt_messages, source_text
from desktop.network_metrics import NetworkSampler, format_network
from desktop.voice_commands import parse_voice_command
from desktop.task_routing import match_task
from desktop.video_export import AfterEffectsInputs, PreviewInputs, VideoExportWorker
from video_studio.after_effects import after_effects_render
from video_studio.after_effects_timeline import timeline_executable, timeline_script
from video_studio.capcut import export_capcut
from video_studio.preview import media_tools, render_preview
from security.policy import Action, Denied, Policy, Stopped
from security.vault import Vault
from providers import profiles as profile_models
from providers.chat import ProviderError, TransientProviderError
from providers.errors import Diagnosis, FailureKind, diagnose
from providers.models import check_model
from providers.registry import provider_names
from providers.router import ProviderRouter
from providers.stream_fallback import StreamTarget, stream_with_fallback, FallbackBlocked
from automation.windows import (APPS, EDITOR_EXECUTABLES, LaunchRequest, editor_executable, launch_app,
                                launch_editor, launch_is_foreground, open_path)
from automation.organise import (OrganiseError, organise, plan_organise, plan_text,
                                 result_text)
from automation.desktop_tasks import VerifiedEdit, parse_desktop_task, target_is_foreground, type_into_target
from automation.inspection import inspect_windows
from developer_studio.workspace import Workspace
from developer_studio.codex_cli import codex_executable, run_codex
from developer_studio.editors import (
    CAPABILITY_LABELS, all_statuses, editor_from_text, editor_status, editor_names, open_project_in_editor,
)
from developer_studio.commands import HELP as COMMAND_HELP, parse_command
from developer_studio.context import (
    ConversationMemory, TaskRecord, describe_task, task_is_resumable,
)
from developer_studio.intents import (
    LANGUAGE_NAMES, CodingRequest, detect_reply_language, match_projects,
    parse_coding_request, parse_follow_up, strip_language_marker, summary_labels,
)
from developer_studio.projects import (
    SavedProject, assistant_language, configured_launchers, find_project, load_projects,
    project_status, routine_allowed, save_projects, set_assistant_language,
    set_trusted_routine, trusted_routines,
)
from developer_studio.codex_task import STEP_LABELS, TASK_STEPS, CodexTask, TaskOutcome
from developer_studio.generation import messages_for_goal, messages_for_repair, prepare_draft
from video_studio.editing import editing_checklist, export_davinci
from video_studio.planning import (
    VIDEO_ENGINES, VIDEO_TOOLS, english_srt, parse_plan, plan_json, prompt_sheet,
    planning_messages, shot_list, spoken_brief, suggest_workflow,
)
from business.site_preview import LANGUAGES, WebsiteExport
from business.drafting import (
    EDITOPRO_REPLY, TASKS as BUSINESS_TASKS, draft_messages, parse_editopro_reply,
    spoken_business_request,
)
from agents.gateway import Gateway
from agents.queue import TaskQueue
from agents.workflows import WorkflowQueue

#: The stylesheet the application uses. It is the premium dark interface
#: theme, and it is applied to the running application at startup — the
#: stylesheet was previously only ever applied by the tests, so the shipping
#: JARVIS rendered in the default light Qt theme.
STYLE = prime_theme.PRIME_DARK


class ChatWorker(QThread):
    chunk = Signal(str)
    result = Signal(str, str, object)

    def __init__(self, router, provider, model, key, messages, policy, ticket, backup=None, news_region=None):
        super().__init__()
        self.router, self.provider, self.model, self.key = router, provider, model, key
        self.messages, self.policy, self.ticket = messages, policy, ticket
        self.backup = backup
        self.news_region = news_region

    def check(self):
        self.policy.check(self.ticket)
        if self.isInterruptionRequested():
            raise Stopped('Chat cancelled.')

    def run_news(self, metrics):
        headlines, missing = fetch_headlines(self.news_region, self.check)
        metrics['news_sources'] = source_text(headlines, missing)
        if self.key and headlines:
            metrics['news_ai_used'] = True
            try:
                answer = self.router.stream(self.router.spec(self.provider), self.model, self.key,
                                            prompt_messages(headlines), self.check, lambda _: None,
                                            metrics=metrics)
                if answer.strip() and any('஀' <= char <= '௿' for char in answer):
                    metrics['news_tamil'] = True
                    return answer.strip()
            except ProviderError as error:
                metrics['news_provider_error'] = str(error)
        return fallback_text(headlines)

    def run(self):
        metrics = {'provider': self.provider, 'model': self.model}
        started = time.monotonic()
        try:
            def attempt(provider, model, key, messages, check, emit):
                metrics.clear()
                metrics.update(provider=provider, model=model)
                return self.router.stream(self.router.spec(provider), model, key, messages,
                                          check, emit, metrics=metrics)
            if self.news_region is not None:
                answer = self.run_news(metrics)
            elif self.backup is None:
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


class ModelCheckWorker(QThread):
    """Ask a provider which models this key can use.

    No prompt is sent and nothing is generated, so this costs nothing and
    puts none of the owner's words on the provider's servers. The key is held
    only for the length of the request and is cleared in the `finally`.
    """

    result = Signal(str, str, object)

    def __init__(self, provider, endpoint, model, key, policy, ticket):
        super().__init__()
        self.provider, self.endpoint, self.model, self.key = provider, endpoint, model, key
        self.policy, self.ticket = policy, ticket

    def check(self):
        self.policy.check(self.ticket)
        if self.isInterruptionRequested():
            raise Stopped('Model check cancelled.')

    def run(self):
        try:
            self.check()
            answer = check_model(self.provider, self.endpoint, self.model, self.key)
            status, text, payload = 'completed', answer.detail, answer.as_dict()
        except Stopped:
            status, text, payload = 'cancelled', 'Model check cancelled.', {}
        except Exception:
            status, text, payload = 'failed', 'The model catalogue could not be checked.', {}
        finally:
            self.key = ''
        self.result.emit(status, text, payload)


class CodingTaskWorker(QThread):
    """Run one coding task off the UI thread and report every step.

    The progress signal carries the step and the sentence, so the chat can
    mark the task card as it goes. Nothing is logged, and the key never
    appears here: the CLI reads its own credentials.
    """

    progress = Signal(str, str)
    result = Signal(object)

    def __init__(self, task, policy, ticket):
        super().__init__()
        self.task = task
        self.policy = policy
        self.ticket = ticket

    def check(self):
        self.policy.check(self.ticket)
        if self.isInterruptionRequested():
            raise Stopped('Task cancelled.')

    def run(self):
        self.task.progress = lambda step, text: self.progress.emit(step, text)
        self.task.check_cancelled = self.check
        try:
            outcome = self.task.run()
        except Stopped:
            outcome = TaskOutcome(status='cancelled',
                                  message='Cancelled. Your project was not changed.')
        except Exception as error:
            outcome = TaskOutcome(status='failed', message=str(error))
        self.result.emit(outcome)


class TestRunWorker(QThread):
    """Run a project's tests off the UI thread.

    The tests can take minutes, so they must not run on the UI thread. The
    worker watches for Emergency Stop and for its own interruption, and when
    either happens the TEST PROCESS is terminated — not left running while
    the owner believes it stopped.
    """

    result = Signal(str, str, object)

    def __init__(self, folder, command, policy, ticket):
        super().__init__()
        self.folder = folder
        self.command = command
        self.policy = policy
        self.ticket = ticket
        #: The running test process, so a stop can show that it really ended.
        self.process = None

    def cancel_check(self):
        """Raise to stop the tests. Called while they run."""
        if self.isInterruptionRequested():
            raise Stopped('Test run cancelled.')
        self.policy.check(self.ticket)

    def run(self):
        from developer_studio.codex_task import run_local_tests
        try:
            status, output = run_local_tests(
                self.folder, self.command, cancel=self.cancel_check,
                observer=lambda process: setattr(self, 'process', process))
        except Stopped:
            status, output = 'cancelled', 'The test run was cancelled and the process was stopped.'
        except Exception as error:
            status, output = 'could not run', str(error)
        self.result.emit(status, output, {})


class Window(QMainWindow):
    def __init__(self, data_root):
        super().__init__()
        self.setWindowTitle('JARVIS AI')
        self.resize(1180, 790)
        self.root = Path(data_root)
        self.store = Store(self.root / 'history.sqlite3')
        saved_theme = self.store.get('omega:theme')
        self.interface_theme = saved_theme if isinstance(saved_theme, str) and saved_theme in OMEGA_THEMES else DEFAULT_THEME
        if saved_theme == 'MARK LVII':
            self.store.set('omega:theme', DEFAULT_THEME)
        self.setStyleSheet(theme_sheet(self.interface_theme))
        self.memory_service = MemoryService(self.root / 'history.sqlite3')
        self.router = ProviderRouter()
        self.policy = Policy()
        self.browser = BrowserControl(self)
        self.research_dialog = None
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
        self.attachments = []  # A temporary local snapshot; never persisted.
        self.document_under_read = None  # The document being previewed, if any.
        self.video_chat_brief = None
        self.chat_launch = None
        self.conversation_plan = ConversationPlan(self)
        self.launch_verification = None
        self.launch_timer = QTimer(self)
        self.launch_timer.setInterval(180)
        self.launch_timer.timeout.connect(self.check_chat_launch)
        self.desktop_pending = None
        self.desktop_task_timer = QTimer(self)
        self.desktop_task_timer.setInterval(180)
        self.desktop_task_timer.timeout.connect(self.complete_desktop_task)
        self.coding = None
        self.coding_worker = None
        self.test_worker = None
        self.chat_task_id = None
        self.memory = ConversationMemory(self.store)
        self.pending_clarification = None
        self.assistant_language = assistant_language(self.store)
        self.site_export = None
        self.news_panel = None
        self.site_draft = None
        self.site_preview_path = None
        self.worker = None
        self.omega = None
        self.improvement_worker = None
        self.paused = bool(self.store.get('paused', False))
        self.exit_requested = False
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
        self.resume_button = QPushButton('Resume', self)
        self.resume_button.clicked.connect(self.resume)
        self.resume_button.setEnabled(False)
        self.resume_button.hide()
        self.nav = QListWidget(self)
        self.nav.hide()
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        # One main UI: specialized tools remain available under Settings.
        self.page_indices = {}
        self.add_page('JARVIS Chat', self.chat_page())
        self.add_page('Files & Folders', self.files_page(), primary=False)
        # Keep the composer outside the scrolling conversation.
        outer.addWidget(self.composer_bar)
        self.add_page('PC Control', self.automation_page())
        self.add_page('Coding Assistant', self.editor_page())
        self.voice_panel = VoicePanel()
        # The speech language is remembered, so the owner does not choose it
        # again every time the application starts.
        saved_language = self.store.get('voice_language')
        if saved_language:
            self.voice_panel.set_language(saved_language)
        self.voice_panel.language.currentTextChanged.connect(
            lambda name: self.store.set('voice_language', self.voice_panel.language_code))
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
        self.add_page('Mission Control', self.mission_page())
        self.cybersecurity_panel = CybersecurityPanel(window=self)
        self.add_page('Cybersecurity', self.cybersecurity_panel, primary=False)
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
        self.add_page('Review changes', ReviewPanel(self), primary=False)
        # The chat page is built first, so the brain label can be filled in
        # once every provider page exists.
        self.refresh_brain_label()
        self.nav.currentRowChanged.connect(self.show_primary_page)
        self.nav.setCurrentRow(0)
        self.pages.currentChanged.connect(self.update_assistant_navigation)
        self.update_assistant_navigation()
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
        self.hotkey = GlobalHotkey(self.summon_from_hotkey)
        self.hotkey_status = ''
        self.apply_hotkey(self.store.get('hotkey:shortcut', DEFAULT_SHORTCUT), save=False)
        self.release_checker = ReleaseChecker(self)
        self.maintenance_timer = QTimer(self)
        self.maintenance_timer.timeout.connect(self.check_maintenance)
        self.maintenance_timer.start(60_000)
        self.enable_prime()
        QTimer.singleShot(0, self.check_maintenance)

    def mission_page(self):
        """The mission console: one goal, watched step by step."""
        from desktop.prime_ui import PrimePalette

        panel = MissionPanel(PrimePalette(dark=self.prime_is_dark()),
                             root=self.root, memory=self.memory_service)
        self.mission_panel = panel
        self.mission_controller = MissionController(self, panel)
        return panel

    def enable_omega(self, *, smoke=False):
        if self.omega is None:
            self.omega = Omega(self)
            self.voice_panel.audio_level.connect(self.omega.audio_level)
        self.omega.start(smoke=smoke)
        self.refresh_system_metrics()
        self.refresh_voice_hud()
        self.enable_prime()

    # -- the PRIME composition -------------------------------------------

    def enable_prime(self):
        """Mount the Quantum HUD and move shared controls into it."""
        from desktop.prime_ui import (
            PrimeChat, PrimePalette, PrimeShell,
        )

        if getattr(self, 'prime_shell', None) is not None:
            return self.prime_shell
        palette = PrimePalette(dark=self.prime_is_dark())
        self.prime_palette = palette
        shell = PrimeShell(self, palette)
        self.prime_shell = shell

        central = self.centralWidget()
        outer = central.layout()
        outer.removeWidget(self.pages)
        outer.removeWidget(self.composer_bar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(shell)

        # The chat becomes the PRIME chat. The old page stays alive: the
        # transcript it holds is what the application still reads.
        chat = PrimeChat(self, palette)
        index = self.page_indices['JARVIS Chat']
        was_current = self.pages.currentIndex() == index
        old_chat = self.pages.widget(index)
        self.pages.removeWidget(old_chat)
        self.pages.insertWidget(index, chat)
        if was_current:
            # The page that was open stays open.
            self.pages.setCurrentIndex(index)
        # The old page is kept alive on purpose: the transcript it holds
        # is what the application still reads and copies.
        self.prime_old_chat = old_chat
        self.prime_chat = chat
        chat.adopt_task_panels()
        shell.content.addWidget(self.pages)
        shell.activity.set_rows(self.store.tasks())
        self.render_chat()

        self.refresh_prime_state()
        return shell

    def prime_is_dark(self) -> bool:
        """The PRIME surface follows the theme the owner chose."""
        from desktop.prime_theme import _luminance

        name = self.interface_theme if self.omega is None else self.omega.theme
        palette = OMEGA_THEMES.get(name)
        if palette is None:
            return True
        return _luminance(palette[0]) < 0.5

    def refresh_prime_state(self):
        """The PRIME surface follows what JARVIS is doing."""
        shell = getattr(self, 'prime_shell', None)
        if shell is None:
            return
        state = self.prime_state()
        shell.set_state(state)
        shell.activity.set_live_detail(self.current_desktop_activity(state))
        shell.set_provider(self.brain_label.text())
        chat = getattr(self, 'prime_chat', None)
        if chat is not None:
            chat.set_state(state)

    def current_desktop_activity(self, state):
        if state == 'approval' and self.chat_launch is not None:
            name, _, action, _ = self.chat_launch
            if action.kind == 'desktop_plan_approval':
                return f'{name} · Review the exact text in Chat before approving.'
            return f'{name} · Approve or decline in Chat.'
        if state == 'working' and self.desktop_pending is not None:
            target = self.desktop_pending['task'].app
            return f'{target} · Checking the foreground window before entering text.'
        if state == 'working' and self.launch_verification is not None:
            name = self.launch_verification[0]
            return f'{name} · Checking whether Windows opened the requested window.'
        return ''

    def refresh_prime_theme(self):
        """The PRIME surface follows the theme the owner chose."""
        shell = getattr(self, 'prime_shell', None)
        if shell is None:
            return
        from desktop.prime_ui import PrimePalette

        palette = PrimePalette(dark=self.prime_is_dark())
        shell.palette_.adopt(palette)
        shell.refresh_theme()
        chat = getattr(self, 'prime_chat', None)
        if chat is not None:
            chat.refresh_theme()
        panel = getattr(self, 'mission_panel', None)
        if panel is not None:
            panel.palette_.adopt(palette)
            panel.timeline.palette_.adopt(palette)
            panel.refresh_theme()

    def prime_state(self) -> str:
        """idle, listening, working or error, from the real state."""
        if self.policy.stopped:
            return 'stopped'
        if self.chat_launch is not None or getattr(self, 'coding_pending', None):
            return 'approval'
        if self.voice_panel.speaking:
            return 'speaking'
        if self.voice_panel.listening:
            return 'listening'
        if self.ai_visual_state in ('thinking', 'responding'):
            return self.ai_visual_state
        if (self.worker is not None or self.coding_worker is not None or self.test_worker is not None
                or self.browser.task is not None or self.desktop_pending is not None
                or self.launch_verification is not None):
            return 'working'
        return 'idle'

    def on_theme_chosen(self, name: str) -> None:
        if name not in OMEGA_THEMES:
            return
        self.interface_theme = name
        if self.omega is not None:
            self.omega.set_theme(name)
        else:
            self.store.set('omega:theme', name)
            self.setStyleSheet(theme_sheet(name))
            self.chat_reactor.theme = name
            self.chat_reactor.update()
        # After the theme is really in use, so the PRIME surface reads the
        # theme that is in force and not the one before it.
        self.refresh_prime_theme()

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
            self.open_section(item.text())

    def open_section(self, name):
        name = {'Omega Home': 'JARVIS Chat', 'Omega Settings': 'Settings & Safety'}.get(name, name)
        chat = getattr(self, 'prime_chat', None)
        if chat is not None:
            chat.show_task(name)
            if name in chat.task_panels:
                self.pages.setCurrentIndex(self.page_indices['JARVIS Chat'])
                self.prime_shell.mark_active('JARVIS Chat')
                return
        index = self.page_indices[name]
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.ItemDataRole.UserRole) == index:
                self.nav.setCurrentRow(row)
                break
        self.pages.setCurrentIndex(index)
        shell = getattr(self, 'prime_shell', None)
        if shell is not None:
            shell.mark_active(name)
        if name == 'Settings & Safety':
            # The saved-project table lives in Settings, so it is refreshed
            # whenever the owner comes back to it.
            self.refresh_projects_page()
            self.audio_test.refresh_devices()

    def open_island(self):
        """The only optional presentation mode on the main assistant toolbar."""
        if self.omega is None:
            self.enable_omega()
        self.omega.switch('Island')

    def update_assistant_navigation(self, _index=None):
        """Keep the composer with the conversation."""
        in_chat = self.pages.currentIndex() == self.page_indices['JARVIS Chat']
        self.composer_bar.setVisible(in_chat)

    def open_plugins(self):
        """Open existing plugin switches without a large feature toolbar."""
        self.open_section('Settings & Safety')
        scroller = self.pages.widget(self.page_indices['Settings & Safety'])
        if isinstance(scroller, QScrollArea):
            scroller.ensureWidgetVisible(self.plugins_group, 16, 16)

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

    def draft_spoken_desktop_action(self, text):
        """Require a visible, editable review for a spoken desktop command."""
        if suggestion_argument(text) is not None:
            return False
        try:
            typing = parse_desktop_task(text)
        except ValueError:
            return False
        if typing is None and parse_voice_command(text) is None:
            return False
        self.open_section('JARVIS Chat')
        if self.prompt.toPlainText().strip():
            self.statusBar().showMessage(
                'Finish or clear the current draft, then repeat the voice command.', 15000)
            return True
        self.prompt.setPlainText('/suggest ' + text)
        self.prompt.setFocus()
        self.statusBar().showMessage(
            'Check or edit what JARVIS heard, then send it to preview the action.', 15000)
        return True

    def on_wake_detected(self, transcript, command):
        if self.policy.stopped or not self.voice_panel.consent.listening:
            return
        if self.omega is not None and self.omega.mode == 'Island':
            self.omega.switch('Omega')
        if not self.isVisible() or self.isMinimized() or not self.isActiveWindow():
            self.summon_from_hotkey()
        self.open_section('JARVIS Chat')
        self.prime_shell.pulse_wake()
        text = (command or '').strip()[:4000]
        if text:
            self.show_hud_text('Heard: ' + text)
        if self.draft_spoken_desktop_action(text):
            return
        if (not self.suggestion_mode.isChecked() and suggestion_argument(text) is None
                and (self.answer_spoken_system_command(text) or self.route_task(text))):
            return
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
        if self.omega is not None and self.omega.mode != 'Omega':
            self.omega.switch('Omega')
        self.show_hud_text('Heard: ' + text)
        if self.draft_spoken_desktop_action(text):
            return
        if (not self.suggestion_mode.isChecked() and suggestion_argument(text) is None
                and (self.answer_spoken_system_command(text) or self.route_task(text))):
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
        if self.voice_panel.listening:
            self.voice_panel.cancel_listening()
        else:
            self.voice_panel.listen('once')

    def page(self, title, note=''):
        page = QWidget()
        # The page root carries the premium surface, so the window is never
        # transparent behind the conversation.
        page.setObjectName('pageRoot')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 10, 10)
        label = QLabel(title)
        label.setObjectName('pageTitle')
        layout.addWidget(label)
        if note:
            label = QLabel(note)
            label.setObjectName('pageSubtitle')
            label.setWordWrap(True)
            layout.addWidget(label)
        return page, layout

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def flexible_button(self, layout, text, callback, minimum=110):
        """A button that keeps its natural width but may shrink when it must.

        A long label on a full-width button sets a wide minimum on the whole
        page, and a page that asks for more width than the window has asks to
        scroll sideways. These buttons keep their natural width whenever there
        is room and give some of it back when there is not.
        """
        button = self.button(layout, text, callback)
        button.setMinimumWidth(minimum)
        button.setSizePolicy(QSizePolicy.Minimum, button.sizePolicy().verticalPolicy())
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
        self.button(layout, 'Tamil news briefing', self.open_news_briefing)
        for name in ('Video Editor', 'Coding Assistant', 'Business', 'Phone Remote', 'Task Queue'):
            self.button(layout, name, lambda checked=False, section=name: self.open_section(section))
        self.button(layout, 'Back to JARVIS Chat',
                    lambda: self.open_section('JARVIS Chat'))
        layout.addStretch()
        return page

    def open_news_briefing(self):
        if self.news_panel is None:
            self.news_panel = NewsPanel(self)
        self.news_panel.show()
        self.news_panel.raise_()
        self.news_panel.activateWindow()

    def start_news_briefing(self, region):
        if self.policy.stopped or self.worker is not None:
            return
        spec = self.router.spec('Gemini')
        model = self.store.get('model:Gemini', spec.default_model)
        try:
            key = self.get_key('Gemini')
        except (ValueError, RuntimeError):
            key = ''
        self.chat_ticket = self.policy.ticket()
        self.news_panel.output.setPlainText('Fetching current headlines…')
        self.start_worker('Gemini', model, key, [], 'news_briefing', news_region=region)

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
        if self.omega is not None:
            self.omega.update_metrics(data)
        for key, (value, meter) in self.hud_meters.items():
            percent = data[key]
            value.setText(f'{percent:.1f}%' if percent is not None else 'Unavailable')
            meter.setVisible(percent is not None)
            if percent is not None:
                meter.setValue(round(percent * 10))

    def handle_developer_command(self, text):
        """Dispatch only known commands through existing approval-gated features."""
        command = parse_command(text, load_projects(self.store))
        if command is None or command.kind == 'analysis':
            return False
        if command.kind == 'error':
            self.show_local_system_reply(text, command.detail)
        elif command.kind == 'help':
            self.show_local_system_reply(text, COMMAND_HELP)
        elif command.kind == 'projects':
            projects = load_projects(self.store)
            lines = [f'{item.name} — {item.editor} — ' +
                     ('folder found' if item.exists else 'folder missing')
                     for item in projects]
            self.show_local_system_reply(
                text, '\n'.join(lines) if lines else
                'No saved projects. Use /project add and choose a folder in Settings.')
        elif command.kind == 'editors':
            states = all_statuses(configured_launchers(self.store))
            self.show_local_system_reply(
                text, '\n'.join(item['name'] + ': ' +
                               ('installed' if item['installed'] else 'setup needed')
                               for item in states))
        elif command.kind == 'code_draft':
            # Reuse existing MiniMax/Codex draft worker and explicit approval.
            # A draft remains a preview until the owner reviews and saves it.
            if self.omega is not None and self.omega.mode != 'Omega':
                self.omega.switch('Omega')
            self.open_section('Coding Assistant')
            self.code_goal.setText(command.detail)
            self.generate_code()
        elif command.kind == 'project_status':
            project = find_project(load_projects(self.store), command.target)
            if project is None:
                self.show_local_system_reply(text, 'Project is no longer saved.')
            else:
                self.show_local_system_reply(
                    text, f'{project.name} — {project.editor} — ' +
                    ('folder found' if project.exists else 'folder missing') +
                    f' — tests: {project.test_command or "not configured"}')
        elif command.kind == 'project_add':
            if self.omega is not None and self.omega.mode != 'Omega':
                self.omega.switch('Omega')
            self.open_section('Settings & Safety')
            self.add_project()  # Owner selects the folder; never scan the disk.
        elif command.kind == 'document':
            self.preview_local_document()
        elif command.kind in ('project_open', 'project_test', 'project_fix', 'project_fix_test'):
            request = CodingRequest(
                project=command.target,
                change=command.detail,
                open_project=command.kind == 'project_open',
                run_tests=command.kind in ('project_test', 'project_fix_test'),
                make_change=command.kind in ('project_fix', 'project_fix_test'),
                mentions_work=True,
            )
            if self.omega is not None and self.omega.mode != 'Omega':
                self.omega.switch('Omega')
            self.open_section('JARVIS Chat')
            self.start_coding_task(request, text)  # Existing one-use approvals.
        elif command.kind == 'new':
            self.new_chat()
        elif command.kind == 'island':
            self.show_local_system_reply(
                text, 'Island ready. Expand to send a command; Esc returns to the main assistant.')
            self.open_island()
        elif command.kind == 'page':
            if self.omega is not None and self.omega.mode != 'Omega':
                self.omega.switch('Omega')
            self.open_section(command.target)
            self.show_local_system_reply(text, f'Opened {command.target}.')
        return True

    def preview_local_document(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, 'Open a local document', '', 'Text and Markdown (*.txt *.md *.markdown)')
        if not selected:
            return
        path = Path(selected)
        try:
            if path.suffix.lower() not in ('.txt', '.md', '.markdown') or not path.is_file():
                raise ValueError('Choose a text or Markdown file.')
            with path.open('rb') as document:
                data = document.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError('Choose a file up to 256 KiB.')
            content = data.decode('utf-8-sig')
            if '\x00' in content:
                raise ValueError('Choose a plain text file.')
        except (OSError, UnicodeError, ValueError) as error:
            self.statusBar().showMessage('Document could not be opened: ' + str(error), 15000)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(path.name)
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(content)
        layout.addWidget(preview)
        self.button(layout, 'Close', dialog.accept)
        dialog.exec()

    def local_system_reply(self, text):
        """The questions that are answered here, on this computer.

        These are the ones that do not need a model: what JARVIS can do,
        what time it is, and what the machine is doing. A question that is
        not one of them is not answered here, and goes on to the model.
        """
        intent = local_commands.match(text)
        if intent == 'tidy':
            return self.tidy_command()
        if intent == 'capabilities':
            return capability_summary(self)
        if intent == 'time':
            return datetime.now().astimezone().strftime('%H:%M %Z')
        if intent == 'status':
            phone_status = 'Running' if self.bridge.listener.running else 'Stopped'
            return f'{self.prime_shell.state_chip.text()}\nPhone Remote: {phone_status}\n\n{self.system_summary}'
        return None

    def tidy_command(self):
        """Carry out the folder plan the owner has already seen.

        Nothing moves without a plan that was shown first and an approval
        for that exact plan.
        """
        plan = getattr(self, 'organise_plan', None)
        if plan is None:
            return ('There is no folder plan to carry out. Choose a folder on the '
                    'Windows Automation page and read the plan first.')
        folder = plan.folder
        try:
            result = self.gateway.run(
                Action('organise_folder', folder),
                lambda action: self.confirm(action),
                lambda: organise(plan))
        except Denied:
            return 'Declined. Nothing was moved.'
        except Stopped:
            return 'Emergency stop. Nothing was moved.'
        self.organise_plan = None
        self.refresh_safety_report()
        return result_text(result)

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
        # The four states the owner needs to read at a glance: Idle, Listening,
        # Thinking and Speaking. ANSWERING means the answer is arriving and
        # has not started being read aloud yet.
        label = {
            'idle': 'IDLE', 'listening': 'LISTENING', 'thinking': 'THINKING',
            'responding': 'ANSWERING', 'speaking': 'SPEAKING', 'stopped': 'STOPPED',
        }[state]
        self.orb.set_state(state)
        self.hud_orb.set_state(state)
        if self.chat_launch is not None and not self.policy.stopped:
            label = 'APPROVAL REQUIRED'
        self.orb_status.setText('JARVIS  /  ' + label)
        self.chat_mic.setText('Cancel mic' if self.voice_panel.listening else 'Speak')
        self.chat_mic.setEnabled(not self.policy.stopped and not self.voice_panel.playback_busy)
        self.hud_voice_status.setText(label)
        if self.omega is not None:
            self.omega.set_voice(state)
        self.hud_talk.setEnabled(state not in ('stopped', 'listening', 'speaking')
                                 and not self.voice_panel.playback_busy)
        self.refresh_prime_state()

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
        self.orb.setObjectName('heroOrb')
        hero.addWidget(self.orb)
        details = QVBoxLayout()
        self.orb_status = QLabel('JARVIS  /  STANDBY')
        self.orb_status.setObjectName('statusChip')
        self.orb_status.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        details.addWidget(self.orb_status)
        self.system_metrics_label = QLabel('SYSTEM  /  Collecting local metrics...')
        self.system_metrics_label.setWordWrap(True)
        self.system_metrics_label.setObjectName('systemMetrics')
        self.system_metrics_label.hide()
        hero.addLayout(details, 1)
        layout.addLayout(hero)
        # The MARK LVII-inspired holographic reactor shares the existing AI
        # status and voice pipeline. It does not launch a second assistant.
        from desktop.omega_visuals import Reactor
        self.chat_reactor = Reactor()
        self.chat_reactor.theme = self.interface_theme
        self.chat_reactor.setAccessibleName('JARVIS holographic core')
        self.chat_reactor.setFixedHeight(170)
        layout.addWidget(self.chat_reactor, 0, Qt.AlignmentFlag.AlignCenter)
        # The active brain sits on its own line. It is information the owner
        # needs at a glance, and keeping it out of the provider row stops a
        # long model name from forcing the chat page to scroll sideways.
        self.brain_label = QLabel()
        self.brain_label.setObjectName('systemMetrics')
        self.brain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brain_label.setWordWrap(True)
        self.brain_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.brain_label)
        self.chat_provider = QComboBox()
        self.chat_provider.addItems(provider_names())
        self.chat_provider.setCurrentText(self.stored_chat_provider())
        self.chat_provider.currentTextChanged.connect(self.on_chat_provider_changed)
        self.new_chat_button = QPushButton('New chat')
        self.new_chat_button.clicked.connect(self.new_chat)
        # One command bar and transcript: all advanced chat controls are in
        # Settings, not another set of visible options beside the assistant.
        self.chat_settings_panel = QWidget()
        settings_layout = QVBoxLayout(self.chat_settings_panel)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.addWidget(QLabel('AI provider'))
        settings_layout.addWidget(self.chat_provider)
        self.auto_brain = QCheckBox('Automatically choose an AI provider')
        self.auto_brain.setToolTip('Routes chat and analysis across configured Gemini, OpenAI and MiniMax. '
                                   'The chosen provider receives this conversation and any one-time attachments. '
                                   'The local provider stays local. Provider billing limits still apply.')
        self.auto_brain.setChecked(bool(self.store.get('brain:auto', False)))
        self.auto_brain.toggled.connect(lambda value: self.store.set('brain:auto', value))
        settings_layout.addWidget(self.auto_brain)
        self.reasoning_effort = QComboBox()
        self.reasoning_effort.addItems(task_brain.EFFORTS)
        self.reasoning_effort.setCurrentText(self.store.get('brain:effort', 'Auto'))
        self.reasoning_effort.currentTextChanged.connect(lambda value: self.store.set('brain:effort', value))
        settings_layout.addWidget(QLabel('Reasoning profile'))
        settings_layout.addWidget(self.reasoning_effort)
        settings_layout.addWidget(self.new_chat_button)
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
        saved_backup = self.store.get('backup_provider')
        if saved_backup in provider_names():
            self.backup_provider.setCurrentText(saved_backup)
        self.backup_provider.currentTextChanged.connect(self.on_backup_provider_changed)
        settings_layout.addWidget(self.backup_provider)
        archives = QHBoxLayout()
        self.archives = QComboBox()
        archives.addWidget(self.archives, 1)
        self.archive_button = self.button(archives, 'Saved chats', self.open_chat)
        self.archive_button.setToolTip('Open a conversation that was saved earlier.')
        settings_layout.addLayout(archives)
        self.refresh_archives()
        self.transcript = QPlainTextEdit()
        self.browser_output = QPlainTextEdit()
        self.browser_output.setAccessibleName('Browser result')
        self.browser_output.setReadOnly(True)
        self.browser_output.setMaximumHeight(135)
        self.browser_output.hide()
        layout.addWidget(self.browser_output)
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName('transcriptCard')
        self.transcript.setMinimumHeight(96)
        layout.addWidget(self.transcript, 1)
        self.chat_approval = QWidget()
        self.chat_approval.setObjectName('approvalCard')
        approval_layout = QVBoxLayout(self.chat_approval)
        approval_title = QLabel('Approval required')
        approval_title.setObjectName('approvalTitle')
        approval_layout.addWidget(approval_title)
        approval_row = QHBoxLayout()
        approval_layout.addLayout(approval_row)
        self.chat_approval_label = QLabel()
        self.chat_approval_label.setTextFormat(Qt.TextFormat.PlainText)
        self.chat_approval_label.setWordWrap(True)
        self.chat_approval_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        approval_row.addWidget(self.chat_approval_label, 1)
        self.chat_approve_button = self.button(
            approval_row, 'Approve', lambda: self.finish_chat_launch(True))
        self.chat_decline_button = self.button(
            approval_row, 'Decline', lambda: self.finish_chat_launch(False))
        self.chat_approval.hide()
        layout.addWidget(self.chat_approval)
        self.chat_task_card = QWidget()
        self.chat_task_card.setObjectName('taskCard')
        card_layout = QVBoxLayout(self.chat_task_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_task_text = QLabel()
        self.chat_task_text.setWordWrap(True)
        self.chat_task_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.chat_task_text)
        task_buttons = QHBoxLayout()
        self.chat_task_approve = self.button(
            task_buttons, 'Approve task', lambda: self.finish_coding_approval(True))
        self.chat_task_decline = self.button(
            task_buttons, 'Decline', lambda: self.finish_coding_approval(False))
        self.chat_task_diff = self.button(task_buttons, 'Review diff', self.review_coding_diff)
        self.chat_task_tests = self.button(task_buttons, 'Run tests', self.run_coding_tests)
        self.chat_task_open = self.button(task_buttons, 'Open project', self.open_coding_project)
        self.chat_task_accept = self.button(task_buttons, 'Accept the change', self.accept_coding_change)
        self.chat_task_reject = self.button(task_buttons, 'Reject the change', self.reject_coding_change)
        card_layout.addLayout(task_buttons)
        self.chat_task_card.hide()
        layout.addWidget(self.chat_task_card)
        # The plan of a job with more than one step: every step and the
        # state it is really in. There is no percentage, because the work
        # that is left cannot be measured before it is done.
        self.plan_card = QWidget()
        self.plan_card.setObjectName('taskCard')
        plan_layout = QVBoxLayout(self.plan_card)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        self.plan_text = QLabel()
        self.plan_text.setWordWrap(True)
        self.plan_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        plan_layout.addWidget(self.plan_text)
        plan_buttons = QHBoxLayout()
        self.plan_retry_button = self.button(
            plan_buttons, 'Try this step again', self.retry_failed_plan_step)
        self.plan_retry_button.setObjectName('primary')
        self.plan_retry_button.setVisible(False)
        plan_buttons.addWidget(self.plan_retry_button)
        plan_buttons.addStretch()
        plan_layout.addLayout(plan_buttons)
        self.plan_card.hide()
        layout.addWidget(self.plan_card)
        self.suggested_steps = ()
        self.suggestion_card = QWidget()
        self.suggestion_card.setObjectName('taskCard')
        suggestion_layout = QVBoxLayout(self.suggestion_card)
        self.suggestion_preview = QLabel()
        self.suggestion_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.suggestion_preview.setWordWrap(True)
        suggestion_layout.addWidget(self.suggestion_preview)
        suggestion_actions = QHBoxLayout()
        self.button(suggestion_actions, 'Review suggested steps', self.review_suggested_plan)
        self.button(suggestion_actions, 'Dismiss', self.clear_suggested_plan)
        suggestion_layout.addLayout(suggestion_actions)
        self.suggestion_card.hide()
        layout.addWidget(self.suggestion_card)
        self.desktop_export_text = None
        self.desktop_result_card = QWidget()
        self.desktop_result_card.setObjectName('taskCard')
        result_layout = QVBoxLayout(self.desktop_result_card)
        self.desktop_result_label = QLabel()
        self.desktop_result_label.setTextFormat(Qt.TextFormat.PlainText)
        self.desktop_result_label.setWordWrap(True)
        result_layout.addWidget(self.desktop_result_label)
        self.desktop_save_button = self.button(result_layout, 'Save inserted text as…',
                                               self.save_desktop_result)
        self.desktop_result_card.hide()
        layout.addWidget(self.desktop_result_card)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName('composerCard')
        self.prompt.setPlaceholderText(
            'என்ன செய்ய வேண்டும்? Tell me what you need… e.g. Jarvis, CapCut open pannu')
        self.prompt.setAccessibleName('Message to JARVIS')
        # The prompt is tall enough for two lines of the placeholder, so
        # nothing is cut off when the display is scaled to 150 % or 200 %.
        self.prompt.setMinimumHeight(78)
        self.prompt.setMaximumHeight(190)
        self.chat_send_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self.prompt)
        self.chat_send_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.chat_send_shortcut.activated.connect(self.send)
        # The composer is NOT part of the scrolling page. It lives in the
        # window's own bottom bar, so the conversation scrolls and the input
        # is always in sight, whatever the window size.
        self.composer_bar = QWidget()
        composer_layout = QVBoxLayout(self.composer_bar)
        composer_layout.setContentsMargins(2, 6, 2, 0)
        composer_layout.addWidget(self.prompt)
        self.read_replies = QCheckBox('Read replies aloud')
        # Voice output is an explicit opt-in, remembered across restarts.
        # Without this the user must tick the box on every launch.
        self.read_replies.setChecked(bool(self.store.get('voice:read_replies', False)))
        self.read_replies.toggled.connect(
            lambda enabled: self.store.set('voice:read_replies', bool(enabled)))
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
            settings_actions, 'Review action', self.review_chat_pc_action)
        self.review_pc_action_button.setToolTip(
            'See what the answer wants to do on this PC and approve it.')
        composer_actions = QHBoxLayout()
        self.composer_actions = composer_actions
        composer_layout.addLayout(composer_actions)
        self.chat_mic = self.button(composer_actions, 'Speak', self.listen_to_user)
        self.chat_mic.setObjectName('quiet')
        self.attach_button = self.button(
            composer_actions, 'Attach', lambda: self.open_section('Files & Folders'))
        self.attach_button.setObjectName('quiet')
        self.attach_button.setToolTip(
            'Choose files or a folder to preview. AI sharing is opt-in for one message.')
        self.research_button = self.button(
            composer_actions, 'Research a page', self.open_research_window)
        self.research_button.setObjectName('quiet')
        self.research_button.setToolTip(
            'Read one page you name and ask a question about it. The page is read '
            'here, and only its text goes to the provider.')
        composer_actions.addStretch()
        self.send_button = self.button(composer_actions, 'Ask JARVIS', self.send)
        self.send_button.setObjectName('primary')
        self.send_button.setToolTip('Send message (Ctrl+Enter)')
        self.suggestion_mode = QPushButton('Suggestion Mode')
        self.suggestion_mode.setCheckable(True)
        self.suggestion_mode.setToolTip(
            'Get a plan in chat using your configured AI and conversation history. '
            'This mode does not start task workflows.')
        self.suggestion_mode.toggled.connect(self.update_suggestion_mode)
        composer_actions.insertWidget(composer_actions.indexOf(self.send_button), self.suggestion_mode)
        self.mission_mode = QPushButton('Work on this')
        self.mission_mode.setCheckable(True)
        self.mission_mode.setToolTip(
            'Send this message as a mission. JARVIS plans it, picks a tool, asks '
            'you before anything changes, and shows every step in Mission Control. '
            'The answer comes back into this conversation.')
        self.mission_mode.toggled.connect(self.update_mission_mode)
        composer_actions.insertWidget(composer_actions.indexOf(self.send_button), self.mission_mode)
        return page

    def open_research_window(self):
        """Open the research window: the owner names a page and a question."""
        from desktop.research_dialog import open_research

        if self.research_dialog is None:
            self.research_dialog = open_research(self)
        self.research_dialog.show()
        self.research_dialog.raise_()
        return self.research_dialog

    def show_browser_commands(self):
        from automation.browser import HELP
        self.open_section('JARVIS Chat')
        self.browser_output.setPlainText(HELP)
        self.browser_output.show()
        if not self.prompt.toPlainText().strip():
            self.prompt.insertPlainText('/browser ')
        self.prompt.setFocus()

    def files_page(self):
        """User-chosen local files and folders; no background upload."""
        page, layout = self.page(
            'Files & Folders',
            'Choose local files or a folder. Preview stays on this PC. '
            'Only checked files are shared once with the chosen AI provider.')
        files = QGroupBox('Files')
        file_actions = QHBoxLayout(files)
        self.button(file_actions, 'Choose files…', self.choose_attachment_files)
        layout.addWidget(files)
        folders = QGroupBox('Folders')
        folder_actions = QHBoxLayout(folders)
        self.button(folder_actions, 'Choose folder…', self.choose_attachment_folder)
        layout.addWidget(folders)
        documents_box = QGroupBox('Documents')
        document_actions = QHBoxLayout(documents_box)
        self.button(document_actions, 'Read a document…', self.read_document_file)
        self.button(document_actions, 'Compare with…', self.compare_document_file)
        self.button(document_actions, 'Clear the preview', self.clear_document_preview)
        document_actions.addStretch()
        search_row = QHBoxLayout()
        self.button(search_row, 'Search a folder…', self.search_chosen_folder)
        self.button(search_row, 'Summarise in chat', self.summarise_document)
        self.button(search_row, 'Export the summary…', self.export_summary)
        documents_box.layout().addLayout(search_row)
        layout.addWidget(documents_box)
        self.document_status = QLabel('')
        self.document_status.setWordWrap(True)
        layout.addWidget(self.document_status)
        self.document_preview = QPlainTextEdit()
        self.document_preview.setReadOnly(True)
        self.document_preview.setAccessibleName('Document preview')
        self.document_preview.setMinimumHeight(140)
        self.document_preview.setMaximumHeight(320)
        self.document_preview.setPlaceholderText(
            'A document you read is shown here. Nothing is sent anywhere until you '
            'choose to share a file with the assistant.')
        layout.addWidget(self.document_preview)
        self.attachment_list = QListWidget()
        self.attachment_list.setAccessibleName('Selected local attachments')
        self.attachment_list.itemDoubleClicked.connect(
            lambda _item: self.preview_attachment())
        layout.addWidget(self.attachment_list)
        actions = QHBoxLayout()
        self.button(actions, 'Preview selected', self.preview_attachment)
        self.button(actions, 'Remove selected', self.remove_selected_attachment)
        self.button(actions, 'Clear all', self.clear_attachments)
        layout.addLayout(actions)
        self.files_share_once = QCheckBox('Share selected file text once with AI')
        self.files_share_once.setChecked(False)
        self.files_share_once.setToolTip(
            'Private files stay local unless you check this box and send a message. '
            'Do not attach passwords or private keys. The selected provider may retain data.')
        layout.addWidget(self.files_share_once)
        sharing_note = QLabel(
            'Only your next Ask JARVIS message shares this text with the selected AI '
            'provider (and any separately enabled backup provider). '
            'Keep the checkbox off to preview files locally.')
        sharing_note.setWordWrap(True)
        layout.addWidget(sharing_note)
        self.attachment_status = QLabel('')
        self.attachment_status.setWordWrap(True)
        layout.addWidget(self.attachment_status)
        self.button(layout, 'Back to JARVIS Chat',
                    lambda: self.open_section('JARVIS Chat'))
        self.update_attachment_display()
        return page

    def update_attachment_display(self):
        self.attachment_list.clear()
        for item in self.attachments:
            self.attachment_list.addItem(f'{item.name}  ({item.size} bytes)')
        count = len(self.attachments)
        self.attach_button.setText(f'Attach ({count})' if count else 'Attach')
        self.attach_button.setToolTip(
            f'{count} local file(s) selected. Open to preview and approve one-turn AI sharing.')
        self.files_share_once.setEnabled(bool(count))
        if not count:
            self.files_share_once.setChecked(False)
        self.attachment_status.setText(
            f'{len(self.attachments)} file(s) selected; temporary text snapshots, '
            'not copied to the history database. Up to 12 files / '
            '24 KiB per file / 48,000 characters total. '
            'Supported: UTF-8 text, Markdown, code, CSV, JSON, PDF and DOCX. '
            'A binary file cannot be read.')

    def read_document_file(self):
        """Read one document the owner chose and show it here.

        Reading is a local act: the text stays on this PC until the owner
        chooses to share a file with the assistant, and the same one-turn
        consent that guards every other file guards this one.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose a document to read', '',
            'Documents (*.pdf *.docx *.txt *.md *.markdown *.csv *.json *.rst);;'
            'All files (*)')
        if not path:
            return
        try:
            document = documents.read_document(path)
        except documents.DocumentError as exc:
            self.document_status.setText(str(exc))
            self.document_preview.setPlainText('')
            return
        self.document_under_read = document
        self.document_preview.setPlainText(
            self.document_preview_text(document))
        note = f'{document.name}: {document.characters:,} characters'
        if document.pages:
            note += f' over {document.pages} page(s)'
        note += '. Nothing was sent anywhere.'
        if document.warnings:
            note += ' ' + ' '.join(document.warnings)
        self.document_status.setText(note)

    def document_preview_text(self, document):
        """The text shown for a document, bounded so the page stays usable."""
        limit = 20000
        if document.characters <= limit:
            return document.text
        return (document.text[:limit] +
                f'\n\n… {document.characters - limit:,} more characters are not shown here.')

    def compare_document_file(self):
        """Compare the document that was read with another one."""
        first = getattr(self, 'document_under_read', None)
        if first is None:
            self.document_status.setText('Read a document first, then compare it with another.')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Compare with', '',
            'Documents (*.pdf *.docx *.txt *.md *.markdown *.csv *.json *.rst);;'
            'All files (*)')
        if not path:
            return
        try:
            second = documents.read_document(path)
            result = documents.compare_documents(first, second)
        except documents.DocumentError as exc:
            self.document_status.setText(str(exc))
            return
        self.document_preview.setPlainText(documents.comparison_text(result))
        self.document_status.setText(
            f'Compared {result["first"]} with {result["second"]}. Nothing was sent anywhere.')

    def search_chosen_folder(self):
        """Search the text of the files in a folder the owner chose.

        The search happens here, on this computer. Nothing is sent
        anywhere, and only the folder the owner chose is looked at.
        """
        folder = QFileDialog.getExistingDirectory(
            self, 'Choose a folder to search')
        if not folder:
            return
        query, ok = QInputDialog.getText(
            self, 'Search', 'What are you looking for?')
        if not ok or not query.strip():
            return
        result = search_folder(folder, query)
        self.document_preview.setPlainText(search_result_text(result))
        self.document_status.setText(
            f'{result.match_count} match(es) for "{query.strip()}" in '
            f'{len(result.files_with_matches)} file(s). Nothing was sent anywhere.')

    def summarise_document(self):
        """Put the document that was read in front of the assistant.

        The text goes into the composer and the owner sends it. It is not
        sent by itself, and the same one-turn consent that guards every
        other file guards this one.
        """
        document = getattr(self, 'document_under_read', None)
        if document is None:
            self.document_status.setText('Read a document first, then summarise it.')
            return
        text = document.text.strip()
        if not text:
            self.document_status.setText('That document has no text to summarise.')
            return
        limit = 12000
        excerpt = text[:limit]
        if len(text) > limit:
            excerpt += (f'\n\n… {len(text) - limit:,} more characters were left out. '
                        'The whole document is on this page.')
        self.open_section('JARVIS Chat')
        self.prompt.setPlainText(
            'Summarise this document in the language I am using:\n\n' + excerpt)
        self.prompt.setFocus()
        self.statusBar().showMessage(
            'The document is in the composer. Press Ask JARVIS to send it.', 12000)

    def export_summary(self):
        """Save the summary the assistant gave, where the owner chooses."""
        text = self.transcript.toPlainText()
        if not text.strip():
            self.statusBar().showMessage('There is nothing to save yet.', 10000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save the summary', 'jarvis-summary.md',
            'Markdown (*.md);;Text (*.txt)')
        if not path:
            return
        try:
            Path(path).write_text(summary_export(text), encoding='utf-8')
        except OSError as error:
            self.statusBar().showMessage(f'The summary could not be saved: {error}', 15000)
            return
        self.statusBar().showMessage('The summary was saved to ' + path, 15000)

    def clear_document_preview(self):
        """Forget the document that was read."""
        self.document_under_read = None
        self.document_preview.setPlainText('')
        self.document_status.setText('')

    def choose_attachment_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Choose files to show JARVIS', '',
            'Readable files (*.txt *.md *.markdown *.csv *.json *.py *.js *.ts '
            '*.jsx *.tsx *.html *.css *.xml *.yaml *.yml *.toml *.log *.ini '
            '*.java *.kt *.sql *.sh *.ps1 *.bat *.cmd *.rst *.docx)')
        if not paths:
            return
        try:
            self.attachments = stage_files(paths, self.attachments)
            # Selecting new content invalidates earlier one-turn consent.
            self.files_share_once.setChecked(False)
        except AttachmentError as exc:
            self.statusBar().showMessage(str(exc), 15000)
        self.update_attachment_display()

    def choose_attachment_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Choose a folder to show JARVIS (safe text files only)')
        if not folder:
            return
        try:
            selected, skipped, truncated = stage_folder(folder, self.attachments)
            self.attachments = selected
            self.files_share_once.setChecked(False)
            self.update_attachment_display()
            self.statusBar().showMessage(
                f'Folder scan: {len(selected)} selected, {skipped} skipped'
                + ('; limit reached — not the entire folder' if truncated else ''),
                18000)
        except AttachmentError as exc:
            self.statusBar().showMessage(str(exc), 15000)

    def preview_attachment(self):
        index = self.attachment_list.currentRow()
        if index < 0 or index >= len(self.attachments):
            self.statusBar().showMessage('Select a file to preview.', 8000)
            return
        item = self.attachments[index]
        dialog = QDialog(self)
        dialog.setWindowTitle('Local preview · ' + item.name)
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(item.text)
        layout.addWidget(preview)
        self.button(layout, 'Close', dialog.accept)
        dialog.exec()

    def remove_selected_attachment(self):
        index = self.attachment_list.currentRow()
        if 0 <= index < len(self.attachments):
            del self.attachments[index]
            self.files_share_once.setChecked(False)
            self.update_attachment_display()
        if not self.attachments:
            self.files_share_once.setChecked(False)

    def clear_attachments(self):
        self.attachments.clear()
        self.files_share_once.setChecked(False)
        self.update_attachment_display()

    def bridge_page(self):
        self.bridge = BridgePanel(self.policy, self.store, self.vault, self.confirm, self.notify,
                                  router=self.router)
        return self.bridge

    def automation_page(self):
        page, layout = self.page('PC Control',
            'Choose an action to review. JARVIS asks before launching apps or accessing files and devices.')
        apps = QGroupBox('Applications')
        app_layout = QFormLayout(apps)
        app_row = QHBoxLayout()
        self.app_choice = QComboBox()
        self.app_choice.setAccessibleName('Windows application')
        self.app_choice.addItems(APPS)
        app_row.addWidget(self.app_choice, 1)
        self.flexible_button(app_row, 'Review launch', self.launch)
        app_layout.addRow(app_row)
        layout.addWidget(apps)

        files = QGroupBox('Files and folders')
        file_layout = QHBoxLayout(files)
        self.flexible_button(file_layout, 'Open file…', self.open_chosen_path)
        self.flexible_button(file_layout, 'Open folder…', lambda: self.open_chosen_path(folder=True))
        self.flexible_button(file_layout, 'Review tidy plan…', self.organise_chosen_folder)
        layout.addWidget(files)

        devices = QGroupBox('Windows and devices')
        device_layout = QVBoxLayout(devices)
        self.flexible_button(device_layout, 'Review visible windows', self.inspect_visible_windows)
        self.flexible_button(device_layout, 'Open camera reader',
                             lambda: self.notify(lambda: open_camera_reader(self)))
        layout.addWidget(devices)
        # What the approval boundary has actually done, in the owner's words.
        safety_box = QGroupBox('Approval boundary')
        safety_layout = QVBoxLayout(safety_box)
        self.safety_report = QLabel('')
        self.safety_report.setWordWrap(True)
        safety_layout.addWidget(self.safety_report)
        self.safety_details = QPlainTextEdit()
        self.safety_details.setReadOnly(True)
        self.safety_details.setMaximumHeight(120)
        self.safety_details.setPlaceholderText(
            'The last few decisions of the approval boundary.')
        safety_layout.addWidget(self.safety_details)
        layout.addWidget(safety_box)
        self.refresh_safety_report()
        return page

    def refresh_safety_report(self):
        """Show what the approval boundary has allowed and refused."""
        if not hasattr(self, 'safety_report'):
            return
        self.safety_report.setText(self.policy.summary())
        lines = []
        for decision in self.policy.decisions()[-8:]:
            lines.append(f'{decision.outcome}: {decision.kind} — {decision.target}'
                         + (f' ({decision.detail})' if decision.detail else ''))
        self.safety_details.setPlainText('\n'.join(lines))

    def open_chosen_path(self, *, folder=False):
        """Open the selected file or folder through the approval gateway."""
        if folder:
            path = QFileDialog.getExistingDirectory(self, 'Choose a folder to open')
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, 'Choose a file to open', '', 'Anything (*.*)')
        if not path:
            return
        target = str(Path(path))
        self.notify(lambda: self.gateway.run(Action('open_path', target), self.confirm,
                                             lambda: open_path(target)))
        self.refresh_safety_report()

    def organise_chosen_folder(self):
        """Tidy a folder the owner chose, after they have seen the plan."""
        chosen = QFileDialog.getExistingDirectory(
            self, 'Choose a folder to tidy')
        if not chosen:
            return
        try:
            plan = plan_organise(chosen)
        except OrganiseError as error:
            self.show_local_system_reply(chosen, str(error))
            return
        if not plan.moves:
            self.show_local_system_reply(chosen, plan_text(plan))
            return
        self.organise_plan = plan
        self.organise_folder = chosen
        self.show_local_system_reply(chosen, plan_text(plan))
        self.show_local_system_reply(
            chosen,
            'Nothing has been moved yet. Say "tidy it" and the plan above is '
            'carried out exactly as it is.')

    def run_approved_organise(self):
        """Carry out the plan the owner has seen."""
        plan = getattr(self, 'organise_plan', None)
        if plan is None:
            self.show_local_system_reply('tidy it', 'There is no plan to carry out.')
            return
        folder = plan.folder

        def operation():
            return organise(plan)

        self.gateway.run(
            Action('organise_folder', folder),
            lambda action: self.confirm(action),
            operation)
        self.organise_plan = None
        self.refresh_safety_report()

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
        sheet_row = QHBoxLayout()
        self.video_sheet_kind = QComboBox()
        self.video_sheet_kind.addItems(
            ['Shot list', 'Flow prompts', 'Higgsfield prompts', 'Editing checklist'])
        self.video_sheet_kind.currentTextChanged.connect(self.refresh_video_sheet)
        sheet_row.addWidget(self.video_sheet_kind, 1)
        self.video_copy_button = self.button(sheet_row, 'Copy to clipboard', self.copy_video_sheet)
        layout.addLayout(sheet_row)
        self.video_sheet = QPlainTextEdit()
        self.video_sheet.setReadOnly(True)
        self.video_sheet.setMaximumHeight(190)
        self.video_sheet.setPlaceholderText(
            'The copy-ready sheet appears here once a shot plan is ready.')
        layout.addWidget(self.video_sheet)
        self.video_preview = QPlainTextEdit()
        self.video_preview.setReadOnly(True)
        self.video_preview.setPlaceholderText('The cinematic shot list appears here once a plan is ready.')
        layout.addWidget(self.video_preview, 1)
        handoff = QGroupBox('Browser handoff')
        handoff_layout = QVBoxLayout(handoff)
        handoff_note = QLabel('Pick a shot, then open either tool. JARVIS copies the shot’s '
                             'prompt when available. Paste it in the browser to start.')
        handoff_note.setWordWrap(True)
        handoff_layout.addWidget(handoff_note)
        self.video_handoff_shot = QComboBox()
        self.video_handoff_shot.setAccessibleName('Shot for browser handoff')
        self.video_handoff_shot.setPlaceholderText('Generate a shot plan first')
        self.video_handoff_shot.setEnabled(False)
        handoff_layout.addWidget(self.video_handoff_shot)
        tool_row = QHBoxLayout()
        self.video_tool_buttons = {
            tool: self.flexible_button(
                tool_row, f'Open {tool}', lambda _checked=False, tool=tool: self.open_video_tool(tool))
            for tool in VIDEO_TOOLS
        }
        handoff_layout.addLayout(tool_row)
        layout.addWidget(handoff)
        self.video_engine.currentIndexChanged.connect(self.invalidate_video_plan)
        row = QHBoxLayout()
        self.video_export_buttons = (
            self.flexible_button(row, 'Save shot plan (JSON)',
                                 lambda: self.save_video_draft('json')),
            self.flexible_button(row, 'Save English subtitles (SRT)',
                                 lambda: self.save_video_draft('srt')),
        )
        for button in self.video_export_buttons:
            button.setEnabled(False)
        layout.addLayout(row)
        render_row = QHBoxLayout()
        self.video_render_button = self.flexible_button(
            render_row, 'Assemble MP4 preview', self.assemble_video)
        self.video_render_button.setEnabled(False)
        self.capcut_button = self.flexible_button(
            layout, 'Export for CapCut Desktop', lambda: self.assemble_video(editor='CapCut Desktop'))
        self.capcut_button.setEnabled(False)
        self.davinci_button = self.flexible_button(
            layout, 'Export for DaVinci Resolve', lambda: self.assemble_video(editor='DaVinci Resolve'))
        self.davinci_button.setEnabled(False)
        self.after_effects_button = self.button(render_row, 'Render After Effects', self.render_after_effects)
        self.video_cancel_render = self.button(render_row, 'Cancel export', self.cancel_video_export)
        self.video_cancel_render.hide()
        layout.addLayout(render_row)
        self.after_effects_timeline_button = self.flexible_button(
            layout, 'Build After Effects timeline', self.build_after_effects_timeline)
        self.after_effects_timeline_button.setEnabled(False)
        return page

    def show_workflow_suggestion(self):
        QMessageBox.information(
            self, 'Suggested video workflow',
            suggest_workflow(self.video_brief.toPlainText(), self.video_engine.currentText()),
        )

    def generate_video_plan(self, *, chat_brief=None):
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
            self.video_chat_brief = chat_brief
            self.start_worker(provider, model, key, messages, 'video_plan')

        self.notify(operation)

    def refresh_video_sheet(self):
        """Fill the copy area with the sheet the owner chose.

        The sheet is the part that gets pasted into Flow, Higgsfield or the
        editor, so it carries only what that tool needs.
        """
        if self.video_plan is None:
            self.video_sheet.clear()
            return
        plan = self.video_plan[1]
        kind = self.video_sheet_kind.currentText()
        if kind == 'Flow prompts':
            text = prompt_sheet(plan, 'Google Flow')
        elif kind == 'Higgsfield prompts':
            text = prompt_sheet(plan, 'Higgsfield')
        elif kind == 'Editing checklist':
            text = editing_checklist(plan)
        else:
            text = shot_list(plan)
        self.video_sheet.setPlainText(text)

    def copy_video_sheet(self):
        """Copy the sheet so it can be pasted straight into the tool."""
        text = self.video_sheet.toPlainText()
        if not text.strip():
            self.statusBar().showMessage('Generate a shot plan first.', 8000)
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(
            'Copied the ' + self.video_sheet_kind.currentText().lower() + ' to the clipboard.', 8000)

    def open_video_tool(self, tool):
        """Open an external editing tool and copy the prompt for it.

        The one-click handoff is what the Video Studio section is for: the
        button puts the shot prompt on the clipboard and opens the tool. The
        chat command for the same tool asks for approval, because a chat
        command can come from anything the owner typed.
        """
        url, field = VIDEO_TOOLS[tool]

        def operation():
            self.policy.ticket()
            if not self.plugin_enabled(tool):
                raise ValueError(f'{tool} is disabled in Settings → Plugins.')
            index = self.video_handoff_shot.currentIndex()
            prompt = ''
            if self.video_plan is not None and index >= 0:
                prompt = self.video_plan[1]['shots'][index].get(field, '')
            if prompt:
                QApplication.clipboard().setText(prompt)
            if not QDesktopServices.openUrl(QUrl(url)):
                detail = ' The prompt is on your clipboard.' if prompt else ''
                raise ValueError(f'Could not open {tool} in your browser.' + detail)
            if prompt:
                return f'Shot {index + 1} prompt copied. Paste it in {tool}.'
            if index >= 0:
                return f'Opened {tool}. Shot {index + 1} has no {tool} prompt to copy.'
            return f'Opened {tool}. Generate a shot plan to copy a prompt from JARVIS.'

        self.notify(operation)

    def invalidate_video_plan(self):
        self.video_plan = None
        self.video_preview.clear()
        self.video_sheet.clear()
        self.video_handoff_shot.clear()
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

    def assemble_video(self, *, editor=None):
        if self.video_plan is None or self.worker is not None or self.policy.stopped:
            return
        selection = self.video_plan
        _, plan = selection

        def operation():
            media_tools()
            dialog = PreviewInputs(plan, self, editor=editor)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.video_plan is not selection or self.worker is not None:
                raise ValueError('The current task changed. Open the export dialog again.')
            clips = [field.text() for field in dialog.clips]
            output = dialog.target.text()
            narration = dialog.narration.text() or None
            exporter, action, label = {
                'CapCut Desktop': (export_capcut, 'export_for_capcut', 'Preparing CapCut export…'),
                'DaVinci Resolve': (export_davinci, 'export_for_davinci', 'Preparing DaVinci Resolve export…'),
                None: (render_preview, 'start_video_preview', 'Assembling local MP4 preview…'),
            }[editor]
            self.gateway.run(
                Action(action, output), self.confirm,
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
        self.button(layout, 'Client inbox & replies', self.open_client_inbox)
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
        self.editopro_english_reply = None
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

    def open_client_inbox(self):
        if not self.policy.stopped:
            dialog = StudioInboxDialog(self)
            try:
                dialog.exec()
            finally:
                dialog.deleteLater()

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
        """Open the AI Studio project, with the owner's approval.

        The URL is checked before anything is opened, and the approval names
        the address that is about to be opened.
        """
        try:
            url = validate_studio_url(self.website_project_url.text())
        except (ValueError, OSError) as error:
            self.notify(lambda: (_ for _ in ()).throw(error))
            return
        action = Action('open_website_project', url)

        def operation():
            self.policy.ticket()
            self.store.set('website_ai_studio_url', url)
            if not QDesktopServices.openUrl(QUrl(url)):
                raise ValueError('Project URL saved. Windows could not open your browser.')
            return 'AI Studio project URL saved.'

        self.notify(lambda: self.gateway.run(action, self.confirm, operation))

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
            draft = self.editopro_english_reply or self.business_preview.toPlainText()
            if draft.strip():
                QApplication.clipboard().setText(draft)
                message = ('English reply copied.' if self.editopro_english_reply
                           else 'Business draft copied.')
                self.statusBar().showMessage(message, 5000)

    def clear_business_draft(self):
        self.editopro_english_reply = None
        self.business_copy.setText('Copy draft')
        self.site_draft = None
        self.site_preview_path = None
        self.site_open_preview.setEnabled(False)
        self.site_save.setEnabled(False)
        self.business_preview.clear()
        self.business_status.setText('Review the brief and select Generate business draft.')

    def route_business_brief(self, text):
        request = spoken_business_request(addressed_request(text))
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
        if task == EDITOPRO_REPLY:
            self.business_status.setText(
                'Review the client message, then select Generate business draft to share it with Gemini.')
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
        self.coding_provider.addItems(routing.coding_provider_names())
        self.coding_provider.setCurrentText(routing.coding_provider(self.store))
        self.coding_provider.currentTextChanged.connect(self.on_coding_provider_changed)
        # The choice is written down, so the owner can see which provider is
        # in use even when it is the default.
        routing.set_coding_provider(self.store, self.coding_provider.currentText())
        provider_row.addWidget(self.coding_provider, 1)
        self.button(provider_row, 'MiniMax API settings', self.open_minimax_settings)
        layout.addLayout(provider_row)
        routing_note = QLabel(
            'Only MiniMax and Codex may write or fix source code. Gemini answers you, '
            'reads the proposed change and explains it; it never edits a file.')
        routing_note.setWordWrap(True)
        layout.addWidget(routing_note)
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
        improve = QHBoxLayout()
        self.improvement_goal = QLineEdit()
        self.improvement_goal.setPlaceholderText(
            'Describe an improvement to JARVIS itself…')
        improve.addWidget(self.improvement_goal, 1)
        self.button(improve, 'Prepare this improvement', self.start_improvement)
        self.button(layout, 'Retry latest interrupted improvement', self.retry_improvement)
        layout.addLayout(improve)
        improve_note = QLabel(
            'The change is prepared in an isolated worktree under the local development folder, '
            'where you can review the diff, authorize the tests, then approve the revision for restart.')
        improve_note.setWordWrap(True)
        layout.addWidget(improve_note)
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
        """The provider that writes code.

        Only MiniMax and Codex may do this. The chat provider is never used
        for code, whatever it is set to.
        """
        return routing.require_coding_provider(routing.coding_provider(self.store))

    def on_coding_provider_changed(self, provider):
        """Remember the coding provider the owner chose."""
        if provider in routing.coding_provider_names():
            routing.set_coding_provider(self.store, provider)
            self.refresh_routing_note()

    def coding_model(self, provider):
        """The model to use with a coding provider.

        Codex is the command line tool, so it chooses its own model and has
        no model ID here.
        """
        saved = self.store.get('model:' + provider)
        if saved:
            return saved
        try:
            return self.router.spec(provider).default_model
        except KeyError:
            return ''

    def refresh_routing_note(self):
        """Show which provider answers and which one writes code."""
        if not hasattr(self, 'coding_provider'):
            return
        self.coding_provider.setCurrentText(routing.coding_provider(self.store))

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
            if self.worker_kind in ('code_generation', 'code_repair'):
                # A draft goes to the preview, so it can be applied to the
                # editor in the same way as any other draft.
                self.code_preview.setPlainText(response)
                self.code_status.setText('Codex draft ready. Review it before you copy it.')
            else:
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
            if provider == 'Codex':
                self.draft_with_codex(messages[-1]['content'], 'code_generation')
                return
            model = self.coding_model(provider)
            key = self.coding_key(provider)
            if not self.confirm(Action('send_coding_goal', provider + ' / ' + model + ' (API charges may apply)')):
                return
            self.policy.check(ticket)
            self.chat_ticket = ticket
            self.code_preview.clear()
            self.code_status.setText(f'{provider} is drafting your code…')
            self.start_worker(provider, model, key, messages, 'code_generation')
        self.notify(operation)

    def draft_with_codex(self, prompt, kind):
        """Draft with the Codex command line tool.

        Codex is a local tool, so there is no key and no API charge. The
        draft lands in the same preview the other provider uses, and it is
        applied to the editor only when the owner approves that.
        """
        ticket = self.policy.ticket()
        executable = codex_executable()
        project = self.workspace.root
        action = Action('codex_draft', f'{kind} · Codex reads {project}')
        if not self.confirm(action):
            return
        self.policy.check(ticket)
        self.chat_ticket = ticket
        self.worker_kind = kind
        self.active_provider = 'Codex'
        self.active_model = ''
        self.chat_task = self.store.task(kind, 'Codex CLI draft')
        self.store.finish(self.chat_task, 'running')
        self.code_preview.clear()
        self.code_status.setText('Codex is drafting your code…')
        self.worker = VideoExportWorker(
            lambda check: run_codex(executable, project, prompt, check), self)
        self.worker.result.connect(self.on_codex_result)
        self.worker.finished.connect(self.on_finished)
        self.refresh_draft_buttons()
        self.set_ai_visual_state('thinking')
        self.worker.start()

    def repair_code(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            messages = messages_for_repair(self.editor.toPlainText(), self.code_error.toPlainText())
            provider = self.selected_coding_provider()
            if provider == 'Codex':
                self.draft_with_codex(messages[-1]['content'], 'code_repair')
                return
            model = self.coding_model(provider)
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
        self.provider_profile = QComboBox()
        self.provider_profile.currentIndexChanged.connect(self.on_profile_changed)
        advanced_form.addRow('Model profile', self.provider_profile)
        self.profile_note = QLabel()
        self.profile_note.setWordWrap(True)
        advanced_form.addRow('Profile', self.profile_note)
        advanced_form.addRow('Model ID', self.model)
        advanced_form.addRow('HTTPS endpoint', self.endpoint)
        self.price_note = QLabel()
        self.price_note.setWordWrap(True)
        advanced_form.addRow('List price', self.price_note)
        self.button(advanced_form, 'Use recommended model', self.reset_provider_model)
        layout.addWidget(self.provider_advanced_panel)
        self.provider_advanced_panel.hide()
        self.advanced_provider.toggled.connect(self.provider_advanced_panel.setVisible)
        self.button(layout, 'Save provider settings and check new keys', self.save_provider)
        self.button(layout, 'Remove stored key', self.remove_key)
        self.probe_button = self.button(layout, 'Test saved provider connection (uses API)', self.test_connection)
        self.availability_button = self.button(
            layout, 'Check model availability (free, no prompt sent)', self.check_model_availability)
        self.provider_health = QLabel()
        self.provider_health.setWordWrap(True)
        layout.addWidget(self.provider_health)
        self.provider.currentTextChanged.connect(self.load_provider)
        self.model.textChanged.connect(self.refresh_price_note)
        self.load_provider()
        self.azure_voice = AzureVoiceSettings(self)
        layout.addWidget(self.azure_voice)
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
            'The cost column is an estimate from the list price of the model, read on '
            f'{pricing.PRICED_ON}; only the provider dashboard can say what was really charged. '
            'Unknown does not mean zero or free. '
            'Duration is the local request time; checks are user-triggered, never background probes.')
        self.usage_table = QTableWidget(0, 8)
        self.usage_table.setHorizontalHeaderLabels(
            ['Provider / Model', 'Status', 'Seconds', 'Input', 'Output', 'Total',
             'Est. cost', 'Created (UTC)'])
        self.usage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.usage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.usage_table)
        self.usage_cost_summary = QLabel('')
        self.usage_cost_summary.setWordWrap(True)
        layout.addWidget(self.usage_cost_summary)
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
            self.clear_desktop_result()
            self.clear_suggested_plan()
            self.conversation_plan.cancel('Conversation changed; remaining steps cancelled.')
            if self.chat_launch is not None:
                self.finish_chat_launch(False)
            self.session = session
            self.store.set('session', session)
            self.render_chat()

    def test_connection(self):
        if self.worker is not None:
            return
        def operation():
            ticket = self.policy.ticket()
            provider = self.provider.currentText()
            model = self.selected_model(provider)
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

    def check_model_availability(self):
        """Check that the selected model is one this key can actually use."""
        if self.worker is not None:
            return

        def operation():
            provider = self.provider.currentText()
            model = self.selected_model(provider)
            if self.secret.text() or self.model.text().strip() != model:
                raise ValueError('Save the provider configuration before checking.')
            self.chat_ticket = self.policy.ticket()
            spec = self.router.spec(provider)
            key = '' if spec.local else self.get_key(provider)
            self.worker_kind = 'model_check'
            self.worker = ModelCheckWorker(provider, spec.endpoint, model, key,
                                           self.policy, self.chat_ticket)
            self.worker.result.connect(self.on_model_check_result)
            self.worker.finished.connect(self.on_finished)
            self.availability_button.setEnabled(False)
            self.worker.start()
            return 'Checking which models this key can use…'
        self.notify(operation)

    def on_model_check_result(self, status, text, payload=None):
        """Show the answer: which model, and whether the provider serves it."""
        try:
            self.policy.check(self.chat_ticket)
        except Stopped:
            return
        if status == 'completed' and payload and payload.get('known'):
            name = payload['provider']
            catalogue = payload.get('models', [])
            self.store.set('catalogue:' + name, catalogue)
            if not payload.get('available') and self.store.get('model:' + name) == payload['model']:
                selected = task_brain.catalogued_model(
                    name, payload['model'], catalogue, self.stored_profile(name),
                    custom=bool(self.store.get('custom_model:' + name, False)))
                if selected:
                    self.store.set('model:' + name, selected)
                    if self.stored_profile(name):
                        self.store.set('model:' + name + ':' + self.stored_profile(name), selected)
                    text = f'{name} lists {selected}. Selected for the next request.'
                    if self.provider.currentText() == name:
                        self.load_provider()
                    self.refresh_brain_label()
        if status == 'completed':
            self.provider_health.setText(text)
        else:
            self.provider_health.setText(status.capitalize() + ': ' + text)
        self.statusBar().showMessage(text, 20000)

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

    def start_worker(self, provider, model, key, messages, kind, backup=None, news_region=None):
        self.worker_kind = kind
        self.active_provider, self.active_model = provider, model
        self.chat_task = self.store.task(kind, provider + ' / ' + model)
        self.store.finish(self.chat_task, 'running')
        self.worker = ChatWorker(self.router, provider, model, key, messages, self.policy,
                                 self.chat_ticket,
                                 backup=backup if kind == "chat" else None, news_region=news_region)
        self.refresh_brain_label()
        self.worker.chunk.connect(self.on_chunk)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.on_finished)
        for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button,
                       self.repair_button, self.availability_button):
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
        page, layout = self.page('Settings & Safety')
        tools = QGroupBox('Settings shortcuts')
        tool_layout = QGridLayout(tools)
        for index, (label, name) in enumerate((
            ('AI providers', 'AI Providers'),
            ('Voice and microphone', 'Voice / Hey Jarvis'),
            ('PC Control', 'PC Control'),
            ('Phone Remote', 'Phone Remote'),
            ('Files & Folders', 'Files & Folders'),
            ('Task queue', 'Task Queue'),
            ('Workflows', 'Step Workflows'),
            ('Task history', 'Task History'),
            ('System & usage', 'System & Usage'),
            ('Review prepared changes', 'Review changes'),
        )):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, name=name: self.open_section(name))
            tool_layout.addWidget(button, index // 2, index % 2)
        layout.addWidget(tools)

        assistant_group = QGroupBox('Chat, provider and voice preferences')
        assistant_layout = QVBoxLayout(assistant_group)
        assistant_layout.addWidget(self.chat_settings_panel)
        layout.addWidget(assistant_group)
        self.audio_test = AudioTest(self.voice_panel, self.policy)
        self.audio_test.finished.connect(self.schedule_local_voice_rearm)
        layout.addWidget(self.audio_test)

        preferences = QGroupBox('Appearance and startup')
        preference_layout = QVBoxLayout(preferences)
        appearance = QFormLayout()
        self.theme_choice = QComboBox()
        self.theme_choice.addItems(list(OMEGA_THEMES))
        self.theme_choice.setCurrentText(self.interface_theme)
        self.theme_choice.currentTextChanged.connect(self.on_theme_chosen)
        appearance.addRow('Interface theme', self.theme_choice)
        preference_layout.addLayout(appearance)
        self.keep_in_tray = QCheckBox('Keep JARVIS running in the system tray')
        self.keep_in_tray.setChecked(bool(self.store.get('keep_running_in_tray', False)))
        self.keep_in_tray.toggled.connect(
            lambda enabled: self.store.set('keep_running_in_tray', bool(enabled)))
        preference_layout.addWidget(self.keep_in_tray)
        self.start_at_signin = QCheckBox('Start JARVIS when Windows signs in')
        self.start_at_signin.setEnabled(startup_supported())
        self.start_at_signin.setChecked(start_at_signin_enabled())
        self.start_at_signin.toggled.connect(self.on_start_at_signin)
        preference_layout.addWidget(self.start_at_signin)
        self.tray_note = QLabel(self.tray_note_text())
        self.tray_note.setWordWrap(True)
        preference_layout.addWidget(self.tray_note)
        layout.addWidget(preferences)

        updates = QGroupBox('Updates and recovery')
        update_layout = QVBoxLayout(updates)
        self.flexible_button(update_layout, 'Updates & rollback', lambda: open_updates(self))
        self.auto_maintenance = QCheckBox('Automatically propose source update guide fixes')
        self.auto_maintenance.setChecked(bool(self.store.get('auto_maintenance', False)))
        self.auto_maintenance.toggled.connect(self.set_auto_maintenance)
        update_layout.addWidget(self.auto_maintenance)
        layout.addWidget(updates)
        backup = QGroupBox('History backup and restore')
        backup_layout = QVBoxLayout(backup)
        self.history_backup_panel = HistoryBackupPanel(
            history_path=self.root / 'history.sqlite3')
        backup_layout.addWidget(self.history_backup_panel)
        layout.addWidget(backup)
        self.add_projects_settings(layout)
        plugins = QGroupBox('Plugins')
        self.plugins_group = plugins
        plugin_layout = QVBoxLayout(plugins)
        for name in (*VIDEO_TOOLS, *EDITOR_EXECUTABLES):
            row = QHBoxLayout()
            enabled = QCheckBox(name)
            enabled.setChecked(self.plugin_enabled(name))
            enabled.toggled.connect(
                lambda value, name=name: self.store.set('plugin:' + name, value))
            row.addWidget(enabled)
            row.addStretch()
            if name in EDITOR_EXECUTABLES:
                configured = self.store.get('editor_path:' + name, '')
                label = QLabel('Executable configured' if configured else 'Setup needed')
                row.addWidget(label)
                button = QPushButton('Choose EXE')
                button.clicked.connect(
                    lambda _checked=False, name=name, label=label: self.choose_editor_path(name, label))
                row.addWidget(button)
            plugin_layout.addLayout(row)
        layout.addWidget(plugins)
        safety = QGroupBox('Permissions and data')
        safety_layout = QVBoxLayout(safety)
        for note in (
            'App launches, workflow steps, inspections and file changes require your approval. '
            'Sending a chat message shares it with the selected provider.',
            'Emergency Stop (Ctrl+Alt+J) cancels pending work and approvals. '
            'Apps already opened stay open, and requests already sent may be billed.',
            'Windows Credential Manager stores keys. Local history and code are stored as plaintext.',
        ):
            label = QLabel(note)
            label.setWordWrap(True)
            safety_layout.addWidget(label)
        layout.addWidget(safety)
        return page

    def plugin_enabled(self, name):
        return bool(self.store.get('plugin:' + name, True))

    def choose_editor_path(self, name, label):
        current = self.store.get('editor_path:' + name, '')
        path, _ = QFileDialog.getOpenFileName(
            self, f'Choose {name}', current, 'Windows application (*.exe)')
        if path:
            def save():
                executable = editor_executable(name, path)
                self.store.set('editor_path:' + name, str(executable))
                label.setText(executable.name + ' configured')
            self.notify(save)

    def queue_chat_launch(self, command, name):
        if (self.chat_launch is not None or self.desktop_pending is not None
                or self.launch_verification is not None):
            return False
        self.open_section('JARVIS Chat')
        try:
            ticket = self.policy.ticket()
            if name in APPS:
                action = Action('launch_app', name)
                operation = lambda: launch_app(name)
            else:
                if not self.plugin_enabled(name):
                    raise ValueError(f'{name} is disabled in Settings → Plugins.')
                if name in VIDEO_TOOLS:
                    url, _ = VIDEO_TOOLS[name]
                    action = Action('open_video_tool', url)

                    def operation():
                        if not QDesktopServices.openUrl(QUrl(url)):
                            raise ValueError(f'Could not open {name} in the browser.')
                        return f'Browser launch requested for {name}.'
                else:
                    path = editor_executable(name, self.store.get('editor_path:' + name, ''))
                    action = Action('launch_editor', str(path))
                    operation = lambda: launch_editor(name, path)
        except (Stopped, ValueError, OSError) as error:
            self.show_local_system_reply(command, str(error))
            return False
        self.chat_launch = (name, ticket, action, operation)
        self.show_local_system_reply(command, f'Open {name}? Approve or decline below.')
        self.chat_approval_label.setText(action.target)
        self.chat_approval.show()
        self.refresh_voice_hud()
        return True

    def finish_chat_launch(self, approved):
        pending, self.chat_launch = self.chat_launch, None
        self.chat_approval.hide()
        self.refresh_voice_hud()
        if pending is None:
            return
        name, ticket, action, operation = pending
        success = False
        try:
            self.policy.check(ticket)
            if approved and name not in APPS and not self.plugin_enabled(name):
                raise ValueError(f'{name} is disabled in Settings → Plugins.')
            task_id = self.store.task(action.kind, action.target)
            result = self.gateway.run(action, lambda _action: approved, operation,
                                      task_id=task_id, completion_status='dispatched')
            if isinstance(result, LaunchRequest):
                self.launch_verification = (name, result, ticket, task_id,
                                            self.session, time.monotonic() + 7)
                self.launch_timer.start()
                self.statusBar().showMessage(f'Checking for the {name} window.', 7000)
                self.refresh_history()
                self.refresh_prime_state()
                return
            success = True
        except (Denied, Stopped, ValueError, OSError, RuntimeError) as error:
            result = str(error)
        self.store.message(self.session, 'system', result)
        self.render_chat()
        self.refresh_history()
        if self.desktop_pending is None:
            self.conversation_plan.result(success, str(result) if approved else 'declined')

    def check_chat_launch(self):
        if self.launch_verification is None:
            return
        name, request, ticket, task_id, session, deadline = self.launch_verification
        try:
            self.policy.check(ticket)
            verified = launch_is_foreground(request)
        except Stopped:
            self.cancel_launch_verification()
            return
        except (OSError, RuntimeError):
            verified = False
        if not verified and time.monotonic() < deadline:
            return
        self.launch_timer.stop()
        self.launch_verification = None
        if verified:
            detail = f'{name} opened. Windows confirmed its foreground process (PID {request.pid}).'
        else:
            detail = f'{request} Its window could not be verified.'
        self.store.finish(task_id, 'verified' if verified else 'unverified', detail)
        self.store.message(session, 'system', detail)
        self.render_chat()
        self.refresh_history()
        self.refresh_prime_state()
        self.conversation_plan.result(True, detail, verified=verified)

    def cancel_launch_verification(self):
        if self.launch_verification is None:
            return False
        _, _, _, task_id, _, _ = self.launch_verification
        self.launch_timer.stop()
        self.launch_verification = None
        self.store.finish(task_id, 'cancelled', 'Window verification cancelled after launch dispatch.')
        self.refresh_history()
        self.refresh_prime_state()
        return True

    # ── coding tasks ─────────────────────────────────────────────────────


    # ── saved projects, editors and routines ─────────────────────────────

    def queue_desktop_task(self, command, task):
        """Review exact text before doing anything to a Windows application."""
        if (self.chat_launch is not None or self.desktop_pending is not None
                or self.launch_verification is not None):
            self.statusBar().showMessage('Finish the current desktop task first.', 10000)
            return False
        if self.omega is not None and self.omega.mode != 'Omega':
            self.omega.switch('Omega')
        self.open_section('JARVIS Chat')
        ticket = self.policy.ticket()
        digest = sha256(task.text.encode('utf-8')).hexdigest()
        step = 'open and type' if task.launch else 'type into active window'
        action = Action('desktop_plan_approval', f'{task.app}: {step}, {len(task.text)} chars',
                        digest)
        self.chat_launch = (task.app, ticket, action,
                            lambda: self.schedule_desktop_task(task, ticket, digest))
        excerpt = task.text[:160] + ('…' if len(task.text) > 160 else '')
        self.show_local_system_reply(command,
            f'Review desktop task: {step} in {task.app}. '
            'The full text to be inserted follows; approve only if correct:\n'
            + task.text + '\nThe target window must be verified before typing.')
        self.chat_approval_label.setText(
            f'{step.title()} in {task.app}: {excerpt!r}\nSHA-256: {digest}')
        self.chat_approval.show()
        self.refresh_voice_hud()
        return True

    def schedule_desktop_task(self, task, ticket, digest):
        """Schedule, never poll for a window on the Qt UI thread."""
        self.policy.check(ticket)
        if self.desktop_pending is not None:
            raise ValueError('A desktop task is already running.')
        if task.launch:
            launch_app(task.app)
        self.desktop_pending = dict(task=task, ticket=ticket, digest=digest,
                                    deadline=time.monotonic() + 7.0)
        self.desktop_task_timer.start()
        self.refresh_prime_state()
        return (f'Desktop plan approved for {task.app}. Waiting for its '
                'foreground window; text not entered yet.')

    def show_desktop_result(self, detail, verified_text=None):
        self.desktop_export_text = verified_text
        self.desktop_result_label.setText(detail)
        self.desktop_save_button.setVisible(verified_text is not None)
        self.desktop_result_card.show()

    def clear_desktop_result(self):
        self.desktop_export_text = None
        self.desktop_result_card.hide()

    def save_desktop_result(self):
        text = self.desktop_export_text
        if text is None or self.policy.stopped:
            return
        ticket = self.policy.ticket()
        session = self.session
        destination, _ = QFileDialog.getSaveFileName(
            self, 'Save inserted text as a new file', 'Notepad-text.txt', 'Text files (*.txt)',
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not destination or self.session != session or self.desktop_export_text is not text:
            return

        def save():
            self.policy.check(ticket)
            path = Path(destination)
            if not path.suffix:
                path = path.with_suffix('.txt')
            if path.suffix.lower() != '.txt':
                raise ValueError('Choose a .txt filename.')
            payload = text.encode('utf-8')

            def write_verified():
                try:
                    with path.open('xb') as output:
                        output.write(payload)
                except FileExistsError:
                    raise ValueError('That file already exists. Choose a new filename.') from None
                with path.open('rb') as output:
                    if output.read(len(payload) + 1) != payload:
                        raise OSError('The saved file could not be verified.')
                return f'Inserted text saved and verified in {path}'

            ident = self.store.task('desktop_text_export', str(path))
            detail = self.gateway.run(Action('desktop_text_export', str(path)),
                                      lambda _action: True, write_verified,
                                      task_id=ident, completion_status='verified')
            self.show_desktop_result(detail)
            self.show_local_system_reply('Save inserted text', detail)

        self.notify(save)

    def complete_desktop_task(self):
        """Only type after Windows verifies the target foreground process."""
        pending = self.desktop_pending
        if pending is None:
            self.desktop_task_timer.stop()
            return
        task = pending['task']
        try:
            self.policy.check(pending['ticket'])
            if time.monotonic() >= pending['deadline']:
                self.desktop_task_timer.stop()
                self.desktop_pending = None
                self.show_local_system_reply('Desktop task',
                    f'{task.app} did not become foreground in time. '
                    'No text was entered. Activate the correct window and retry.')
                self.show_desktop_result(
                    f'{task.app} did not come to the foreground. No text was sent.')
                self.conversation_plan.result(False, 'Target window did not become foreground in time.')
                return
            if not target_is_foreground(task.app):
                return
            self.desktop_task_timer.stop()
            self.desktop_pending = None
            action = Action('desktop_type', f'{task.app}: {len(task.text)} characters',
                            pending['digest'])
            task_id = self.store.task(action.kind, action.target)
            result = self.gateway.run(
                action, lambda _action: True,  # the exact text was approved in chat
                lambda: type_into_target(task.app, task.text),
                task_id=task_id, completion_status='dispatched')
            verified = isinstance(result, VerifiedEdit)
            status = 'verified' if verified else 'unverified'
            detail = f'{task.app} foreground confirmed. {result} JARVIS did not save a file.'
            self.store.finish(task_id, status, detail)
            self.show_desktop_result(
                detail if verified else detail + ' Check the editor before trying again.',
                task.text if verified else None)
            self.show_local_system_reply('Desktop task result', detail)
            self.conversation_plan.result(True, detail, verified=verified)
        except (Denied, Stopped, RuntimeError, ValueError, OSError) as error:
            self.desktop_task_timer.stop()
            self.desktop_pending = None
            self.show_desktop_result(f'Typing failed. {error}')
            self.show_local_system_reply('Desktop task failed', str(error))
            self.conversation_plan.result(False, str(error))
        finally:
            self.refresh_prime_state()

    def add_projects_settings(self, layout):
        """The saved-project settings, inside Settings & Plugins.

        Save each project folder with the editor you work in and the local test
        command. After that a chat request only has to name the project. JARVIS
        opens the real folder, works in an isolated Git worktree so your
        uncommitted files stay untouched, and shows you the diff before
        anything is pushed or merged.
        """
        heading = QLabel('Saved projects and editors')
        heading.setStyleSheet('font-size:19px;font-weight:600')
        layout.addWidget(heading)
        note = QLabel(
            'Save each project folder with the editor you work in and the local test command. '
            'After that a chat request only has to name the project. JARVIS opens the real '
            'folder, works in an isolated Git worktree so your uncommitted files stay '
            'untouched, and shows you the diff before anything is pushed or merged.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.projects_table = QTableWidget(0, 4)
        self.projects_table.setHorizontalHeaderLabels(
            ['Project', 'Folder', 'Editor', 'Test command'])
        header = self.projects_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.projects_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.projects_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.projects_table.itemSelectionChanged.connect(self.refresh_routine_switches)
        layout.addWidget(self.projects_table)
        row = QHBoxLayout()
        self.button(row, 'Add project folder', self.add_project)
        self.button(row, 'Remove selected project', self.remove_project)
        layout.addLayout(row)
        self.project_status = QLabel()
        self.project_status.setWordWrap(True)
        layout.addWidget(self.project_status)
        self.editor_status = QLabel()
        self.editor_status.setWordWrap(True)
        layout.addWidget(self.editor_status)
        launcher_heading = QLabel('Another editor, as a launcher you configure')
        launcher_heading.setStyleSheet('font-weight:600')
        layout.addWidget(launcher_heading)
        self.launchers_table = QTableWidget(0, 3)
        self.launchers_table.setHorizontalHeaderLabels(['Name', 'Command', 'Capabilities'])
        self.launchers_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.launchers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.launchers_table)
        launcher_row = QHBoxLayout()
        self.launcher_name = QLineEdit()
        self.launcher_name.setPlaceholderText('Name, e.g. Fleet')
        launcher_row.addWidget(self.launcher_name)
        self.launcher_command = QLineEdit()
        self.launcher_command.setPlaceholderText('Command or full path to its executable')
        launcher_row.addWidget(self.launcher_command)
        layout.addLayout(launcher_row)
        self.button(layout, 'Add this launcher', self.add_launcher)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel('Assistant language'))
        self.assistant_language_box = QComboBox()
        self.assistant_language_box.addItems(
            ['தமிழ் (Tamil)', 'English', 'Français (French)'])
        self.assistant_language_box.currentTextChanged.connect(self.change_assistant_language)
        language_row.addWidget(self.assistant_language_box)
        layout.addLayout(language_row)
        self.routine_open = QCheckBox('Open the selected project without asking')
        self.routine_open.toggled.connect(self.change_routine_open)
        layout.addWidget(self.routine_open)
        self.routine_tests = QCheckBox("Run the selected project's tests without asking")
        self.routine_tests.toggled.connect(self.change_routine_tests)
        layout.addWidget(self.routine_tests)
        self.refresh_projects_page()

    def refresh_projects_page(self):
        """Show the saved projects, the editors and the configured launchers."""
        projects = load_projects(self.store)
        self.projects_table.setRowCount(len(projects))
        for row, project in enumerate(projects):
            status = project_status(project)
            for column, text in enumerate((project.name, project.path,
                                           project.editor, project.test_command)):
                item = QTableWidgetItem(text)
                if column == 1 and not status['exists']:
                    item.setToolTip('This folder is not there any more.')
                self.projects_table.setItem(row, column, item)
        launchers = configured_launchers(self.store)
        self.launchers_table.setRowCount(len(launchers))
        for row, launcher in enumerate(launchers):
            state = editor_status(launcher['name'], launcher)
            self.launchers_table.setItem(row, 0, QTableWidgetItem(launcher['name']))
            self.launchers_table.setItem(row, 1, QTableWidgetItem(launcher['command']))
            self.launchers_table.setItem(row, 2, QTableWidgetItem(
                ', '.join(CAPABILITY_LABELS.get(item, item) for item in state['capabilities'])
                or 'No capabilities declared'))
        lines = []
        for name in editor_names():
            state = editor_status(name)
            if state['installed']:
                lines.append(f'{name}: installed — ' + ', '.join(
                    CAPABILITY_LABELS.get(item, item) for item in state['capabilities']))
            else:
                lines.append(f'{name}: SETUP NEEDED — {state["setup"]}')
        for launcher in launchers:
            state = editor_status(launcher['name'], launcher)
            lines.append(f'{launcher["name"]}: ' + (
                'installed' if state['installed'] else 'SETUP NEEDED') + ' — ' + ', '.join(
                    CAPABILITY_LABELS.get(item, item) for item in state['capabilities']))
        self.editor_status.setText('\n'.join(lines))
        language = assistant_language(self.store)
        self.assistant_language_box.blockSignals(True)
        self.assistant_language_box.setCurrentIndex({'ta': 0, 'en': 1, 'fr': 2}[language])
        self.assistant_language_box.blockSignals(False)
        self.refresh_routine_switches()

    def selected_project(self):
        row = self.projects_table.currentRow()
        projects = load_projects(self.store)
        if 0 <= row < len(projects):
            return projects[row]
        return None

    def refresh_routine_switches(self):
        project = self.selected_project()
        routines = trusted_routines(self.store)
        for box, key in ((self.routine_open, 'open'), (self.routine_tests, 'tests')):
            box.blockSignals(True)
            box.setChecked(bool(project and routines.get(key + ':' + project.name)))
            box.setEnabled(project is not None)
            box.blockSignals(False)
        if project is None:
            self.project_status.setText('Select a project to see its status.')
        else:
            state = project_status(project)
            parts = [f'{project.name}: {project.path}']
            if not state['exists']:
                parts.append('SETUP NEEDED — the folder is not there.')
            elif state['git']:
                parts.append('Git repository.' + (
                    f" {state['uncommitted']} uncommitted file(s) are protected when a task runs."
                    if state['dirty'] else ' Working folder is clean.'))
            else:
                parts.append('SETUP NEEDED — not a Git repository, so a task cannot be isolated.')
            self.project_status.setText(' '.join(parts))

    def add_project(self):
        """Choose a folder and save it with an editor and a test command."""
        folder = QFileDialog.getExistingDirectory(self, 'Choose the project folder')
        if not folder:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Save this project')
        form = QFormLayout(dialog)
        name_field = QLineEdit(Path(folder).name)
        form.addRow('Project name', name_field)
        editor_field = QComboBox()
        editor_field.addItems(editor_names())
        form.addRow('Editor', editor_field)
        test_field = QLineEdit()
        test_field.setPlaceholderText('e.g. pytest -q')
        form.addRow('Local test command', test_field)
        buttons = QHBoxLayout()
        save_button = QPushButton('Save project')
        cancel_button = QPushButton('Cancel')
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        form.addRow(buttons)
        save_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = name_field.text().strip()
        if not name:
            self.statusBar().showMessage('Give the project a name.', 10000)
            return
        projects = load_projects(self.store)
        projects = [item for item in projects if item.name.casefold() != name.casefold()]
        projects.append(SavedProject(name=name, path=folder, editor=editor_field.currentText(),
                                     test_command=test_field.text().strip()))
        save_projects(self.store, projects)
        self.refresh_projects_page()

    def remove_project(self):
        project = self.selected_project()
        if project is None:
            return
        if not self.confirm(Action('remove_saved_project', project.name)):
            return
        projects = [item for item in load_projects(self.store)
                    if item.name.casefold() != project.name.casefold()]
        save_projects(self.store, projects)
        self.refresh_projects_page()

    def add_launcher(self):
        """Save the owner's own editor launcher."""
        name = self.launcher_name.text().strip()
        command = self.launcher_command.text().strip()
        if not name or not command:
            self.statusBar().showMessage('Give the launcher a name and a command.', 10000)
            return
        launchers = configured_launchers(self.store)
        launchers = [item for item in launchers if item['name'].casefold() != name.casefold()]
        launchers.append({'name': name, 'command': command,
                           'capabilities': ['open_project', 'open_file']})
        from developer_studio.projects import save_configured_launchers
        save_configured_launchers(self.store, launchers)
        self.launcher_name.clear()
        self.launcher_command.clear()
        self.refresh_projects_page()

    def change_assistant_language(self, label):
        code = {'தமிழ் (Tamil)': 'ta', 'English': 'en', 'Français (French)': 'fr'}.get(label, 'ta')
        set_assistant_language(self.store, code)

    def change_routine_open(self, enabled):
        project = self.selected_project()
        if project is not None:
            set_trusted_routine(self.store, 'open:' + project.name, enabled)

    def change_routine_tests(self, enabled):
        project = self.selected_project()
        if project is not None:
            set_trusted_routine(self.store, 'tests:' + project.name, enabled)

    # ── follow-ups about the task already in flight ─────────────────────────

    def handle_follow_up(self, kind, text):
        """Answer 'continue that task', 'show the diff', 'run the tests again'
        or 'stop this task' against the task this conversation remembers."""
        context = self.memory.load()
        record = context.last_task
        if kind == 'stop':
            self.stop_saved_task(context, text)
            return
        if kind == 'show_diff':
            self.show_saved_diff(context, text)
            return
        if kind == 'run_tests':
            self.rerun_saved_tests(context, text)
            return
        self.resume_saved_task(context, text)

    def _saved_project(self, context):
        """The saved project a remembered task belongs to, or None."""
        record = context.last_task
        if not record or not record.project:
            return None
        return find_project(load_projects(self.store), record.project)

    def show_saved_diff(self, context, text):
        """Show the diff of the remembered task, read back from its worktree."""
        record = context.last_task
        allowed, reason = task_is_resumable(record)
        if not allowed:
            self.show_local_system_reply(text, reason)
            return
        from developer_studio.codex_task import reviewable_diff
        diff = reviewable_diff(record.worktree, record.starting_commit)
        if not diff.strip():
            self.show_local_system_reply(
                text, f'There is no difference in {record.worktree} against '
                      f'{record.starting_commit[:8]}.')
            return
        self.show_local_system_reply(text, diff)

    def rerun_saved_tests(self, context, text):
        """Run the remembered task's tests again, in its worktree."""
        record = context.last_task
        allowed, reason = task_is_resumable(record)
        if not allowed:
            self.show_local_system_reply(text, reason)
            return
        project = self._saved_project(context)
        if project is None:
            self.show_local_system_reply(
                text, f'The project {record.project} is not saved any more.')
            return
        command = project.test_command
        if not command:
            self.show_local_system_reply(
                text, f'No test command is configured for {project.name}.')
            return
        action = Action('run_project_tests', f'{project.name}: {command}')
        self.coding_action_gate(
            action,
            lambda: self.start_test_run(project, Path(record.worktree), command),
            trusted=self.test_command_trusted(project, command))

    def stop_saved_task(self, context, text):
        """Stop the remembered task without stopping the whole assistant."""
        record = context.last_task
        if self.coding_worker is not None:
            self.coding_worker.requestInterruption()
        if self.test_worker is not None:
            self.test_worker.requestInterruption()
        if record and record.ident:
            self.store.finish(record.ident, 'cancelled', 'Cancelled by the owner.')
        self.show_local_system_reply(
            text, 'The task is stopped. Nothing was pushed, merged or published.')

    def resume_saved_task(self, context, text):
        """Bring the remembered task back, after checking it is still valid."""
        record = context.last_task
        allowed, reason = task_is_resumable(record)
        if not allowed:
            self.show_local_system_reply(text, reason)
            return
        project = self._saved_project(context)
        if project is None:
            self.show_local_system_reply(
                text, f'The project {record.project} is not saved any more, so the task '
                      'cannot be continued. Save it again in Settings & Plugins.')
            return
        # The card comes back with what is known about the task, so the owner
        # can carry on with it.
        steps = [{'key': 'resume', 'done': True, 'state': 'done',
                  'label': f'Continue {record.project}: {record.change or "the saved task"}',
                  'approval': False}]
        self.coding = {
            'request': parse_coding_request(record.change or record.project,
                                            [project], editor_from_text),
            'project': project, 'editor': record.editor or project.editor,
            'editor_status': editor_status(record.editor or project.editor, None,
                                           self.assistant_language),
            'steps': steps, 'index': len(steps), 'outcome': None, 'text': text,
        }
        self.chat_task_id = record.ident
        self.render_coding_card()
        self.show_local_system_reply(
            text, f'Continuing {record.project}. The worktree is {record.worktree}. '
                  'Say what to change next, or use Review diff, Run tests or Open project.')

    def coding_request(self, text):
        """The coding request in a chat sentence, or None.

        A sentence is only a coding request when it names a saved project.
        Anything else is ordinary chat and goes to the assistant, because a
        request that might be a coding task must never swallow a question.

        When the sentence names more than one saved project, JARVIS does not
        guess: it asks which one, and the answer is treated as the answer to
        that question.
        """
        projects = load_projects(self.store)
        if not projects:
            return None
        matches = match_projects(text, projects)
        if len(matches) > 1:
            self.ask_which_project(text, matches)
            return None
        # The project this conversation is about is the default, so a request
        # that names no project still knows where to go.
        remembered = self.memory.load().project
        if remembered and find_project(projects, remembered) is None:
            remembered = ''
        request = parse_coding_request(text, projects, editor_from_text,
                                       default_project=remembered)
        if request.question:
            # The request is not clear enough to act on: ask one short
            # question instead of guessing.
            self.ask_clarification(text, request, projects)
            return None
        if request.project and (request.open_project or request.make_change or request.run_tests):
            return request
        return None

    def ask_which_project(self, text, candidates):
        """Ask a short question when more than one project could be meant."""
        names = ', '.join(project.name for project in candidates)
        self.pending_clarification = {'kind': 'project', 'text': text,
                                      'candidates': list(candidates)}
        self.show_local_system_reply(
            text, f'Which project do you mean? Choose one: {names}.')

    def ask_clarification(self, text, request, projects):
        """Ask the short question the request needs before anything happens.

        Two kinds: the project to work on, and what to do in it. The answer
        is folded back into the request, so the task that starts is the one
        the owner actually described.
        """
        if request.question_kind == 'project':
            names = ', '.join(project.name for project in projects[:6])
            self.pending_clarification = {'kind': 'project', 'text': text,
                                          'candidates': list(projects[:6])}
            self.show_local_system_reply(
                text, f'Which saved project is this for? Choose one: {names}.')
            return
        self.pending_clarification = {'kind': 'merge', 'text': text,
                                      'question': request.question}
        self.show_local_system_reply(text, request.question)

    def answer_clarification(self, text):
        """Use the owner's answer to finish the request, and start the task.

        When the question was about the project, the answer has to name one
        of them. When the question was about what to do, the answer is
        folded back into the request, so "fix the contact form validation"
        becomes the change the task works on.
        """
        pending = self.pending_clarification
        self.pending_clarification = None
        if pending is None:
            return False
        if pending['kind'] == 'merge':
            # The owner said what to do: read the request again with it.
            combined = pending['text'] + ' ' + text
            request = self.coding_request(combined)
            if request is not None:
                self.start_coding_task(request, combined)
            return True
        candidates = pending['candidates']
        matches = match_projects(text, candidates)
        if len(matches) != 1:
            self.pending_clarification = pending
            self.show_local_system_reply(
                text, 'Say the project name exactly, one of: '
                + ', '.join(project.name for project in candidates) + '.')
            return True
        project = matches[0]
        request = parse_coding_request(pending['text'], [project], editor_from_text)
        if not request.project:
            request = replace(request, project=project.name)
        self.start_coding_task(request, pending['text'])
        return True

    def coding_task_active(self):
        """True when a coding task is running or waiting for approval.

        A second chat request must never take over a task that is already in
        flight: the running job would report its result into the new task's
        card, and a pending approval would be silently lost.
        """
        if self.coding_worker is not None or self.test_worker is not None:
            return True
        if getattr(self, 'coding_pending', None) is not None:
            return True
        if self.coding is not None:
            steps = self.coding.get('steps', [])
            if self.coding.get('index', 0) < len(steps):
                return True
        return False

    def start_coding_task(self, request, text):
        """Show the task card and start the first step."""
        if self.coding_task_active():
            self.show_local_system_reply(
                text, 'A task is already running or waiting for approval. '
                      'Finish or decline it before starting another.')
            return
        projects = load_projects(self.store)
        project = find_project(projects, request.project)
        if project is None:
            self.show_local_system_reply(text, 'That project is not saved any more.')
            return
        launchers = configured_launchers(self.store)
        editor = request.editor or project.editor
        configured = next((item for item in launchers if item['name'] == editor), None)
        status = editor_status(editor, configured, self.assistant_language)
        routines = trusted_routines(self.store)
        steps = []
        if request.open_project:
            steps.append({
                'key': 'open', 'done': False, 'state': 'waiting',
                'label': summary_labels(self.assistant_language)['step_open'].format(
                    project=project.name, editor=editor),
                'approval': not routines.get('open:' + project.name),
            })
        if request.make_change:
            steps.append({
                'key': 'change', 'done': False, 'state': 'waiting',
                'label': summary_labels(self.assistant_language)['step_change'].format(
                    change=request.change or project.name),
                'approval': True,
            })
        if request.run_tests:
            steps.append({
                'key': 'tests', 'done': False, 'state': 'waiting',
                'label': summary_labels(self.assistant_language)['step_tests'].format(
                    command=project.test_command or '(none configured)'),
                # A test command the owner has not trusted is approved on its
                # own, separately from the change that produced it.
                'approval': not (routines.get('tests:' + project.name)
                                 and project.test_command),
            })
        # The project is looked at before the model is called, so the report
        # can say what was found instead of what was assumed. This reads
        # files and compiles nothing: it never runs the project.
        inspection = inspect_project(project.path)
        self.coding = {
            'request': request, 'project': project, 'editor': editor,
            'editor_status': status, 'steps': steps, 'index': 0,
            'outcome': None, 'text': text,
            'inspection': inspection,
            'inspection_findings': inspection.problems_text(),
        }
        # The task is recorded in the task history from the moment it starts,
        # so a task that is interrupted still leaves a trace.
        self.chat_task_id = self.store.task(
            'codex_task', f'{project.name} · {project.path} · {request.change or project.name}')
        self.store.finish(self.chat_task_id, 'running')
        # Remember what this conversation is about, so a follow-up that names
        # no project still knows where to go.
        language = detect_reply_language(text) or self.assistant_language
        if language:
            self.assistant_language = language
            set_assistant_language(self.store, language)
        self.memory.remember(project=project.name, editor=editor, language=language)
        self.render_coding_card()
        self.advance_coding_task()

    def coding_action(self, step):
        """The exact action and target the owner approves for this step.

        The target says which project, which folder and which change, so the
        owner can see what is about to happen before it happens.
        """
        coding = self.coding
        project = coding['project']
        request = coding['request']
        if step['key'] == 'open':
            return Action('open_project', f'{coding["editor"]} · {project.path}')
        if step['key'] == 'tests':
            return Action('run_project_tests', f'{project.name}: {project.test_command}')
        change = request.change or project.name
        return Action('codex_task', f'{project.name} · {project.path} · {change}')

    def render_coding_card(self):
        """The task card: project, requested change and the steps."""
        coding = self.coding
        if coding is None:
            self.chat_task_card.hide()
            return
        project = coding['project']
        request = coding['request']
        status = coding['editor_status']
        labels = summary_labels(self.assistant_language)
        lines = [f"{labels['task']} · {project.name}", f"{labels['folder']}: {project.path}"]
        editor_line = f"{labels['editor']}: {coding['editor']}"
        if status['installed']:
            editor_line += f" — {status['path']}"
        else:
            editor_line += ' — ' + labels['setup_needed']
        lines.append(editor_line)
        if not status['installed'] and status['setup']:
            lines.append(status['setup'])
        if request.change:
            lines.append(labels['change'] + ': ' + request.change)
        inspection = coding.get('inspection')
        if inspection is not None:
            found = f'{inspection.files_inspected} file(s) looked at'
            if inspection.problem_count:
                found += f', {inspection.problem_count} problem(s) found'
            lines.append(found)
            for problem in inspection.problems[:5]:
                lines.append('  ' + str(problem))
            if inspection.problem_count > 5:
                lines.append(f'  … and {inspection.problem_count - 5} more')
        lines.append('')
        for number, step in enumerate(coding['steps'], 1):
            mark = {'done': labels['done'], 'running': labels['running'],
                    'waiting': labels['waiting'], 'declined': labels['declined'],
                    'failed': labels['failed']}.get(step['state'], labels['waiting'])
            if step['state'] == 'waiting' and coding.get('pending_step') is step:
                mark = labels['awaiting_approval']
            lines.append(f'{number}. {step["label"]}  [{mark}]')
        outcome = coding.get('outcome')
        if outcome is not None:
            labels = summary_labels(self.assistant_language)
            lines.append('')
            lines.append(outcome.message)
            if outcome.changed_files:
                lines.append(labels['changed'] + ': ' + ', '.join(outcome.changed_files))
            else:
                lines.append(labels['changed'] + ': ' + labels['none'])
            if outcome.test_status not in ('', 'not run'):
                lines.append(f"{labels['tests']}: {outcome.test_status}")
            if outcome.protected:
                lines.append(labels['protected'] + ': ' + ', '.join(outcome.protected))
            if outcome.files_inspected:
                lines.append('Files looked at: ' + str(outcome.files_inspected))
            if outcome.problems_found:
                lines.append('Problems found: ' + str(outcome.problems_found))
        self.chat_task_text.setText('\n'.join(lines))
        self.chat_task_card.show()
        self.chat_task_diff.setEnabled(bool(outcome and outcome.diff))
        self.chat_task_tests.setEnabled(bool(outcome and outcome.worktree))
        self.chat_task_open.setEnabled(True)
        # The owner accepts or rejects the change once there is one, and not
        # before, so the buttons cannot be pressed on a task that has not
        # produced anything.
        decided = bool(outcome and outcome.diff and not outcome.reviewed)
        self.chat_task_accept.setEnabled(decided)
        self.chat_task_reject.setEnabled(decided)

    def advance_coding_task(self):
        """Run the next step, or ask for approval when it needs one."""
        coding = self.coding
        if coding is None:
            return
        while coding['index'] < len(coding['steps']):
            step = coding['steps'][coding['index']]
            if step['done']:
                coding['index'] += 1
                continue
            break
        if coding['index'] >= len(coding['steps']):
            self.finish_coding_task()
            return
        step = coding['steps'][coding['index']]
        step['state'] = 'running'
        self.render_coding_card()
        if step['key'] == 'open':
            self.step_open_project(step)
        elif step['key'] == 'change':
            self.step_codex_change(step)
        else:
            self.step_run_tests(step)

    def coding_configured_launcher(self):
        """The owner's own launcher for this editor, when there is one."""
        coding = self.coding
        if coding is None:
            return None
        launchers = configured_launchers(self.store)
        return next((item for item in launchers if item['name'] == coding['editor']), None)

    def step_open_project(self, step):
        coding = self.coding
        project = coding['project']
        if step['approval']:
            self.queue_coding_approval(
                step, self.coding_action(step),
                lambda: open_project_in_editor(coding['editor'], project.path,
                                               self.coding_configured_launcher()))
            return
        self.run_coding_step(
            step, lambda: open_project_in_editor(coding['editor'], project.path,
                                                 self.coding_configured_launcher()))

    def step_codex_change(self, step):
        # A change always needs approval: it writes code and sends project
        # data to a provider.
        self.queue_coding_approval(step, self.coding_action(step), None)

    def step_run_tests(self, step):
        coding = self.coding
        project = coding['project']
        if not project.test_command:
            step['done'] = True
            step['state'] = 'done'
            self.render_coding_card()
            self.advance_coding_task()
            return
        if step['approval']:
            # A test command the owner has not trusted is approved on its own,
            # separately from the change that produced it.
            self.queue_coding_approval(step, self.coding_action(step), None)
            return
        self.run_coding_tests_for(project, project.folder)

    def coding_action_gate(self, action, operation, *, trusted=False, read_only=False):
        """Run one task-card action through the approval gateway and Emergency Stop.

        EVERY action the task card offers comes through here. An action that
        changes something needs an approval unless the owner has trusted that
        exact routine, and it is then executed through the gateway, so the
        one-use approval token and the Emergency Stop checks apply. A
        read-only action still checks the stop, because an assistant that has
        been stopped should not quietly keep working.
        """
        coding = self.coding
        if coding is None:
            return
        try:
            ticket = self.policy.ticket()
            self.policy.check(ticket)
        except Stopped as error:
            self.show_local_system_reply(coding['text'], str(error))
            return
        if read_only:
            self.show_local_system_reply(coding['text'], operation())
            return
        if trusted:
            try:
                result = self.gateway.run(action, lambda _action: True, operation)
            except (Denied, Stopped, ValueError, OSError, RuntimeError) as error:
                result = str(error)
            self.show_local_system_reply(coding['text'], result)
            return
        self.queue_coding_approval(None, action, operation)

    def queue_coding_approval(self, step, action, operation=None):
        """Ask for approval, showing the exact action and its target.

        `step` is None for an action the owner started from the task card
        rather than from the task plan.
        """
        try:
            ticket = self.policy.ticket()
        except Stopped as error:
            self.show_local_system_reply(self.coding['text'], str(error))
            return
        self.coding_pending = (step, ticket, action, operation)
        if self.omega is not None:
            self.omega.set_approval(True)
        if self.coding is not None:
            self.coding['pending_step'] = step
        if step is not None:
            step['state'] = 'waiting'
        self.render_coding_card()
        self.chat_task_text.setText(
            self.chat_task_text.text()
            + f'\n\n{action.kind}: {action.target}\nApprove this task or decline below.')
        self.chat_task_approve.show()
        self.chat_task_decline.show()

    def finish_coding_approval(self, approved):
        """Run or refuse the whole task."""
        pending = getattr(self, 'coding_pending', None)
        self.coding_pending = None
        if self.omega is not None:
            self.omega.set_approval(False)
        if self.coding is not None:
            self.coding['pending_step'] = None
        self.chat_task_approve.hide()
        self.chat_task_decline.hide()
        if pending is None:
            return
        step, ticket, action, operation = pending
        coding = self.coding
        if coding is None:
            return
        try:
            self.policy.check(ticket)
        except Stopped as error:
            self.show_local_system_reply(coding['text'], str(error))
            return
        if not approved:
            if step is None:
                # An action the owner started from the task card was declined.
                self.show_local_system_reply(coding['text'], 'Declined. Nothing was changed.')
                return
            # Declining one step declines the whole task. Nothing is left half
            # done and nothing is changed.
            for item in coding['steps']:
                item['state'] = 'declined'
                item['done'] = True
            coding['index'] = len(coding['steps'])
            self.render_coding_card()
            self.show_local_system_reply(coding['text'], 'Declined. Nothing was changed.')
            self.finish_coding_task()
            return
        if step is None:
            # A card action the owner approved.
            try:
                result = self.gateway.run(action, lambda _action: True, operation)
            except (Denied, Stopped, ValueError, OSError, RuntimeError) as error:
                result = str(error)
            self.show_local_system_reply(coding['text'], result)
            return
        if step['key'] == 'change':
            self.start_codex_task(step)
        elif step['key'] == 'tests':
            self.run_coding_tests_for(coding['project'], self.coding_test_folder())
        else:
            self.run_coding_step(step,
                                 lambda: open_project_in_editor(coding['editor'],
                                                               coding['project'].path))

    def run_coding_step(self, step, operation):
        """Run one approved routine action."""
        coding = self.coding
        try:
            result = operation()
            step['state'] = 'done'
            step['done'] = True
            coding['index'] += 1
            self.render_coding_card()
            self.show_local_system_reply(coding['text'], result)
        except (Denied, Stopped, ValueError, OSError, RuntimeError) as error:
            step['state'] = 'failed'
            step['done'] = True
            coding['index'] += 1
            self.render_coding_card()
            self.show_local_system_reply(coding['text'], str(error))
            if step['key'] == 'open':
                # A missing editor does not stop the work. The task itself runs
                # in a worktree and does not need the editor.
                self.statusBar().showMessage(str(error), 15000)
                self.advance_coding_task()
                return
        self.advance_coding_task()

    def start_codex_task(self, step):
        """Start the Codex task in an isolated worktree."""
        coding = self.coding
        project = coding['project']
        request = coding['request']
        if self.worker is not None:
            self.show_local_system_reply(coding['text'],
                                         'Wait for the current request to finish.')
            return
        # The change does NOT run the tests. An untrusted test command needs
        # its own approval, and a test command bundled inside the change
        # approval would never get one.
        task = CodexTask(project, request.change or project.name,
                         test_command='',
                         worktree_root=self.root / 'worktrees',
                         codex_path=None,
                         language=self.assistant_language,
                         findings=coding.get('inspection_findings', ''),
                         files_inspected=coding['inspection'].files_inspected,
                         problems_found=coding['inspection'].problem_count)
        self.worker_kind = 'coding'
        self.coding_worker = CodingTaskWorker(task, self.policy, self.policy.ticket())
        self.coding_worker.progress.connect(self.on_coding_progress)
        self.coding_worker.result.connect(self.on_coding_result)
        self.coding_worker.finished.connect(self.on_coding_finished)
        if self.omega is not None:
            # The Omega presentation shows that coding work is in progress.
            # It is refreshed AFTER the worker exists, so the state is real.
            self.omega.refresh_state()
        step['state'] = 'running'
        self.render_coding_card()
        self.coding_worker.start()

    def on_coding_progress(self, step, text):
        """Show one step of the task as it happens."""
        coding = self.coding
        if coding is None:
            return
        for item in coding['steps']:
            if item['key'] == step:
                item['state'] = 'running'
        self.render_coding_card()
        self.store.message(self.session, 'system', '· ' + text)
        self.render_chat()

    def on_coding_result(self, outcome):
        coding = self.coding
        if coding is None:
            return
        coding['outcome'] = outcome
        for step in coding['steps']:
            if step['key'] == 'change' and step['state'] == 'running':
                step['state'] = 'done' if outcome.status == 'completed' else 'failed'
                step['done'] = True
        self.render_coding_card()

    def on_coding_finished(self):
        worker = self.coding_worker
        self.coding_worker = None
        if worker is not None:
            worker.deleteLater()
        if self.omega is not None:
            self.omega.refresh_state()
        self.advance_coding_task()
        if self.close_when_done and self.coding_worker is None and self.test_worker is None:
            self.close()

    def record_coding_history(self, outcome=None):
        """Write the task's status, test result and worktree into the history.

        The history row is updated as the task goes, so a task that is
        interrupted still leaves a trace of what it was and where it worked.
        """
        if self.chat_task_id is None:
            return
        coding = self.coding or {}
        outcome = outcome if outcome is not None else coding.get('outcome')
        if outcome is None:
            self.store.finish(self.chat_task_id, 'running')
            return
        status = outcome.status
        if outcome.test_status == 'failed':
            # The job was to make the change AND prove it. A failing test is a
            # failed task, and the history says so.
            status = 'failed'
        elif outcome.test_status == 'cancelled':
            status = 'cancelled'
        detail = 'tests=' + (outcome.test_status or 'not run')
        if outcome.reviewed:
            detail += ' · reviewed=' + outcome.reviewed
        if outcome.files_inspected:
            detail += ' · looked_at=' + str(outcome.files_inspected)
        if outcome.changed_files:
            detail += ' · files=' + str(len(outcome.changed_files))
        if outcome.worktree:
            detail += ' · worktree=' + outcome.worktree
        if outcome.starting_commit:
            detail += ' · from=' + outcome.starting_commit[:8]
        self.store.finish(self.chat_task_id, status, detail)

    def finish_coding_task(self):
        """Close the task card with the result in the conversation.

        The report says what actually happened: the files that changed, the
        diff to review, the test outcome and where the work was saved. It is
        written in the language the owner asked the answer in.
        """
        coding = self.coding
        if coding is None:
            return
        outcome = coding.get('outcome')
        if outcome is not None:
            labels = summary_labels(self.assistant_language)
            summary = outcome.message
            if outcome.changed_files:
                summary += '\n' + labels['changed'] + ': ' + ', '.join(outcome.changed_files)
            else:
                summary += '\n' + labels['changed'] + ': ' + labels['none']
            # The test result is ALWAYS in the final result, pass or fail.
            summary += '\n' + labels['tests'] + ': ' + (outcome.test_status or 'not run')
            if outcome.diff:
                # The whole diff goes in, but it is bounded so one enormous
                # change cannot fill the conversation.
                diff = outcome.diff
                if len(diff) > 8000:
                    diff = diff[:8000] + '\n… the diff was shortened. Use Review diff for all of it.'
                summary += '\n' + labels['diff'] + ':\n' + diff
            if outcome.worktree:
                summary += '\n' + labels['saved'] + ': ' + outcome.worktree
            if outcome.refused:
                summary += ('\nPut back (protected, not changed): '
                            + ', '.join(outcome.refused))
            self.store.message(self.session, 'system', summary)
            self.render_chat()
        self.record_coding_history(outcome)
        self.remember_finished_task(outcome)
        self.refresh_archives()
        self.refresh_history()

    def remember_finished_task(self, outcome):
        """Keep the finished task so the owner can continue it later."""
        coding = self.coding
        if coding is None or outcome is None:
            return
        project = coding['project']
        record = TaskRecord(
            ident=self.chat_task_id or '',
            project=project.name,
            folder=project.path,
            editor=coding.get('editor') or project.editor,
            worktree=outcome.worktree,
            starting_commit=outcome.starting_commit,
            change=coding['request'].change or project.name,
            test_command=project.test_command,
            status=outcome.status,
            created=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        )
        self.memory.remember_task(record)

    def retry_failed_plan_step(self):
        """Run only the step of a plan that failed."""
        self.conversation_plan.retry_failed()

    def review_coding_diff(self):
        """Show the reviewable diff of the last task.

        Reading changes nothing, so it needs no approval, but it still goes
        through the gate so a stopped assistant stops answering.
        """
        coding = self.coding
        if coding is None or not coding.get('outcome'):
            return
        outcome = coding['outcome']
        if not outcome.diff:
            self.statusBar().showMessage('There is no diff to review.', 10000)
            return
        self.coding_action_gate(
            Action('review_diff', f'{coding["project"].name} · {outcome.starting_commit[:8]}'),
            lambda: outcome.diff, read_only=True)

    def accept_coding_change(self):
        """The owner says the change is wanted.

        Accepting does not touch the owner's working folder. The change
        lives in the worktree that was made for it, and the owner brings
        it in themselves, because their own uncommitted work is in the way
        and JARVIS does not put a change under it without being asked.
        """
        coding = self.coding
        if coding is None:
            return
        outcome = coding.get('outcome')
        if outcome is None or not outcome.diff:
            self.statusBar().showMessage('There is no change to accept.', 10000)
            return
        project = coding['project']

        def operation():
            outcome.reviewed = 'accepted'
            self.store.finish(self.chat_task_id, 'accepted')
            self.render_coding_card()
            where = outcome.worktree or str(project.folder)
            self.show_local_system_reply(
                coding['text'],
                'You accepted the change. It is kept in ' + where + ' and your own '
                'project folder was not touched. To bring it in, review the diff '
                'and apply it yourself, for example: '
                f'git -C "{project.folder}" diff --no-index '
                f'"{where}" "{project.folder}" > change.patch, then apply that patch.')
            return 'The change was accepted and kept in the worktree.'

        self.coding_action_gate(
            Action('accept_coding_change', f'{project.name} · keep the change in the worktree'),
            operation)

    def reject_coding_change(self):
        """The owner says the change is not wanted.

        The worktree is kept, because it holds work that may still be worth
        reading, and the owner is told where it is. Nothing of the owner's
        own is touched either way.
        """
        coding = self.coding
        if coding is None:
            return
        outcome = coding.get('outcome')
        if outcome is None or not outcome.diff:
            self.statusBar().showMessage('There is no change to reject.', 10000)
            return
        project = coding['project']

        def operation():
            outcome.reviewed = 'rejected'
            self.store.finish(self.chat_task_id, 'rejected')
            self.render_coding_card()
            where = outcome.worktree or str(project.folder)
            self.show_local_system_reply(
                coding['text'],
                'You rejected the change. Your project was not touched. The work is '
                'still in ' + where + ' so you can read it; delete that folder when '
                'you do not want it.')
            return 'The change was rejected and nothing was applied.'

        self.coding_action_gate(
            Action('reject_coding_change', f'{project.name} · do not use the change'),
            operation)

    def coding_test_folder(self):
        """Where the tests run: the task worktree if there is one."""
        coding = self.coding
        if coding is None:
            return None
        outcome = coding.get('outcome')
        if outcome is not None and outcome.worktree:
            return Path(outcome.worktree)
        return coding['project'].folder

    def test_command_trusted(self, project, command):
        """True when this exact command is the saved one AND the owner trusts it.

        A command the owner typed somewhere else is never trusted, even when
        the saved routine is.
        """
        saved = (project.test_command or '').strip()
        if not saved or (command or '').strip() != saved:
            return False
        return routine_allowed(self.store, 'tests:' + project.name)

    def run_coding_tests(self):
        """Run the project's configured tests again, from the task card."""
        coding = self.coding
        if coding is None:
            return
        project = coding['project']
        command = project.test_command
        if not command:
            self.show_local_system_reply(project.name,
                                         'No test command is configured for this project.')
            return
        action = Action('run_project_tests', f'{project.name}: {command}')
        self.coding_action_gate(
            action,
            lambda: self.start_test_run(project, self.coding_test_folder(), command),
            trusted=self.test_command_trusted(project, command))

    def run_coding_tests_for(self, project, folder):
        """Start the project's configured tests in the background."""
        command = project.test_command
        if not command:
            step = self._current_test_step()
            if step is not None:
                step['done'] = True
                step['state'] = 'done'
            self.render_coding_card()
            self.advance_coding_task()
            return
        self.start_test_run(project, folder, command)

    def _current_test_step(self):
        coding = self.coding
        if coding is None:
            return None
        for step in coding['steps']:
            if step['key'] == 'tests':
                return step
        return None

    def start_test_run(self, project, folder, command):
        """Run the tests on a worker thread, where they can be cancelled."""
        if self.test_worker is not None:
            raise RuntimeError('A test run is already going.')
        self.test_worker = TestRunWorker(folder, command, self.policy, self.policy.ticket())
        self.test_worker.result.connect(self.on_test_result)
        self.test_worker.finished.connect(self.on_test_finished)
        step = self._current_test_step()
        if step is not None:
            step['state'] = 'running'
        self.render_coding_card()
        self.test_worker.start()
        return f'Tests are running in {folder}.'

    def on_test_result(self, status, output, payload=None):
        """Record the test result and show it in the conversation."""
        coding = self.coding
        if coding is None:
            return
        outcome = coding.get('outcome')
        if outcome is None:
            outcome = TaskOutcome(status='completed')
            coding['outcome'] = outcome
        outcome.test_status = status
        outcome.test_output = output
        step = self._current_test_step()
        if step is not None:
            step['state'] = 'done' if status in ('passed', 'failed', 'not configured') else 'failed'
            step['done'] = True
        self.render_coding_card()
        self.record_coding_history(outcome)
        project = coding['project']
        self.show_local_system_reply(
            project.name,
            f'Tests {status} in {self.coding_test_folder()}.\n\n' + (output or '(no output)'))

    def on_test_finished(self):
        worker = self.test_worker
        self.test_worker = None
        if worker is not None:
            worker.deleteLater()
        self.advance_coding_task()
        if self.close_when_done and self.coding_worker is None and self.test_worker is None:
            self.close()

    def mission_answered(self, mission, failure=None):
        """A mission that came from the conversation answers in it.

        The answer is stored in the conversation so it survives a
        restart, and the steps that produced it stay on the Mission
        Control page. A mission that did not finish says so plainly and
        does not pretend to have an answer.
        """
        if mission is None:
            reply = ('The mission did not finish. '
                     + (failure or 'See Mission Control for the steps that ran.'))
        elif mission.status == 'completed' and mission.answer:
            reply = mission.answer
        else:
            reply = ('The mission stopped: '
                     + (mission.events[-1].detail if mission.events else 'no reason given')
                     + '. The steps that ran are on the Mission Control page.')
        self.store.message(self.session, 'assistant', reply)
        self.render_chat()
        self.show_hud_text(reply)
        if self.read_replies.isChecked() and not self.policy.stopped:
            self.voice_panel.speak_response(reply[:600])

    def mission_finished(self):
        """The mission stopped, so the window may close if it was waiting."""
        controller = getattr(self, 'mission_controller', None)
        if controller is not None and controller.worker is not None:
            controller.worker.deleteLater()
            controller.worker = None
        if (self.close_when_done and self.coding_worker is None and self.test_worker is None
                and self.worker is None):
            self.close()

    def open_coding_project(self):
        """Open the project folder in the editor the owner saved.

        Launching a program is not a read-only action, so it goes through the
        approval gateway unless the owner has trusted opening this project.
        """
        coding = self.coding
        if coding is None:
            return
        project = coding['project']
        configured = self.coding_configured_launcher()
        action = Action('open_project', f'{coding["editor"]} · {project.path}')

        def operation():
            try:
                return open_project_in_editor(coding['editor'], project.path, configured)
            except (ValueError, RuntimeError, OSError) as error:
                return str(error)

        self.coding_action_gate(
            action, operation,
            trusted=routine_allowed(self.store, 'open:' + project.name))

    # ── the review of prepared changes ─────────────────────────────────────

    def installation_root(self):
        """The folder JARVIS is installed in."""
        return installation_root()

    def development_test_command(self):
        """The command that tests a prepared change."""
        return self.store.get('development_test_command') or 'pytest -q'

    def set_paused(self, paused):
        """Pause or resume the background work.

        Pausing stops the automatic source check and the background
        preparation of changes. Nothing is closed and nothing is lost: the
        saved work stays in the task history and can be resumed.
        """
        self.paused = bool(paused)
        self.store.set('paused', self.paused)
        if self.paused:
            self.release_checker.pause()
            if self.improvement_worker is not None:
                self.improvement_worker.requestInterruption()
            self.statusBar().showMessage('JARVIS is paused in the system tray.', 10000)
        else:
            self.release_checker.resume()
            self.statusBar().showMessage('JARVIS is running again.', 10000)

    def keep_running_in_tray(self):
        """True when closing the window keeps JARVIS in the tray."""
        return bool(self.store.get('keep_running_in_tray', False))

    def refresh_review(self):
        """Show the prepared changes again, after one of them changed."""
        widget = self.pages.widget(self.page_indices['Review changes'])
        if isinstance(widget, QScrollArea):
            widget = widget.widget()
        if hasattr(widget, 'refresh'):
            widget.refresh()

    def prepared_improvements(self):
        """The improvements that are ready for the owner to review."""
        return prepared_tasks(self.store)

    def candidate_diff(self, candidate):
        """The diff between the running version and a prepared revision."""
        from core.candidates import prepared_files
        from core.updates import changed_files, release_path, read_state
        try:
            files = prepared_files(self.installation_root(), candidate.revision)
        except Exception:
            return ''
        current = release_path(self.installation_root(), read_state(self.installation_root())['active'])
        if not changed_files(current, files):
            return 'This revision is the one that is already running.'
        from core.candidates import unified_diff
        return unified_diff(current, files)

    def tray_note_text(self):
        """What the owner is told about the background session."""
        if not startup_supported():
            return ('Starting at sign-in is a Windows setting. '
                    'The system tray controls are available on Windows.')
        if start_at_signin_enabled():
            return 'JARVIS starts when you sign in to Windows.'
        return 'JARVIS does not start when you sign in to Windows.'

    def on_start_at_signin(self, enabled):
        """Turn the start-at-sign-in setting on or off."""
        try:
            changed = set_start_at_signin(bool(enabled))
        except StartupError as error:
            changed = False
            self.statusBar().showMessage(str(error), 15000)
        self.start_at_signin.setChecked(changed)
        self.tray_note.setText(self.tray_note_text())

    # ── preparing an improvement to JARVIS itself ────────────────────────────

    def set_auto_maintenance(self, enabled):
        if not enabled:
            self.store.set('auto_maintenance', False)
            if self.improvement_worker is not None and self.improvement_worker.automatic:
                self.improvement_worker.requestInterruption()
            return
        provider = self.selected_coding_provider()
        action = Action('enable_automatic_guide_proposals',
                        f'{provider} · may read project source to update docs/UPDATES.md')
        self.notify(lambda: self.gateway.run(action, self.confirm,
                    lambda: self.store.set('auto_maintenance', provider)))
        blocked = self.auto_maintenance.blockSignals(True)
        self.auto_maintenance.setChecked(bool(self.store.get('auto_maintenance', False)))
        self.auto_maintenance.blockSignals(blocked)

    def check_maintenance(self):
        provider = self.store.get('auto_maintenance')
        if (not provider or self.paused or self.close_when_done or self.policy.stopped
                or self.improvement_worker is not None or self.release_checker.source_worker is not None):
            return
        try:
            routing.require_coding_provider(provider)
            root = self.installation_root()
            state = read_state(root)
            active = release_path(root, state['active'])
            goal = maintenance_goal(active)
        except (OSError, ValueError):
            return
        if not goal or self.store.get('last_maintenance_goal') == [state['active'], goal]:
            return
        self.store.set('last_maintenance_goal', [state['active'], goal])
        self.run_improvement(goal, provider, automatic=True)

    def start_improvement(self):
        """Ask a coding provider to prepare an improvement, in the background."""
        if self.improvement_worker is not None:
            self.statusBar().showMessage('A change is already being prepared.', 10000)
            return
        goal = self.improvement_goal.text().strip()
        if not goal or len(goal) > 8000:
            self.statusBar().showMessage('Describe the change in 1–8,000 characters.', 10000)
            return
        provider = self.selected_coding_provider()
        action = Action('prepare_code_change',
                        f'{provider} · {goal[:120]} · sends project files to {provider} for review')

        def operation():
            self.improvement_goal.clear()
            self.run_improvement(goal, provider)

        self.notify(lambda: self.gateway.run(action, self.confirm, operation))

    def retry_improvement(self):
        pending = resumable_tasks(self.store)
        if not pending:
            self.statusBar().showMessage('No interrupted improvement is waiting.', 10000)
            return
        task = pending[0]
        provider = self.selected_coding_provider()
        action = Action('retry_saved_improvement',
                        f'{provider} · {task.goal[:120]} · sends project files to this provider')
        self.notify(lambda: self.gateway.run(action, self.confirm,
                    lambda: self.run_improvement(task.goal, provider, task=task)))

    def run_improvement(self, goal, provider, *, automatic=False, task=None):
        """Start the background work for one improvement."""
        if self.improvement_worker is not None:
            self.statusBar().showMessage('A change is already being prepared.', 10000)
            return
        worker = ImprovementWorker(self, goal, provider, parent=self, automatic=automatic, task=task)
        self.improvement_worker = worker
        worker.prepared.connect(self.on_improvement_prepared)
        worker.message.connect(lambda text: self.statusBar().showMessage(text, 20000))
        worker.finished.connect(self.finish_improvement_worker)
        worker.start()

    def on_improvement_prepared(self, improvement):
        """A prepared change is ready to be looked at."""
        self.statusBar().showMessage(
            f'Revision {improvement.short} is prepared. Review it before it is used.', 20000)
        review = self.pages.widget(self.page_indices['Review changes'])
        if isinstance(review, QScrollArea):
            review = review.widget()
        if hasattr(review, 'refresh'):
            review.refresh()

    def finish_improvement_worker(self):
        """The background work has ended."""
        worker = self.improvement_worker
        self.improvement_worker = None
        if worker is not None:
            worker.deleteLater()
        if self.close_when_done:
            self.close()

    def switch_coding_provider(self, goal, provider):
        """Prepare a change with the other coding provider, after approval.

        The owner asked for the other provider, so the switch is an approved
        action like any other. The task that was saved is the one that is
        continued.
        """
        action = Action('use_other_coding_provider',
                        f'{provider} · {goal[:120]} · sends project files to {provider} for review')

        def operation():
            # The owner approved the switch, so this provider is the one that
            # does the work from now on.
            routing.set_coding_provider(self.store, provider)
            self.improvement_goal.setText(goal)
            self.run_improvement(goal, provider)

        self.notify(lambda: self.gateway.run(action, self.confirm, operation))

    def confirm(self, action):
        extra = ('\nContent SHA-256: ' + action.digest) if action.digest else ''
        if self.omega is not None:
            self.omega.set_approval(True)
        try:
            return QMessageBox.question(self, 'Approve one action?',
                f'{action.kind}: {action.target}{extra}\n\nApprove this action once?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        finally:
            if self.omega is not None:
                self.omega.set_approval(False)

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
        """Put the recommended model of the chosen profile back."""
        provider = self.provider.currentText()
        profile = self.provider_profile.currentData()
        if profile:
            self.model.setText(profile_models.model_for(provider, profile))
        else:
            self.model.setText(self.router.spec(provider).default_model)

    def stored_chat_provider(self):
        """The primary chat provider the owner chose, or the default."""
        return routing.person_provider(self.store)

    def on_chat_provider_changed(self, name):
        """Remember the primary chat provider and show what it means."""
        routing.set_person_provider(self.store, name)
        self.guard_local_voice_provider()
        self.refresh_brain_label()

    def on_backup_provider_changed(self, name):
        """Remember the backup provider. It is only used when it is enabled."""
        self.store.set('backup_provider', name)

    def stored_profile(self, provider):
        """The model profile the owner selected for a provider."""
        saved = self.store.get('profile:' + provider)
        names = profile_models.profile_names(provider)
        return saved if saved in names else profile_models.default_profile(provider)

    def selected_model(self, provider, profile=None):
        """The model that will actually be used for a provider.

        A provider with profiles uses the model of the chosen profile. A model
        the owner typed by hand always wins, because that was a deliberate
        choice and must not be quietly replaced by a default.
        """
        profile = profile if profile is not None else self.stored_profile(provider)
        override = self.store.get('model:' + provider + ':' + profile)
        if override:
            return override
        stored = self.store.get('model:' + provider)
        if stored:
            default = self.router.spec(provider).default_model
            if not profile_models.supports_profiles(provider) or stored != default:
                return stored
        return profile_models.model_for(provider, profile,
                                        self.router.spec(provider).default_model)

    def refresh_brain_label(self):
        """Show the provider, the profile and the model that chat will use."""
        provider = self.chat_provider.currentText()
        profile = self.stored_profile(provider)
        model = self.selected_model(provider)
        if self.active_provider and self.active_model and self.worker is not None:
            provider, profile, model = self.active_provider, '', self.active_model
        self.brain_label.setText('Active brain: ' + profile_models.describe(provider, profile, model))
        self.refresh_prime_state()

    def load_provider(self):
        provider = self.provider.currentText()
        spec = self.router.spec(provider)
        self.load_provider_profiles(provider)
        self.model.setText(self.selected_model(provider))
        self.endpoint.setText(spec.endpoint)
        self.secret.clear()
        health = self.store.get('health:' + provider + ':' + self.model.text())
        self.provider_health.setText('Last explicit check: ' + (health['summary'] if health else 'Not tested'))
        if hasattr(self, 'price_note'):
            self.price_note.setText(pricing.describe(provider, self.model.text()))
        if spec.local:
            self.key_status.setText('Not required: this model runs on this computer')
            return
        try:
            self.key_status.setText('Stored in Windows vault' if self.vault.get(provider) else 'Not configured')
        except Exception:
            self.key_status.setText('Windows vault unavailable on this system')

    def load_provider_profiles(self, provider):
        """Fill the profile chooser with the profiles this provider offers."""
        self.provider_profile.blockSignals(True)
        self.provider_profile.clear()
        names = profile_models.profile_names(provider)
        if names:
            for name in names:
                self.provider_profile.addItem(profile_models.PROFILE_LABELS.get(name, name), name)
            current = self.stored_profile(provider)
            index = self.provider_profile.findData(current)
            self.provider_profile.setCurrentIndex(index if index >= 0 else 0)
            self.profile_note.setText(
                profile_models.PROFILE_NOTES.get(self.provider_profile.currentData(), ''))
        else:
            self.provider_profile.addItem('One model for this provider', '')
            self.profile_note.setText(
                'This provider has a single model, so there is no profile to choose.')
        self.provider_profile.blockSignals(False)

    def on_profile_changed(self):
        """Show the model of the chosen profile."""
        provider = self.provider.currentText()
        profile = self.provider_profile.currentData()
        self.profile_note.setText(profile_models.PROFILE_NOTES.get(profile, ''))
        if profile:
            self.model.setText(self.selected_model(provider, profile))
        self.refresh_price_note()
        self.refresh_brain_label()

    def refresh_price_note(self):
        """Show what the model in the box costs, or that the price is unknown."""
        if not hasattr(self, 'price_note'):
            return
        self.price_note.setText(
            pricing.describe(self.provider.currentText(), self.model.text()))

    def save_provider(self):
        def operation():
            if self.worker is not None:
                raise ValueError('Wait for the current request before changing provider settings.')
            self.policy.ticket()
            provider = self.provider.currentText()
            spec = self.router.spec(provider)
            profile = self.provider_profile.currentData()
            model = self.model.text().strip() or spec.default_model
            if spec.local:
                if self.secret.text():
                    raise ValueError('The local model does not use an API key.')
                self.store.set('model:' + provider, model)
                if profile:
                    self.store.set('profile:' + provider, profile)
                self.load_provider()
                self.chat_provider.setCurrentText(provider)
                self.refresh_brain_label()
                return 'Local model saved. Ready for chat; connection has not been tested.'
            new_key = bool(self.secret.text())
            if new_key:
                try:
                    self.vault.put(provider, self.secret.text())
                except Exception:
                    raise RuntimeError('Could not save the key to Windows Credential Manager.') from None
                finally:
                    self.secret.clear()
                self.store.set('catalogue:' + provider, [])
            self.store.set('custom_model:' + provider,
                           self.advanced_provider.isChecked() and model not in
                           {spec.default_model, *profile_models.profiles_for(provider).values()})
            self.store.set('model:' + provider, model)
            if profile:
                # The model is remembered per profile, so switching back to the
                # other profile does not lose the owner's own model ID.
                self.store.set('model:' + provider + ':' + profile, model)
                self.store.set('profile:' + provider, profile)
            self.load_provider()
            if not self.auto_brain.isChecked():
                self.chat_provider.setCurrentText(provider)
            self.refresh_brain_label()
            if new_key:
                self.check_model_availability()
                return 'Key saved. Checking the provider catalogue…'
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
        messages = self.store.messages(self.session)
        self.transcript.setPlainText('\n\n'.join(
            f'{m["role"].upper()}\n{m["content"]}' for m in messages))
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)
        chat = getattr(self, 'prime_chat', None)
        if chat is not None:
            chat.render(messages)

    def new_chat(self):
        if self.worker is not None:
            return
        if self.coding_task_active():
            self.statusBar().showMessage(
                'A task is still running. Finish or decline it before starting a new chat.', 12000)
            return
        self.clear_desktop_result()
        self.clear_suggested_plan()
        self.conversation_plan.cancel('New conversation; remaining steps cancelled.')
        self.cancel_launch_verification()
        if self.chat_launch is not None:
            self.finish_chat_launch(False)
        self.session = uuid.uuid4().hex
        self.store.set('session', self.session)
        self.clear_attachments()
        self.render_chat()
        self.refresh_archives()
        self.statusBar().showMessage('New conversation. Open older conversations from the saved chat list.')

    def clear_chat(self):
        if self.worker is not None:
            return
        if self.confirm(Action('delete_conversation', self.session)):
            self.clear_desktop_result()
            self.clear_suggested_plan()
            self.conversation_plan.cancel('Conversation deleted.')
            self.cancel_launch_verification()
            self.store.clear_messages(self.session)
            # Deleting the conversation must also revoke any previously
            # selected one-turn file sharing and discard local text snapshots.
            self.clear_attachments()
            self.render_chat()
            self.refresh_archives()

    def clear_suggested_plan(self):
        self.suggested_steps = ()
        self.suggestion_card.hide()

    def show_suggested_steps(self, steps):
        self.suggested_steps = steps
        self.suggestion_preview.setText('Suggested steps:\n' +
            '\n'.join(f'{index}. {step.label}' for index, step in enumerate(steps, 1)))
        self.suggestion_card.show()

    def review_suggested_plan(self):
        if not self.suggested_steps or self.policy.stopped:
            return

        def review():
            self.conversation_plan.start('Review suggested steps', self.suggested_steps)
            self.clear_suggested_plan()

        self.notify(review)

    def update_suggestion_mode(self, enabled):
        self.send_button.setText('Get suggestions' if enabled else 'Send')

    def start_mission_from_chat(self, goal):
        """Run a goal through the mission runtime, from the conversation.

        The goal is kept in the conversation so the history shows what was
        asked, and the answer comes back into the same conversation when
        the mission finishes. The steps themselves are on the Mission
        Control page, where the owner can watch them.
        """
        controller = getattr(self, 'mission_controller', None)
        if controller is None:
            self.show_local_system_reply(goal, 'The mission runtime is not available.')
            return
        self.store.message(self.session, 'user', goal)
        self.render_chat()
        controller.start(goal, from_chat=True)

    def update_mission_mode(self, enabled):
        """The composer says which of the two it will do."""
        if enabled:
            self.send_button.setText('Start the mission')
        elif self.suggestion_mode.isChecked():
            self.send_button.setText('Get suggestions')
        else:
            self.send_button.setText('Send')

    def send(self, *, allow_notes=True):
        if self.policy.stopped or self.worker is not None or not self.prompt.toPlainText().strip():
            return
        self.clear_suggested_plan()
        text = self.prompt.toPlainText().strip()
        if addressed_request(text).casefold() in ('/cancel', 'cancel task', 'task cancel pannu'):
            if self.browser.task:
                self.browser.stop()
                self.prompt.clear()
                return
            cancelled = self.conversation_plan.cancel()
            cancelled = self.cancel_launch_verification() or cancelled
            if not cancelled and self.chat_launch is not None:
                self.finish_chat_launch(False)
                cancelled = True
            if not cancelled and self.desktop_pending is not None:
                self.desktop_task_timer.stop()
                self.desktop_pending = None
                cancelled = True
            self.show_local_system_reply(text, 'Pending desktop requests cancelled. Already opened apps remain open.'
                                         if cancelled else 'No pending conversation plan. Use Emergency Stop to cancel other active work.')
            self.prompt.clear()
            return
        requested_mission = mission_argument(text)
        if requested_mission is not None or self.mission_mode.isChecked():
            goal = text if requested_mission is None else requested_mission
            if not goal:
                self.statusBar().showMessage(
                    'Usage: /mission followed by the goal you want JARVIS to work on.',
                    10000)
                return
            self.prompt.clear()
            self.use_notes.setChecked(False)
            self.files_share_once.setChecked(False)
            self.backup_consent.setChecked(False)
            self.start_mission_from_chat(goal)
            return
        requested_goal = suggestion_argument(text)
        if requested_goal is not None or self.suggestion_mode.isChecked():
            goal = text if requested_goal is None else requested_goal
            if not goal:
                self.statusBar().showMessage('Usage: /suggest followed by your goal.', 10000)
                return
            try:
                typing = parse_desktop_task(goal)
            except ValueError as error:
                self.statusBar().showMessage(str(error), 10000)
                return
            if typing is not None:
                self.prompt.clear()
                self.use_notes.setChecked(False)
                self.files_share_once.setChecked(False)
                self.backup_consent.setChecked(False)
                self.show_local_system_reply(goal,
                    'Review the exact text JARVIS would enter in Notepad:\n' + typing.text
                    + '\n\nTyping will not save a file.')
                self.show_suggested_steps((Step(typing.app, typing),))
                return
            app = parse_voice_command(goal) if requested_goal is not None else None
            if app:
                self.prompt.clear()
                self.use_notes.setChecked(False)
                self.files_share_once.setChecked(False)
                self.backup_consent.setChecked(False)
                self.show_local_system_reply(goal, f'Review the proposed launch of {app}.')
                self.show_suggested_steps((Step(app),))
                return
            self.send_chat_reply(goal, suggestion=True)
            return
        command, _, argument = addressed_request(text).partition(' ')
        if command.casefold() == '/browser':
            self.prompt.clear()
            self.open_section('JARVIS Chat')
            self.browser_output.show()
            self.browser.command(argument)
            return
        if self.launch_verification is not None:
            self.statusBar().showMessage(
                'Checking the application window. Wait or type /cancel.', 10000)
            return
        if self.conversation_plan.active:
            self.statusBar().showMessage('Approve the current step or type /cancel first.', 10000)
            return
        try:
            plan = parse_conversation_plan(text)
            if plan is not None:
                self.conversation_plan.start(text, plan)
                self.prompt.clear()
                return
        except ValueError as error:
            self.show_local_system_reply(text, str(error))
            return
        analysis = parse_command(text)
        analysis = analysis if analysis is not None and analysis.kind == 'analysis' else None
        if analysis is None and self.handle_developer_command(text):
            self.prompt.clear()
            return
        use_notes = allow_notes and self.use_notes.isChecked()
        if allow_notes:
            self.use_notes.setChecked(False)
        if analysis is None:
            local_reply = self.local_system_reply(text)
            if local_reply is not None:
                self.prompt.clear()
                self.show_local_system_reply(text, local_reply)
                return
            # A follow-up such as "continue" or "show the diff" only means
            # something while JARVIS still knows the task it refers to.
            follow_up = parse_follow_up(text)
            if follow_up:
                self.prompt.clear()
                self.open_section('JARVIS Chat')
                self.handle_follow_up(follow_up, text)
                return
            # The answer to a question JARVIS asked comes before anything
            # else, so it is never mistaken for a new request.
            if self.pending_clarification is not None and self.answer_clarification(text):
                self.prompt.clear()
                self.open_section('JARVIS Chat')
                return
            desktop_task = parse_desktop_task(text)
            if desktop_task is not None:
                self.prompt.clear()
                self.queue_desktop_task(text, desktop_task)
                return
            coding = self.coding_request(text)
            if coding is not None:
                self.prompt.clear()
                self.open_section('JARVIS Chat')
                self.start_coding_task(coding, text)
                return
            name = parse_voice_command(text)
            if name:
                if self.chat_launch is not None:
                    self.statusBar().showMessage('Approve or decline the pending action first.', 10000)
                    return
                self.prompt.clear()
                self.queue_chat_launch(text, name)
                return
            request_text = addressed_request(text)
            if request_text.casefold().startswith('/video '):
                if not allow_notes:
                    self.statusBar().showMessage(
                        'Review the video brief and press Ask JARVIS to send it to Gemini.', 15000)
                    return
                brief = request_text[7:].strip()
                if brief:
                    self.open_section('JARVIS Chat')
                    self.video_brief.setPlainText(brief)
                    self.generate_video_plan(chat_brief=brief)
                    if self.worker is not None:
                        self.prompt.clear()
                    return
            if self.route_task(text):
                self.prompt.clear()
                return
        self.send_chat_reply(text, analysis=analysis, use_notes=use_notes)

    def send_chat_reply(self, text, *, analysis=None, use_notes=False, suggestion=False):
        def operation():
            self.chat_ticket = self.policy.ticket()
            provider = self.chat_provider.currentText()
            effort = task_brain.effort_for(text, self.reasoning_effort.currentText(), bool(analysis))
            if self.auto_brain.isChecked() and provider in ('Gemini', 'OpenAI', 'MiniMax'):
                def available(name):
                    try:
                        return bool(self.get_key(name))
                    except ValueError:
                        return False
                def model_for(name, style):
                    wanted = self.selected_model(name, style)
                    return task_brain.catalogued_model(name, wanted, self.store.get('catalogue:' + name, []),
                        style, custom=self.store.get('custom_model:' + name, False))
                provider, model = task_brain.select_route(provider, effort, available=available,
                    model_for=model_for, history=self.store.usage_rows())
            else:
                explicit = self.reasoning_effort.currentText() != 'Auto' or analysis
                model = self.selected_model(provider, effort if explicit else None)
            key = self.get_key(provider)
            backup = None
            if not suggestion and self.backup_consent.isChecked():
                name = self.backup_provider.currentText()
                if name == provider:
                    raise ValueError('Choose a different backup provider.')
                if self.router.spec(provider).local:
                    # A local model never falls through to a paid cloud provider.
                    raise ValueError('The local model never falls back to a cloud provider.')
                backup = StreamTarget(name, self.selected_model(name),
                                      self.get_key(name))
            prompt = analysis.detail if analysis else text
            messages = [message for message in self.store.messages(self.session)
                        if message['role'] in ('user', 'assistant')]
            messages.append({'role': 'user', 'content': prompt})
            notes = self.memory_service.as_context(prompt) if use_notes else ''
            if notes:
                messages[-1]['content'] = (
                    prompt + '\n\nRelated notes from my local memory, for reference only:\n' + notes
                )
            # Only the explicit one-turn checkbox grants file-content sharing.
            # A chosen path alone never uploads content. The app never saves
            # these file bytes in the conversation database.
            shared_files = ()
            if not suggestion and self.files_share_once.isChecked():
                shared_files = tuple(self.attachments)
            if shared_files:
                messages[-1]['content'] += '\n\n' + as_untrusted_context(shared_files)
            if sum(len(m['content']) for m in messages) > 90000:
                raise ValueError('Conversation is too long. Start a new chat.')
            self.store.message(self.session, 'user', prompt)
            self.render_chat()
            self.transcript.appendPlainText('\nJARVIS\n')
            self.prompt.clear()
            language = detect_reply_language(text) or self.assistant_language
            if language:
                self.assistant_language = language
                set_assistant_language(self.store, language)
            guidance = ASSISTANT_GUIDANCE
            if suggestion:
                guidance += SUGGESTION_GUIDANCE
            else:
                guidance += capability_context(self) + conversation_context(self)
            system = {'role': 'system', 'content': guidance}
            if language:
                system['content'] += ' Answer in ' + LANGUAGE_NAMES.get(language, language) + '.'
            kind = 'suggestion' if suggestion else 'chat'
            self.start_worker(provider, model, key, [system] + messages, kind, backup=backup)
            if suggestion:
                self.use_notes.setChecked(False)
                self.files_share_once.setChecked(False)
            if shared_files:
                self.clear_attachments()
                self.statusBar().showMessage(
                    f'{len(shared_files)} file(s) shared with the chosen AI for this message only.',
                    12000)
            self.backup_consent.setChecked(False)
        self.notify(operation)

    def on_chunk(self, text):
        if self.worker_kind not in ('chat', 'suggestion'):
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
                    self.video_handoff_shot.addItems(
                        [f'Shot {number}' for number in range(1, len(plan['shots']) + 1)])
                    self.video_handoff_shot.setCurrentIndex(0)
                    self.video_preview.setPlainText(shot_list(plan))
                    self.refresh_video_sheet()
                    self.video_status.setText(
                        'Shot plan ready. Verify historical details and sync captions to the recorded voiceover.'
                        if plan.get('detailed', False) else
                        'Shot plan ready, but the model left some fields out. The missing ones are marked.')
            else:
                self.video_status.setText(status + ': ' + text)
            if self.video_chat_brief is not None:
                brief = self.video_chat_brief
                self.video_chat_brief = None
                reply = (self.video_preview.toPlainText()
                         if status == 'completed' else self.video_status.text())
                self.show_local_system_reply('/video ' + brief, reply)
        elif self.worker_kind == 'news_briefing':
            data = metrics or {}
            parts = [text]
            if status == 'completed':
                parts.extend(value for value in (
                    data.get('news_provider_error'), data.get('news_sources')) if value)
            self.news_panel.output.setPlainText('\n\n'.join(parts))
            if (status == 'completed' and data.get('news_tamil')
                    and self.news_panel.speech.isChecked() and not self.policy.stopped):
                self.voice_panel.speak_response(text)
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
                try:
                    if self.business_task.currentText() == EDITOPRO_REPLY:
                        summary, reply = parse_editopro_reply(text)
                        self.editopro_english_reply = reply
                        self.business_copy.setText('Copy English reply')
                        text = f'தமிழ் சுருக்கம்\n{summary}\n\nEnglish reply\n{reply}'
                    self.business_preview.setPlainText(text.strip())
                    self.business_status.setText('Draft ready to review and copy.')
                except ValueError as error:
                    status = 'failed'
                    self.business_status.setText(str(error))
            elif status == 'completed':
                status = 'failed'
                self.business_status.setText('Gemini returned an empty draft. Try again.')
            else:
                self.business_status.setText(status + ': ' + text)
        elif self.worker_kind in ('chat', 'suggestion'):
            if status == 'completed':
                if self.worker_kind == 'suggestion':
                    text, steps = extract_suggested_plan(text)
                    if steps:
                        self.show_suggested_steps(steps)
                self.store.message(self.session, 'assistant', text)
                self.render_chat()
                self.show_hud_text(text)
                if self.read_replies.isChecked() and not self.policy.stopped:
                    self.voice_panel.speak_response(text[:600])
            else:
                if status == 'cancelled':
                    # A late reply from an invalidated ticket must never be
                    # persisted after Stop/Resume or appear in a later chat.
                    self.transcript.appendPlainText('\n[CANCELLED] Request cancelled.')
                else:
                    # Keep a generic failure notice across app restarts, but
                    # do not persist potentially sensitive provider diagnostics.
                    notice = ('AI request failed. Check the selected AI provider '
                              'and connection, then retry.')
                    self.store.message(self.session, 'system', '[FAILED] ' + notice)
                    self.render_chat()
                    self.transcript.appendPlainText('\nAttempt details: ' + text)
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
        if self.active_provider and (self.worker_kind != 'news_briefing' or (metrics or {}).get('news_ai_used')):
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
        self.refresh_brain_label()
        self.video_cancel_render.hide()
        self.video_brief.setReadOnly(False)
        self.business_brief.setReadOnly(False)
        self.business_task.setEnabled(True)
        self.refresh_draft_buttons()
        self.set_ai_visual_state('stopped' if self.policy.stopped else 'idle')
        for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button,
                       self.repair_button, self.availability_button):
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
        self.video_handoff_shot.setEnabled(ready and self.video_plan is not None)
        for button in self.video_tool_buttons.values():
            button.setEnabled(ready)
        self.business_generate.setEnabled(ready)
        self.site_generate.setEnabled(ready)
        self.site_language.setEnabled(ready)
        self.site_open_preview.setEnabled(ready and self.site_preview_path is not None)
        self.site_save.setEnabled(ready and self.site_draft is not None)
        for button in self.video_export_buttons:
            button.setEnabled(ready and self.video_plan is not None)
        self.video_render_button.setEnabled(ready and self.video_plan is not None)
        self.capcut_button.setEnabled(ready and self.video_plan is not None)
        self.davinci_button.setEnabled(ready and self.video_plan is not None)
        self.after_effects_button.setEnabled(ready)
        self.after_effects_timeline_button.setEnabled(ready and self.video_plan is not None)

    def stop(self):
        self.policy.stop()
        self.browser.stop()
        controller = getattr(self, 'mission_controller', None)
        if controller is not None:
            controller.cancel()
        if self.research_dialog:
            self.research_dialog.cancel()
        self.clear_desktop_result()
        self.clear_suggested_plan()
        self.conversation_plan.cancel('Emergency Stop. Resume will not replay this plan.')
        self.cancel_launch_verification()
        self.desktop_task_timer.stop()
        self.desktop_pending = None
        if self.test_worker is not None:
            # The test PROCESS is stopped too, not just the assistant.
            self.test_worker.requestInterruption()
        if self.coding_worker is not None:
            self.coding_worker.requestInterruption()
        if self.chat_launch is not None:
            self.finish_chat_launch(False)
        self.release_checker.cancel_source()
        if self.improvement_worker is not None:
            self.improvement_worker.requestInterruption()
        if self.omega is not None:
            self.omega.on_stop()
        if self.news_panel is not None:
            self.news_panel.disable_schedule()
        self.refresh_draft_buttons()
        self.voice_rearm_timer.stop()
        self.hands_free_voice.setChecked(False)
        self.voice_panel.stop_voice()
        self.set_ai_visual_state('stopped')
        self.queue.cancel_pending()
        self.workflows.cancel_pending()
        if self.worker:
            self.worker.requestInterruption()
        self.resume_button.setEnabled(True)
        self.resume_button.show()
        self.send_button.setEnabled(False)
        self.review_pc_action_button.setEnabled(False)
        ident = self.store.task('emergency_stop', 'All outstanding approvals invalidated')
        self.store.finish(ident, 'completed')
        self.statusBar().showMessage('STOPPED. No new actions. In-flight network reads may need up to 30 seconds.')
        self.refresh_history()

    def resume(self):
        self.policy.resume()
        self.voice_panel.resume_voice()
        if self.omega is not None:
            self.omega.refresh_feed.setEnabled(True)
            self.omega.refresh_state()
        self.refresh_draft_buttons()
        self.set_ai_visual_state('idle' if self.worker is None else 'thinking')
        self.resume_button.setEnabled(False)
        self.resume_button.hide()
        if self.worker is None:
            for button in (self.send_button, self.new_chat_button, self.clear_button,
                       self.archive_button, self.probe_button, self.generate_button,
                       self.repair_button, self.availability_button):
                button.setEnabled(True)
        self.review_pc_action_button.setEnabled(True)

    def refresh_history(self):
        rows = self.store.tasks()
        shell = getattr(self, 'prime_shell', None)
        if shell is not None:
            shell.activity.set_rows(rows)
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
        estimated_total = 0.0
        priced = 0
        unknown = 0
        for index, attempt in enumerate(attempts):
            cost = pricing.estimate(attempt['provider'], attempt['model'],
                                     attempt['prompt_tokens'], attempt['completion_tokens'])
            if cost is None:
                unknown += 1
            else:
                estimated_total += cost
                priced += 1
            values = [attempt['provider'] + ' / ' + attempt['model'], attempt['status'],
                      f"{attempt['duration_ms'] / 1000:.2f}",
                      *[attempt[k] if attempt[k] is not None else 'Unknown'
                        for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')],
                      pricing.format_cost(cost),
                      attempt['created']]
            for column, value in enumerate(values):
                self.usage_table.setItem(index, column, QTableWidgetItem(str(value)))
        if hasattr(self, 'usage_cost_summary'):
            self.usage_cost_summary.setText(
                f'Estimated total for the {len(attempts)} attempts shown: '
                f'{pricing.format_cost(estimated_total)} '
                f'({priced} priced, {unknown} without a known price). '
                'The estimate uses the list price of the model; only the provider dashboard '
                'can say what was really charged.')

    def apply_hotkey(self, text, *, save=True):
        """Take the key that brings JARVIS up, or say why it cannot be taken.

        The key is not the microphone. It brings JARVIS to the front, and
        the owner decides there what happens next.
        """
        message = self.hotkey.register(text)
        self.hotkey_status = message
        if save:
            shortcut = self.hotkey.shortcut
            self.store.set('hotkey:shortcut', shortcut.describe() if shortcut else '')
        omega = getattr(self, 'omega', None)
        if omega is not None and getattr(omega, 'hotkey_status', None) is not None:
            omega.hotkey_status.setText(message)
        return message

    def summon_from_hotkey(self):
        """Bring JARVIS to the front. The microphone is not opened."""
        controls = getattr(self, 'background_controls', None)
        if controls is not None and controls.tray is not None:
            controls.restore()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()
        omega = getattr(self, 'omega', None)
        if omega is not None:
            omega.window.activateWindow()

    def request_exit(self):
        self.exit_requested = True
        self.close()

    def closeEvent(self, event):
        self.conversation_plan.cancel('Window closed; remaining steps cancelled.')
        self.audio_test.stop()
        self.cancel_launch_verification()
        self.desktop_task_timer.stop()
        self.desktop_pending = None
        if not self.close_when_done and self.editor.document().isModified():
            if not self.confirm(Action('discard_unsaved_editor_changes', self.filename.text())):
                self.exit_requested = False
                event.ignore()
                return
        if (self.keep_running_in_tray() and not self.exit_requested
                and self.background_controls is not None
                and self.background_controls.tray is not None
                and self.background_controls.tray.isVisible()):
            # The owner asked JARVIS to keep running: the window goes away and
            # the tray keeps it alive, with Pause and Exit.
            self.background_controls.hide()
            event.ignore()
            return
        controller = getattr(self, 'mission_controller', None)
        mission_running = (controller is not None and controller.worker is not None
                           and controller.worker.isRunning())
        if (self.worker is not None or self.coding_worker is not None
                or self.browser.worker is not None
                or (self.research_dialog and self.research_dialog.worker is not None)
                or self.test_worker is not None or self.release_checker.source_worker is not None
                or self.improvement_worker is not None or mission_running):
            # A coding task runs the Codex CLI and the test command in their
            # own processes. Closing the window must not leave them running
            # behind the owner's back, so the stop happens first and the
            # window closes when the workers are gone.
            self.close_when_done = True
            self.stop()
            self.statusBar().showMessage('Waiting for the current task to exit safely…')
            event.ignore()
        else:
            if self.news_panel is not None:
                self.news_panel.disable_schedule()
            self.voice_rearm_timer.stop()
            self.hands_free_voice.setChecked(False)
            self.voice_panel.stop_voice()
            self.voice_panel.wait_for_workers()
            self.bridge.listener.stop()
            if getattr(self, 'hotkey', None) is not None:
                self.hotkey.unregister()
            if self.omega is not None:
                self.omega.shutdown()
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
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'JarvisAI'
    base.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(base / 'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, 'JARVIS AI', 'JARVIS is already running for this user.')
        return 1
    window = Window(base)
    window.enable_omega(smoke=smoke)
    if smoke:
        # Offline native smoke test: no provider calls or remote listener.
        def finish_smoke():
            if (window.isVisible() and window.isAncestorOf(window.prime_shell)
                    and window.prime_shell.brand.text() == 'JARVIS AI'
                    and window.prime_shell.stop_button.isVisibleTo(window)
                    and not window.omega.floating.isVisible()):
                app.quit()
            else:
                app.exit(10)
        QTimer.singleShot(1000, finish_smoke)
    return app.exec()
