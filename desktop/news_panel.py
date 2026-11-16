"""Controls and results for the optional Tamil news briefing."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QPlainTextEdit, QPushButton, QSpinBox

from news.briefing import REGIONS


class NewsPanel(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('Tamil news briefing')
        self.resize(660, 480)
        layout = QFormLayout(self)
        self.region = QComboBox()
        for key, label in REGIONS.items():
            self.region.addItem(label, key)
        layout.addRow('Region', self.region)
        self.interval = QSpinBox()
        self.interval.setRange(15, 1440)
        self.interval.setValue(120)
        self.interval.setSuffix(' min')
        layout.addRow('Interval', self.interval)
        self.schedule = QCheckBox('Brief automatically while JARVIS is open')
        self.speech = QCheckBox('Read Tamil briefing aloud')
        layout.addRow(self.schedule)
        layout.addRow(self.speech)
        self.fetch_button = QPushButton('Fetch news now')
        self.fetch_button.clicked.connect(self.fetch_now)
        layout.addRow(self.fetch_button)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addRow(self.output)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_now)
        self.schedule.toggled.connect(self.update_timer)
        self.interval.valueChanged.connect(self.update_timer)

    def update_timer(self):
        if self.schedule.isChecked() and not self.window.policy.stopped:
            self.timer.start(self.interval.value() * 60_000)
        else:
            self.timer.stop()

    def disable_schedule(self):
        self.schedule.setChecked(False)
        self.timer.stop()

    def fetch_now(self):
        self.window.start_news_briefing(self.region.currentData())
