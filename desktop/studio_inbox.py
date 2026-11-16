"""A reviewable inbox and reply dialog for the Business workspace."""
from collections import deque
from functools import partial
import os

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from business.studio_inbox import MAX_MESSAGE_LENGTH, InboxError, StudioInbox, reply_messages, site_origin
from quantum_core.studio_project import STUDIO_URL


class InboxWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.completed.emit(self.operation())
        except InboxError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit('The operation failed. Check the provider or website settings.')


class StudioInboxDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = None
        self.pending = None
        self.order = None
        self.history = deque(maxlen=1000)
        self.initial_read = False
        self.setWindowTitle('AI Creative Studio · Client inbox')
        self.resize(740, 660)
        self.timer = QTimer(self)
        self.timer.setInterval(15_000)
        self.timer.timeout.connect(self.refresh_inbox)

        layout = QVBoxLayout(self)
        links = QHBoxLayout()
        self.button(links, 'Open website', self.open_website)
        self.button(links, 'Open Fiverr Inbox', lambda: QDesktopServices.openUrl(QUrl('https://www.fiverr.com/inbox')))
        layout.addLayout(links)
        controls = QHBoxLayout()
        self.refresh = self.button(controls, 'Refresh website inbox', self.refresh_inbox)
        self.watch = QCheckBox('Check every 15 seconds')
        self.watch.toggled.connect(self.set_watch)
        controls.addWidget(self.watch)
        self.voice = QCheckBox('Voice alerts')
        controls.addWidget(self.voice)
        layout.addLayout(controls)
        self.status = QLabel('Select a website message, or paste a client message to prepare a draft.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)

        self.messages = QListWidget()
        self.messages.currentItemChanged.connect(self.select_message)
        layout.addWidget(self.messages)
        self.manual = self.button(layout, 'New manual draft', self.new_manual_draft)
        self.customer = QPlainTextEdit()
        self.customer.setPlaceholderText('Client message')
        self.customer.setMaximumHeight(98)
        self.customer.textChanged.connect(self.customer_changed)
        layout.addWidget(self.customer)
        self.reply = QPlainTextEdit()
        self.reply.setPlaceholderText('What you want to say, or the final reply to review')
        self.reply.textChanged.connect(self.update_buttons)
        layout.addWidget(self.reply)
        actions = QHBoxLayout()
        self.draft = self.button(actions, 'Draft with Gemini', self.generate_reply)
        self.copy = self.button(actions, 'Copy reply', self.copy_reply)
        self.send = self.button(actions, 'Send website reply…', self.send_reply)
        self.button(actions, 'Close', self.reject)
        layout.addLayout(actions)
        self.update_buttons()

    @staticmethod
    def button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def open_website(self):
        value = os.environ.get('MY_WEBSITE_ADMIN_URL', '').strip()
        try:
            url = site_origin(value) if value else STUDIO_URL
        except InboxError as error:
            self.status.setText(str(error))
            return
        QDesktopServices.openUrl(QUrl(url))

    def set_watch(self, checked):
        if checked and not self.window.policy.stopped:
            self.timer.start()
            self.refresh_inbox()
        else:
            self.timer.stop()

    def start(self, operation, completed, status):
        if self.worker is not None or self.window.policy.stopped:
            return
        self.status.setText(status)
        self.pending = completed
        self.worker = InboxWorker(operation, self)
        self.worker.completed.connect(self.operation_completed)
        self.worker.failed.connect(self.operation_failed)
        self.worker.finished.connect(self.release_worker)
        self.update_buttons()
        self.worker.start()

    def operation_completed(self, result):
        self.pending(result)

    def operation_failed(self, message):
        self.status.setText(message)
        if self.pending == self.show_inbox:
            self.watch.setChecked(False)

    def release_worker(self):
        self.worker.deleteLater()
        self.worker = None
        self.pending = None
        self.update_buttons()

    def update_buttons(self):
        idle = self.worker is None and not self.window.policy.stopped
        has_reply = bool(self.reply.toPlainText().strip())
        self.refresh.setEnabled(idle)
        self.messages.setEnabled(idle)
        self.manual.setEnabled(idle)
        self.customer.setReadOnly(not idle or self.order is not None)
        self.reply.setReadOnly(not idle)
        self.draft.setEnabled(idle)
        self.copy.setEnabled(idle and has_reply)
        self.send.setEnabled(idle and self.order is not None and has_reply)

    def website_client(self):
        try:
            return StudioInbox.from_environment()
        except InboxError as error:
            self.watch.setChecked(False)
            self.status.setText(str(error))
            return None

    def refresh_inbox(self):
        if self.window.policy.stopped:
            self.watch.setChecked(False)
            return
        if self.worker is not None:
            return
        client = self.website_client()
        if client is not None:
            self.start(client.list_messages, self.show_inbox, 'Reading website inbox…')

    def show_inbox(self, records):
        seen = set(self.history)
        new_ids = [message.id for message in records if message.id not in seen]
        self.history.extend(new_ids)
        watching = self.initial_read and self.watch.isChecked() and not self.window.policy.stopped
        self.initial_read = True
        current = self.messages.currentItem()
        previous = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.messages.blockSignals(True)
        self.messages.clear()
        for message in records:
            item = QListWidgetItem(f'{message.sender} · {message.order_id}')
            item.setData(Qt.ItemDataRole.UserRole, message)
            self.messages.addItem(item)
            if previous == message:
                self.messages.setCurrentItem(item)
        self.messages.blockSignals(False)
        if previous is not None and self.messages.currentItem() is None:
            self.select_message(None, None)
        self.status.setText(f'{len(records)} customer messages.')
        if watching and new_ids and self.voice.isChecked():
            self.window.voice_panel.speak_response(f'{len(new_ids)} new website client messages.')

    def select_message(self, item, _previous):
        message = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self.order = message.order_id if message else None
        self.customer.setPlainText(message.text if message else '')
        self.reply.clear()
        self.update_buttons()

    def new_manual_draft(self):
        self.messages.setCurrentRow(-1)
        self.select_message(None, None)
        self.customer.setFocus()

    def customer_changed(self):
        self.update_buttons()

    def generate_reply(self):
        try:
            messages = reply_messages(self.customer.toPlainText(), self.reply.toPlainText())
            spec = self.window.router.spec('Gemini')
            model = self.window.store.get('model:Gemini', spec.default_model)
            key = self.window.get_key('Gemini')
            ticket = self.window.policy.ticket()
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))
            return
        operation = partial(self.window.router.stream, spec, model, key, messages,
                            partial(self.window.policy.check, ticket), lambda _: None)
        self.start(operation, self.show_reply, 'Drafting a reply with Gemini…')

    def show_reply(self, text):
        self.reply.setPlainText(text.strip())
        self.status.setText('Review the reply and select Send or Copy.')

    def copy_reply(self):
        QApplication.clipboard().setText(self.reply.toPlainText())
        self.status.setText('Reply copied.')

    def send_reply(self):
        text = self.reply.toPlainText().strip()
        if self.order is None or not text:
            return
        if len(text) > MAX_MESSAGE_LENGTH:
            self.status.setText('Keep the reply within 4,000 characters.')
            return
        client = self.website_client()
        if client is None:
            return
        order = self.order
        confirm = QMessageBox(self)
        confirm.setWindowTitle('Send website reply?')
        confirm.setTextFormat(Qt.TextFormat.PlainText)
        confirm.setText(f'Send this reply to website order {order}?\n\n{text}')
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return
        self.start(partial(client.send_reply, order, text), self.reply_confirmed, 'Sending approved reply…')

    def reply_confirmed(self, _message_id):
        self.reply.clear()
        self.status.setText('The website confirmed the reply.')

    def reject(self):
        if self.worker is None:
            self.timer.stop()
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
        else:
            self.timer.stop()
            super().closeEvent(event)
