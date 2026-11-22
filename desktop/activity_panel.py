"""The task activity drawer for the main JARVIS AI window."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)


STATES = {
    'idle': ('Ready', 'good'),
    'listening': ('Listening', 'good'),
    'thinking': ('Thinking', 'accent'),
    'responding': ('Answering', 'accent'),
    'speaking': ('Speaking', 'good'),
    'working': ('Working', 'accent'),
    'approval': ('Approval required', 'warn'),
    'stopped': ('Stopped', 'danger'),
}

STATUS_COLOURS = {
    'pending': 'warn', 'running': 'accent', 'completed': 'good',
    'accepted': 'good', 'verified': 'good', 'failed': 'danger', 'error': 'danger',
    'interrupted': 'warn', 'unverified': 'warn', 'dispatched': 'muted',
}


def caption(value):
    return str(value or 'Unknown').replace('_', ' ').capitalize()


class ActivityPanel(QFrame):
    closed = Signal()

    def __init__(self, palette, open_history, parent=None):
        super().__init__(parent)
        self.setObjectName('activityPanel')
        self.setFixedWidth(288)
        self.palette_ = palette
        self._state = 'idle'
        self._rows = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.title = QLabel('Activity')
        header.addWidget(self.title, 1)
        close = QPushButton('Close')
        close.setAccessibleName('Close activity panel')
        close.clicked.connect(self.closed.emit)
        header.addWidget(close)
        layout.addLayout(header)

        self.state = QLabel()
        self.state.setAccessibleName('Current JARVIS activity')
        layout.addWidget(self.state)
        self.heading = QLabel('Recent actions')
        layout.addWidget(self.heading)

        self.empty = QLabel('No actions recorded yet.')
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.records = QListWidget()
        self.records.setAccessibleName('Recent actions')
        self.records.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.records.currentRowChanged.connect(self.show_record)
        layout.addWidget(self.records, 2)
        self.details = QPlainTextEdit()
        self.details.setAccessibleName('Selected activity details')
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        history = QPushButton('Open task history')
        history.clicked.connect(open_history)
        layout.addWidget(history)
        self.set_rows([])
        self.refresh_theme()

    def set_state(self, state):
        if state == self._state and self.state.text():
            return
        self._state = state
        self.style_state()

    def style_state(self):
        label, colour = STATES[self._state]
        accent = getattr(self.palette_, colour).name()
        self.state.setText(label)
        self.state.setStyleSheet(f'color: {accent}; font-size: 13px; font-weight: 600;'
                                 f' border: 1px solid {accent}; border-radius: 8px; padding: 7px;')

    def refresh_theme(self):
        palette = self.palette_
        self.setStyleSheet(
            f'QFrame#activityPanel {{ background: {palette.ground_far.name()}; '
            f'border-left: 1px solid {palette.muted.name()}; }}'
            f'QListWidget, QPlainTextEdit {{ background: {palette.ground.name()}; '
            f'color: {palette.ink.name()}; border: 0; border-radius: 6px; padding: 5px; }}'
            'QListWidget::item { padding: 6px; }'
            f'QListWidget::item:selected {{ background: {palette.accent_deep.name()}; '
            'color: white; }')
        self.title.setStyleSheet(f'color: {palette.ink.name()}; font-size: 19px; font-weight: 600;')
        for label in (self.heading, self.empty):
            label.setStyleSheet(f'color: {palette.muted.name()};')
        self.style_state()
        for index, row in enumerate(self._rows):
            self.records.item(index).setForeground(self.status_colour(row['status']))

    def status_colour(self, status):
        return QColor(getattr(self.palette_, STATUS_COLOURS.get(status, 'ink')))

    def set_rows(self, rows):
        recent = rows[:30]
        if recent == self._rows:
            return
        selection = self.records.currentItem()
        selected_id = selection.data(Qt.ItemDataRole.UserRole) if selection else None
        self._rows = recent
        self.records.blockSignals(True)
        self.records.clear()
        selected_row = 0
        for index, row in enumerate(recent):
            item = QListWidgetItem(f"{caption(row['kind'])}\n{caption(row['status'])}")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setForeground(self.status_colour(row['status']))
            self.records.addItem(item)
            if row['id'] == selected_id:
                selected_row = index
        if recent:
            self.records.setCurrentRow(selected_row)
        self.records.blockSignals(False)
        self.records.setVisible(bool(recent))
        self.empty.setVisible(not recent)
        self.show_record(self.records.currentRow())

    def show_record(self, index):
        self.details.setVisible(index >= 0)
        row = self._rows[index] if index >= 0 else None
        text = f"{row['created']} UTC\n\n{row['detail'] or 'No details recorded.'}" if row else ''
        if text != self.details.toPlainText():
            self.details.setPlainText(text)
