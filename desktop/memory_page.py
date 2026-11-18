"""The Memory page.

The owner keeps short notes here and finds them again with a word search.
The notes stay in the local database of the program; nothing is sent anywhere
until the owner chooses Include notes once in Chat options.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from memory.memory_service import MemoryError, MemoryService


class MemoryPanel(QWidget):
    """Write, find and forget the owner's memories."""

    def __init__(self, *, service=None, path=None, parent=None):
        super().__init__(parent)
        if service is None:
            if path is None:
                raise ValueError('A memory service or a path is needed.')
            service = MemoryService(path)
        self.service = service
        self.editing_id = None
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 10, 10)
        title = QLabel('Memory')
        title.setStyleSheet('font-size:24px;font-weight:600')
        layout.addWidget(title)
        note = QLabel(
            'Keep the things you want JARVIS to remember between sessions. The notes '
            'stay in the local database. To share matching notes with the selected '
            'AI provider for a single message, enable Include notes once in Chat options.')
        note.setWordWrap(True)
        layout.addWidget(note)

        write_box = QGroupBox('Remember something')
        write_layout = QFormLayout(write_box)
        self.memory_title = QLineEdit()
        self.memory_title.setPlaceholderText('A short title')
        write_layout.addRow('Title', self.memory_title)
        self.memory_body = QPlainTextEdit()
        self.memory_body.setPlaceholderText('What should JARVIS remember?')
        self.memory_body.setMaximumHeight(110)
        write_layout.addRow('Note', self.memory_body)
        self.memory_tags = QLineEdit()
        self.memory_tags.setPlaceholderText('Tags, separated by commas')
        write_layout.addRow('Tags', self.memory_tags)
        write_row = QHBoxLayout()
        self.remember_button = QPushButton('Remember')
        self.remember_button.clicked.connect(self.remember)
        write_row.addWidget(self.remember_button)
        self.cancel_edit_button = QPushButton('Cancel edit')
        self.cancel_edit_button.clicked.connect(self.clear_edit)
        self.cancel_edit_button.hide()
        write_row.addWidget(self.cancel_edit_button)
        write_layout.addRow(write_row)
        self.memory_status = QLabel('')
        self.memory_status.setTextFormat(Qt.TextFormat.PlainText)
        self.memory_status.setWordWrap(True)
        write_layout.addRow('Status', self.memory_status)
        layout.addWidget(write_box)

        find_box = QGroupBox('Find')
        find_layout = QFormLayout(find_box)
        self.query = QLineEdit()
        self.query.setPlaceholderText('A word from the note you are looking for')
        self.query.returnPressed.connect(self.find)
        find_layout.addRow('Search', self.query)
        find_row = QHBoxLayout()
        self.find_button = QPushButton('Search')
        self.find_button.clicked.connect(self.find)
        find_row.addWidget(self.find_button)
        self.show_all_button = QPushButton('Show all')
        self.show_all_button.clicked.connect(self.show_all)
        find_row.addWidget(self.show_all_button)
        find_layout.addRow(find_row)
        layout.addWidget(find_box)

        self.results = QListWidget()
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setWordWrap(True)
        self.results.itemDoubleClicked.connect(self.show_one)
        layout.addWidget(self.results)

        actions = QHBoxLayout()
        edit_button = QPushButton('Edit selected note')
        edit_button.clicked.connect(self.edit_selected)
        actions.addWidget(edit_button)
        self.forget_button = QPushButton('Forget the selected note')
        self.forget_button.clicked.connect(self.forget)
        actions.addWidget(self.forget_button)
        layout.addLayout(actions)
        layout.addStretch()

    # ---------------------------------------------------------------- actions

    def remember(self):
        """Save what the owner typed."""
        title = self.memory_title.text().strip()
        body = self.memory_body.toPlainText().strip()
        tags = [part.strip() for part in self.memory_tags.text().split(',') if part.strip()]
        try:
            editing = self.editing_id is not None
            if editing:
                memory = self.service.update(self.editing_id, title, body, tags)
            else:
                memory = self.service.remember(title, body, tags)
        except MemoryError as error:
            self.memory_status.setText(str(error))
            return
        self.clear_edit()
        self.memory_status.setText(('Updated: ' if editing else 'Remembered: ') + memory.title)
        self.refresh()

    def clear_edit(self):
        self.editing_id = None
        self.memory_title.clear()
        self.memory_body.clear()
        self.memory_tags.clear()
        self.memory_status.clear()
        self.remember_button.setText('Remember')
        self.cancel_edit_button.hide()

    def edit_selected(self):
        item = self.results.currentItem()
        if item is None:
            self.memory_status.setText('Choose a note first.')
            return
        self.show_one(item)

    def find(self):
        """Look for the memories that match the word."""
        query = self.query.text().strip()
        if not query:
            self.show_all()
            return
        found = self.service.search(query)
        self.results.clear()
        if not found:
            self.memory_status.setText('Nothing matches "' + query + '".')
            return
        self.memory_status.setText(f'{len(found)} note(s) match "{query}".')
        for memory in found:
            item = QListWidgetItem(f'{memory.title} — {memory.body[:160]}')
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            item.setToolTip('Tags: ' + (', '.join(memory.tags) or 'none'))
            self.results.addItem(item)

    def show_all(self):
        """List every memory."""
        self.results.clear()
        for memory in self.service.all():
            item = QListWidgetItem(f'{memory.title} — {memory.body[:160]}')
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            item.setToolTip('Tags: ' + (', '.join(memory.tags) or 'none'))
            self.results.addItem(item)

    def show_one(self, item):
        """Load the selected note into the form."""
        identifier = item.data(Qt.ItemDataRole.UserRole)
        memory = self.service.get(identifier)
        if memory is None:
            return
        self.editing_id = memory.id
        self.remember_button.setText('Save changes')
        self.cancel_edit_button.show()
        self.memory_status.setText('Editing: ' + memory.title)
        self.memory_title.setText(memory.title)
        self.memory_body.setPlainText(memory.body)
        self.memory_tags.setText(', '.join(memory.tags))

    def forget(self):
        """Delete the selected memory."""
        item = self.results.currentItem()
        if item is None:
            self.memory_status.setText('Choose a note first.')
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        title = item.text().split(' — ')[0]
        if self.service.forget(identifier):
            if identifier == self.editing_id:
                self.clear_edit()
            self.memory_status.setText('Forgotten: ' + title)
        else:
            self.memory_status.setText('That note was already gone.')
        self.refresh()

    def refresh(self):
        """Show what is there."""
        self.show_all()


__all__ = ['MemoryPanel']
