"""Review local media inputs before starting a cancellable export."""
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from security.policy import Stopped


class MediaInputs(QDialog):
    def add_file(self, label, filters, *, default_suffix=None, clearable=False):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        field = QLineEdit()
        field.setReadOnly(True)
        row.addWidget(field, 1)
        button = QPushButton("Choose…")
        row.addWidget(button)
        self.form.addRow(label, widget)

        def choose():
            picker = QFileDialog.getSaveFileName if default_suffix else QFileDialog.getOpenFileName
            path, _ = picker(self, label, field.text(), filters)
            if path:
                if default_suffix and not Path(path).suffix:
                    path += default_suffix
                field.setText(path)

        button.clicked.connect(choose)
        if clearable:
            clear = QPushButton("Clear")
            clear.clicked.connect(field.clear)
            row.addWidget(clear)
        return field


class PreviewInputs(MediaInputs):
    def __init__(self, plan, parent, *, timeline=False, editor=None):
        super().__init__(parent)
        self.setWindowTitle("Build After Effects timeline" if timeline else "Assemble MP4 preview")
        self.resize(640, 390)
        layout = QVBoxLayout(self)
        note = QLabel((
            "Select one clip per shot. Save the JSX for File → Scripts → Run Script File, "
            "or send it to After Effects on Windows. Short clips hold their last frame."
        ) if timeline else (
            "Select one clip per shot. JARVIS trims from the beginning, holds the last "
            "frame for short clips and fits the image inside the vertical frame. "
            "Optional narration starts at the beginning and lowers the clip audio."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.clips = [
            self.add_file(
                f"Shot {index} · {shot['start_ms'] / 1000:.2f}–{shot['end_ms'] / 1000:.2f}s",
                "Video (*.mp4 *.mov *.m4v)",
            )
            for index, shot in enumerate(plan["shots"], 1)
        ]
        self.narration = self.add_file("Narration (optional)", "Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg)", clearable=True)
        self.script_only = None
        if timeline:
            self.script_only = QCheckBox("Save JSX only")
            self.script_only.setChecked(True)
            self.script_only.setEnabled(sys.platform == "win32")
            self.form.addRow(self.script_only)
            self.target = self.add_file("Adobe application", "After Effects (AfterFX.exe)")
        elif editor:
            self.setWindowTitle(f"Export for {editor}")
            note.setText("Choose one clip per shot and an export folder. Import video.mp4 "
                         f"and english.srt into {editor}.")
            self.target = QLineEdit()
            self.target.setReadOnly(True)
            choose = QPushButton("Choose export folder…")
            self.form.addRow(choose, self.target)

            def choose_folder():
                folder = QFileDialog.getExistingDirectory(self, "Choose export folder", self.target.text())
                if folder:
                    self.target.setText(folder)

            choose.clicked.connect(choose_folder)
        else:
            self.target = self.add_file("Save preview as", "MP4 (*.mp4)", default_suffix=".mp4")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Review timeline" if timeline else "Review export")
        self.ok.setEnabled(False)
        for field in (*self.clips, self.target):
            field.textChanged.connect(self.refresh_ready)
        layout.addWidget(buttons)
        if self.script_only is not None:
            self.script_only.toggled.connect(self.refresh_ready)
        self.refresh_ready()

    def refresh_ready(self):
        script_only = self.script_only is not None and self.script_only.isChecked()
        if self.script_only is not None:
            self.target.parentWidget().setEnabled(not script_only)
        self.ok.setEnabled((script_only or bool(self.target.text()))
                           and all(field.text() for field in self.clips))


class AfterEffectsInputs(MediaInputs):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Render After Effects composition")
        self.resize(660, 280)
        layout = QVBoxLayout(self)
        note = QLabel("Choose Adobe’s aerender.exe and an existing project. Enter the exact "
                      "composition and movie output template names from After Effects.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.executable = self.add_file("Adobe renderer", "Adobe renderer (aerender.exe)")
        self.project = self.add_file("After Effects project", "After Effects (*.aep)")
        self.composition = QLineEdit()
        self.template = QLineEdit()
        self.form.addRow("Composition", self.composition)
        self.form.addRow("Output module template", self.template)
        self.output = self.add_file("Save movie as", "Movie (*.mp4 *.mov *.avi)", default_suffix=".mov")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Review render")
        self.fields = (self.executable, self.project, self.composition, self.template, self.output)
        for field in self.fields:
            field.textChanged.connect(self.refresh_ready)
        self.refresh_ready()

    def refresh_ready(self):
        self.ok.setEnabled(all(field.text().strip() for field in self.fields))

    def values(self):
        return tuple(field.text() for field in self.fields)


class VideoExportWorker(QThread):
    result = Signal(str, str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def check_cancelled(self):
        if self.isInterruptionRequested():
            raise Stopped("Preview export cancelled.")

    def run(self):
        try:
            output = self.operation(self.check_cancelled)
        except Stopped as error:
            self.result.emit("cancelled", str(error))
        except Exception as error:
            self.result.emit("failed", str(error))
        else:
            self.result.emit("completed", str(output))
