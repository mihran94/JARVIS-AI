"""Port the chat-first changes onto the JARVIS Omega tree, keeping Omega intact.

The chat-first patch was written against main before JARVIS Omega landed, so
its desktop/app.py hunks no longer apply. This script performs the same edits
by hand, merging with Omega instead of overwriting it:

  * the navigation row and the inline Approve/Decline row are added;
  * the chat commands and the /video command are added to send();
  * the plugin switches and the chosen executable are added to Settings;
  * stop() cancels the pending launch AND still calls Omega's on_stop();
  * confirm() keeps Omega's approval state around the dialog.

Run from the repository root:  python scripts/port_chat_first_omega.py
"""
import pathlib
import sys

TARGET = pathlib.Path('desktop/app.py')


def port(text):
    edits = []

    def sub(old, new, label):
        nonlocal text
        if old not in text:
            raise SystemExit('MISSING: ' + label)
        text = text.replace(old, new, 1)
        edits.append(label)

    sub("""    QHeaderView, QCheckBox, QDialog, QFileDialog, QScrollArea, QLayout, QGridLayout,
    QProgressBar, QGroupBox, QSizePolicy,""",
        """    QHeaderView, QCheckBox, QDialog, QFileDialog, QScrollArea, QLayout,
    QProgressBar, QGroupBox, QSizePolicy,""", 'imports: QGridLayout')
    sub("from security.policy import Policy, Action, Stopped",
        "from security.policy import Action, Denied, Policy, Stopped", 'imports: Denied')
    sub("from automation.windows import APPS, launch_app",
        "from automation.windows import APPS, EDITOR_EXECUTABLES, editor_executable, launch_app, launch_editor",
        'imports: EDITOR_EXECUTABLES')
    sub("""        self.video_plan = None
        self.site_export = None""",
        """        self.video_plan = None
        self.video_chat_brief = None
        self.chat_launch = None
        self.site_export = None""", 'state: chat_launch')
    sub("""        outer.addLayout(header)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(174)
        self.pages = QStackedWidget()""",
        """        outer.addLayout(header)
        navigation = QHBoxLayout()
        self.chat_home_button = self.button(
            navigation, 'Chat', lambda: self.open_section('JARVIS Chat'))
        self.tools_button = QPushButton('Tools')
        self.tools_button.setCheckable(True)
        navigation.addWidget(self.tools_button)
        self.button(navigation, 'Settings & Plugins', lambda: self.open_section('Settings & Safety'))
        navigation.addStretch()
        outer.addLayout(navigation)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(174)
        self.nav.hide()
        self.tools_button.toggled.connect(self.nav.setVisible)
        self.pages = QStackedWidget()""", 'nav row')
    sub("""        shortcuts = QGridLayout()
        for index, (label, section) in enumerate([
            ('Video', 'Video Editor'), ('Coding', 'Coding Assistant'),
            ('Phone', 'Phone Remote'), ('Camera', 'PC Control'),
            ('Commands', 'Command Center'),
        ]):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, section=section: self.open_section(section))
            shortcuts.addWidget(button, index // 3, index % 3)
        layout.addLayout(shortcuts)
""", "", 'chat page: shortcuts grid removed')
    sub("""        layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText('Ask JARVIS… தமிழ் / English / Français')""",
        """        layout.addWidget(self.transcript, 1)
        self.chat_approval = QWidget()
        approval_row = QHBoxLayout(self.chat_approval)
        approval_row.setContentsMargins(0, 0, 0, 0)
        self.chat_approval_label = QLabel()
        self.chat_approval_label.setWordWrap(True)
        approval_row.addWidget(self.chat_approval_label, 1)
        self.chat_approve_button = self.button(
            approval_row, 'Approve', lambda: self.finish_chat_launch(True))
        self.chat_decline_button = self.button(
            approval_row, 'Decline', lambda: self.finish_chat_launch(False))
        self.chat_approval.hide()
        layout.addWidget(self.chat_approval)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(
            'Ask JARVIS… e.g. Open CapCut or /video followed by a brief')""", 'chat page: approval row')
    sub("    def generate_video_plan(self):", "    def generate_video_plan(self, *, chat_brief=None):",
        'generate_video_plan signature')
    sub("""            self.video_status.setText(f'Generating a {engine} shot plan with Gemini…')
            self.start_worker(provider, model, key, messages, 'video_plan')""",
        """            self.video_status.setText(f'Generating a {engine} shot plan with Gemini…')
            self.video_chat_brief = chat_brief
            self.start_worker(provider, model, key, messages, 'video_plan')""", 'generate_video_plan body')
    sub("""        def operation():
            self.policy.ticket()
            index = self.video_handoff_shot.currentIndex()""",
        """        def operation():
            self.policy.ticket()
            if not self.plugin_enabled(tool):
                raise ValueError(f'{tool} is disabled in Settings → Plugins.')
            index = self.video_handoff_shot.currentIndex()""", 'handoff: plugin check')
    sub("""        session = self.archives.currentData()
        if session:
            self.session = session""",
        """        session = self.archives.currentData()
        if session:
            if self.chat_launch is not None:
                self.finish_chat_launch(False)
            self.session = session""", 'open_chat: cancel pending launch')
    sub("""        layout.addLayout(advanced)
        text = QPlainTextEdit()
        text.setReadOnly(True)""",
        """        layout.addLayout(advanced)
        plugins = QGroupBox('Plugins')
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
        text = QPlainTextEdit()
        text.setReadOnly(True)""", 'settings: plugin switches')

    new_methods = '''    def plugin_enabled(self, name):
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
                        return f'{name} opened in the browser.'
                else:
                    path = editor_executable(name, self.store.get('editor_path:' + name, ''))
                    action = Action('launch_editor', str(path))
                    operation = lambda: launch_editor(name, path)
        except (Stopped, ValueError, OSError) as error:
            self.show_local_system_reply(command, str(error))
            return
        self.chat_launch = (name, ticket, action, operation)
        self.show_local_system_reply(command, f'Open {name}? Approve or decline below.')
        self.chat_approval_label.setText(action.target)
        self.chat_approval.show()

    def finish_chat_launch(self, approved):
        pending, self.chat_launch = self.chat_launch, None
        self.chat_approval.hide()
        if pending is None:
            return
        name, ticket, action, operation = pending
        try:
            self.policy.check(ticket)
            if approved and name not in APPS and not self.plugin_enabled(name):
                raise ValueError(f'{name} is disabled in Settings → Plugins.')
            result = self.gateway.run(action, lambda _action: approved, operation)
        except (Denied, Stopped, ValueError, OSError, RuntimeError) as error:
            result = str(error)
        self.store.message(self.session, 'system', result)
        self.render_chat()
        self.refresh_history()

    def confirm(self, action):'''

    sub("""    def confirm(self, action):
        extra = ('\\nContent SHA-256: ' + action.digest) if action.digest else ''
        if self.omega is not None:""",
        new_methods + """
        extra = ('\\nContent SHA-256: ' + action.digest) if action.digest else ''
        if self.omega is not None:""", 'chat launch methods + Omega confirm kept')
    sub("""    def new_chat(self):
        if self.worker is not None:
            return
        self.session = uuid.uuid4().hex""",
        """    def new_chat(self):
        if self.worker is not None:
            return
        if self.chat_launch is not None:
            self.finish_chat_launch(False)
        self.session = uuid.uuid4().hex""", 'new_chat cancels pending launch')
    sub("""            self.prompt.clear()
            self.show_local_system_reply(text, local_reply)
            return
        if self.route_task(text):""",
        """            self.prompt.clear()
            self.show_local_system_reply(text, local_reply)
            return
        name = parse_voice_command(text)
        if name:
            if self.chat_launch is not None:
                self.statusBar().showMessage('Approve or decline the pending action first.', 10000)
                return
            self.prompt.clear()
            self.queue_chat_launch(text, name)
            return
        if text.casefold().startswith('/video '):
            if not allow_notes:
                self.statusBar().showMessage(
                    'Review the video brief and press Ask JARVIS to send it to Gemini.', 15000)
                return
            brief = text[7:].strip()
            if brief:
                self.open_section('JARVIS Chat')
                self.video_brief.setPlainText(brief)
                self.generate_video_plan(chat_brief=brief)
                if self.worker is not None:
                    self.prompt.clear()
                return
        if self.route_task(text):""", 'send: chat commands')
    sub("""            else:
                self.video_status.setText(status + ': ' + text)
        elif self.worker_kind == 'news_briefing':""",
        """            else:
                self.video_status.setText(status + ': ' + text)
            if self.video_chat_brief is not None:
                brief = self.video_chat_brief
                self.video_chat_brief = None
                reply = (self.video_preview.toPlainText()
                         if status == 'completed' else self.video_status.text())
                self.show_local_system_reply('/video ' + brief, reply)
        elif self.worker_kind == 'news_briefing':""", 'on_result: plan back to chat')
    sub("""    def stop(self):
        self.policy.stop()
        if self.omega is not None:
            self.omega.on_stop()""",
        """    def stop(self):
        self.policy.stop()
        if self.chat_launch is not None:
            self.finish_chat_launch(False)
        if self.omega is not None:
            self.omega.on_stop()""", 'stop: chat launch + Omega kept')
    return text, edits


def main():
    if not TARGET.is_file():
        raise SystemExit('Run this from the repository root.')
    original = TARGET.read_text(encoding='utf-8')
    if 'def queue_chat_launch' in original:
        print('Already ported.')
        return 0
    text, edits = port(original)
    TARGET.write_text(text, encoding='utf-8')
    print('Ported onto Omega:', ', '.join(edits))
    return 0


if __name__ == '__main__':
    sys.exit(main())
