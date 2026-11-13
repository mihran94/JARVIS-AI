from PyQt6.QtCore import pyqtSignal
from threading import Thread
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel, QComboBox, QTextEdit, QFileDialog, QMessageBox
from core.project_update import UpdateSession
from core.coding_prompts import PROMPTS, draft_prompt

class ProjectUpdateDialog(QDialog):
    batch_generated = pyqtSignal(object, str)
    generated = pyqtSignal(str, str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Project ZIP updater')
        self.resize(850, 700)
        self.generated.connect(self._generated)
        self.batch_generated.connect(self._batch_generated)
        self._generating = False
        self.session = None
        self.proposal = None
        self.staged = {}
        self.drafts = {}
        self.loaded_name = ""
        layout = QVBoxLayout(self)
        self.status = QLabel('Import ZIP → select file → edit → preview → apply → export. Original ZIP stays unchanged.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.files = QComboBox()
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.diff = QTextEdit()
        self.diff.setReadOnly(True)
        for text, callback in [('Import ZIP', self.import_zip)]:
            button = QPushButton(text); button.clicked.connect(lambda _, fn=callback: self.perform(fn)); layout.addWidget(button)
        layout.addWidget(self.files); layout.addWidget(self.editor); layout.addWidget(self.diff)
        self.instruction = QTextEdit()
        self.instruction.setPlaceholderText('Describe the change for the selected file')
        self.instruction.setMaximumHeight(70)
        self.prompt_choice = QComboBox()
        self.prompt_choice.addItems(PROMPTS)
        self.prompt_choice.currentTextChanged.connect(lambda name: self.instruction.setPlainText(PROMPTS[name]))
        layout.addWidget(self.prompt_choice)
        layout.addWidget(self.instruction)
        for text, callback in [('AI task across project files', self.generate_batch), ('AI draft for selected file', self.generate), ('Stage file + preview all', self.preview), ('Apply all staged files', self.apply), ('Discard drafts', self.discard), ('Undo last change', self.undo), ('Check Python syntax', self.check), ('Run project unit tests…', self.run_tests), ('Export updated ZIP', self.export)]:
            button = QPushButton(text); button.clicked.connect(lambda _, fn=callback: self.perform(fn)); layout.addWidget(button)
        self.files.currentTextChanged.connect(lambda _: self.perform(self.load))
        self.editor.textChanged.connect(self.invalidate)

    def invalidate(self):
        self.proposal = None
        if self.loaded_name:
            self.drafts[self.loaded_name] = self.editor.toPlainText()
            self.staged.pop(self.loaded_name, None)
            self.show_diff()

    def show_diff(self):
        self.diff.setPlainText('\n'.join(p[3] for p in self.staged.values()) or 'No staged changes.')

    def discard(self):
        self.staged.clear(); self.drafts.clear(); self.loaded_name = ''
        self.load()


    def perform(self, action):
        try: action()
        except Exception as error: self.status.setText(str(error))

    def import_zip(self):
        source, _ = QFileDialog.getOpenFileName(self, 'Project ZIP', '', 'ZIP (*.zip)')
        if not source: return
        destination = QFileDialog.getExistingDirectory(self, 'Folder for working copy and backups')
        if not destination: return
        session = UpdateSession(source, destination)
        self.staged.clear(); self.drafts.clear(); self.loaded_name = ""
        self.session = session
        self.files.blockSignals(True); self.files.clear()
        for path in session.root.rglob('*'):
            if path.is_file():
                try: session.workspace.read_text(path.relative_to(session.root))
                except (ValueError, OSError): continue
                self.files.addItem(path.relative_to(session.root).as_posix())
        self.files.blockSignals(False)
        self.load()
        self.status.setText(f'Working copy: {session.home}. Excluded {len(session.skipped)} credential/environment entries. Backups stay here.')

    def load(self):
        self.loaded_name = self.files.currentText()
        self.editor.blockSignals(True)
        try:
            text = ''
            if self.session and self.loaded_name:
                text = self.drafts.get(self.loaded_name)
                if text is None: text = self.session.workspace.read_text(self.loaded_name)
            self.editor.setPlainText(text)
        finally:
            self.editor.blockSignals(False)
        self.show_diff()

    def preview(self):
        if not self.session: raise ValueError('Import a ZIP first.')
        proposal = self.session.preview(self.files.currentText(), self.editor.toPlainText())
        self.staged[proposal[0]] = proposal
        self.show_diff()
        self.status.setText(f'{len(self.staged)} files staged. Review all diffs before applying.')

    def apply(self):
        if not self.staged: raise ValueError('Stage changes first.')
        for name, text in self.drafts.items():
            if name not in self.staged and text != self.session.workspace.read_text(name):
                raise ValueError('Stage or discard every edited file before applying.')
        self.session.apply_batch(self.staged.values())
        self.discard()
        self.status.setText('All staged files applied; grouped backup saved.')

    def undo(self):
        if not self.session: return
        if self.staged or self.drafts: raise ValueError("Discard drafts before undo.")
        self.session.undo(); self.load(); self.status.setText('Last change restored.')

    def check(self):
        if self.session: self.status.setText(self.session.check())

    def export(self):
        if not self.session: return
        if self.staged or any(text != self.session.workspace.read_text(name) for name, text in self.drafts.items()):
            raise ValueError('Apply or discard the current edit before export.')
        destination, _ = QFileDialog.getSaveFileName(self, 'Save new ZIP (choose a new filename)', 'updated-project.zip', 'ZIP (*.zip)')
        if destination:
            self.session.export(destination); self.status.setText('Exported: '+destination)

    def generate(self):
        if not self.session or not self.files.currentText(): raise ValueError('Select a file first.')
        instruction = self.instruction.toPlainText().strip()
        if not instruction: raise ValueError('Describe the requested change.')
        prompt = draft_prompt(self.files.currentText(), instruction, self.editor.toPlainText())
        if QMessageBox.question(self, 'AI draft', 'Send the selected file and request to your configured AI provider? Usage may be billed.') != QMessageBox.StandardButton.Yes: return
        name = self.files.currentText()
        content = self.editor.toPlainText()
        self._generating = True
        self.status.setText("AI is writing the selected file…")
        self.setEnabled(False)
        def work():
            try:
                from core import gemini
                answer = gemini.text(prompt, tier=gemini.SMART)
                error = '' if answer else 'AI returned no draft. Check provider settings.'
            except Exception:
                answer, error = '', 'AI draft failed. Check provider settings.'
            try: self.generated.emit(answer, error)
            except RuntimeError: pass
        Thread(target=work, daemon=True).start()

    def _generated(self, answer, error):
        self._generating = False
        self.setEnabled(True)
        if error: self.status.setText(error)
        else:
            self.editor.setPlainText(answer)
            self.perform(self.preview)
            if self.loaded_name in self.staged:
                self.status.setText('AI draft staged. Review the diff, then apply when ready.')

    def reject(self):
        if self._generating:
            return  # Keep the destination stable until the provider returns.
        super().reject()

    def generate_batch(self):
        if not self.session: raise ValueError('Import a project ZIP first.')
        if self.staged or self.drafts: raise ValueError('Apply or discard drafts before starting a project task.')
        names = [self.files.itemText(i) for i in range(self.files.count())]
        if not 1 <= len(names) <= 10:
            raise ValueError('This first project-agent version accepts projects with 1–10 editable files.')
        instruction = self.instruction.toPlainText().strip()
        if not instruction: raise ValueError('Describe the project task.')
        scope = '\n'.join(names)
        if QMessageBox.question(self, 'Project task scope',
            'Send these files to your configured provider for one coding task? Usage may be billed.\n\n'+scope) != QMessageBox.StandardButton.Yes: return
        self._generating = True
        self.setEnabled(False)
        self.status.setText('Planning and drafting project changes…')
        session = self.session
        def work():
            try:
                from core.project_agent import propose_changes
                proposals, error = propose_changes(session, names, instruction), ''
            except Exception as exc:
                proposals, error = [], str(exc)
            try: self.batch_generated.emit(proposals, error)
            except RuntimeError: pass
        Thread(target=work, daemon=True).start()

    def _batch_generated(self, proposals, error):
        self._generating = False
        self.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        self.staged = {proposal[0]: proposal for proposal in proposals}
        self.drafts = {proposal[0]: proposal[2].decode('utf-8') for proposal in proposals}
        self.load()
        self.status.setText(f'Project task produced {len(proposals)} validated file drafts. Review all diffs, then Apply all staged files.')

    def run_tests(self):
        if not self.session: raise ValueError('Import a project first.')
        if self.staged or self.drafts: raise ValueError('Apply or discard drafts before testing.')
        from core.project_tests_ui import ProjectTestsDialog
        dialog = ProjectTestsDialog(self.session.root, self)
        requests = []
        dialog.repair_requested.connect(requests.append)
        dialog.exec()
        if requests:
            self.instruction.setPlainText(requests[-1])
            self.generate_batch()
