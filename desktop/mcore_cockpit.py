"""Native M-CORE cockpit; presentation over the existing desktop services."""

from datetime import datetime
import math
from pathlib import Path
import platform

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from core.runtime_profile import APP_NAME
from desktop.activity_panel import STATES
from desktop.attachments import AttachmentError, stage_files, stage_folder
from desktop.prime_ui import PrimeOrb, PrimePalette
from desktop.system_metrics import psutil


DARK = '#031016'
EDGE = '#124753'
CYAN = '#00c9e8'
ICE = '#dbfaff'
DIM = '#75aebd'
GREEN = '#00f7a8'
RED = '#ff5176'
AMBER = '#ffab45'


def label(text='', name=''):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setMinimumWidth(0)
    if name:
        result.setObjectName(name)
    return result


def action(text, fn, name='', *, accessible=None):
    button = QPushButton(text)
    button.clicked.connect(fn)
    if name:
        button.setObjectName(name)
    button.setAccessibleName(accessible or text)
    return button


def card_path(rect, cut):
    path = QPainterPath()
    path.moveTo(rect.left() + cut, rect.top())
    for x, y in ((rect.right(), rect.top()), (rect.right(), rect.bottom() - cut),
                 (rect.right() - cut, rect.bottom()), (rect.left(), rect.bottom()),
                 (rect.left(), rect.top() + cut)):
        path.lineTo(x, y)
    path.closeSubpath()
    return path


class Panel(QWidget):
    """Panel with a true cut-corner outline, independently of text scaling."""

    def __init__(self, title, meta='', control=None):
        super().__init__()
        self.setAccessibleName(title.title() + ' panel')
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 9, 14, 13)
        self.body.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(7)
        heading.addWidget(label('▌', 'mcorePip'))
        heading.addWidget(label(title, 'mcorePanelTitle'), 1)
        if control is not None:
            heading.addWidget(control)
        elif meta:
            heading.addWidget(label(meta, 'mcoreMeta'))
        self.body.addLayout(heading)
        line = QFrame()
        line.setObjectName('mcoreLine')
        line.setFixedHeight(1)
        self.body.addWidget(line)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = 14
        painter.setPen(QPen(QColor(EDGE), 1))
        painter.setBrush(QColor('#061820'))
        painter.drawPath(card_path(r, c))
        painter.setPen(QPen(QColor(CYAN), 1.3))
        painter.drawLine(QPointF(r.left(), r.top() + c), QPointF(r.left() + c, r.top()))
        painter.drawLine(QPointF(r.left() + c, r.top()), QPointF(r.left() + 70, r.top()))
        painter.drawLine(QPointF(r.right() - c, r.bottom()), QPointF(r.right(), r.bottom() - c))
        painter.drawLine(QPointF(r.right() - 54, r.bottom()), QPointF(r.right() - c, r.bottom()))


class Gauge(QWidget):
    """Readout of the app's sampled metric, with an explicit empty state."""

    def __init__(self, title, unit='%'):
        super().__init__()
        self.title, self.unit = title, unit
        self.value = None
        self.setMinimumSize(66, 60)
        self.set_value(None)

    def set_value(self, value):
        if value is not None:
            value = float(value)
        self.value = value
        self.setAccessibleName(f'{self.title}: {self.readout}')
        self.update()

    @property
    def readout(self):
        return f'{self.value:.0f}{self.unit}' if self.value is not None else 'N/A'

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = max(13, min(self.width() / 2 - 5, (self.height() - 18) / 2 - 3))
        centre = QPointF(self.width() / 2, (self.height() - 18) / 2)
        ring = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
        p.setPen(QPen(QColor('#123944'), 3))
        p.drawArc(ring, -45 * 16, 270 * 16)
        p.setPen(QPen(QColor('#16596c'), 1))
        for index in range(25):
            angle = math.radians(135 + 11.25 * index)
            dx, dy = math.cos(angle), math.sin(angle)
            p.drawLine(centre + QPointF(dx, dy) * (radius + 2),
                       centre + QPointF(dx, dy) * (radius + (5 if index % 4 == 0 else 3)))
        if self.value is not None and self.unit == '%':
            p.setPen(QPen(QColor(CYAN), 3))
            p.drawArc(ring, 225 * 16, -round(max(0, min(self.value, 100)) * 270 * 16 / 100))
        p.setPen(QColor(ICE if self.value is not None else DIM))
        p.drawText(ring, Qt.AlignmentFlag.AlignCenter, self.readout)
        p.setPen(QColor(CYAN))
        p.drawText(QRectF(0, self.height() - 17, self.width(), 17),
                   Qt.AlignmentFlag.AlignCenter, self.title)


class Orbit(PrimeOrb):
    """The visual core; orbit motion is decoration, not an audio waveform."""

    def __init__(self):
        super().__init__(PrimePalette())
        self.setMinimumHeight(144)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _colours(self):
        if self.state == 'listening':
            return QColor(GREEN), QColor(CYAN)
        return super()._colours()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bright, secondary = self._colours()
        w, h = self.width(), self.height()
        x, y = w / 2, h * .39
        scale = max(1, min(w * .22, h * .38))
        p.setPen(QPen(QColor('#0d2631'), 1))
        for n in range(1, 8):
            at = h * (.67 + .32 * (n / 7) ** 1.6)
            p.drawLine(QPointF(0, at), QPointF(w, at))
        for n in range(-5, 6):
            p.drawLine(QPointF(x + n * w / 40, h * .67), QPointF(x + n * w / 7, h))
        p.setPen(QPen(QColor('#17616b'), 1))
        for radius in (.45, .72, 1.05, 1.3):
            p.drawEllipse(QPointF(x, h * .77), scale * radius, scale * radius * .33)
        glow = QRadialGradient(QPointF(x, y), scale * .9)
        glow.setColorAt(0, bright.lighter(150))
        tinted = QColor(bright)
        tinted.setAlpha(78)
        glow.setColorAt(.27, tinted)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x, y), scale * .9, scale * .9)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor('#1686a4'), 1))
        r = scale * .53
        p.drawEllipse(QPointF(x, y), r, r)
        for i in (.33, .68):
            p.drawEllipse(QPointF(x, y), r * i, r)
            p.drawEllipse(QPointF(x, y), r, r * i)
        for index, angle in enumerate((-31, 11, 62)):
            p.save()
            p.translate(x, y)
            p.rotate(angle)
            p.setPen(QPen(secondary if index != 2 else bright, 1))
            a, b = scale * (1.22 if index == 1 else 1.03), scale * (.27 + index * .04)
            p.drawEllipse(QPointF(0, 0), a, b)
            phase = self._phase * (index + 1) + index * 2.0
            p.setBrush(bright if index == 2 else secondary)
            p.drawEllipse(QPointF(a * math.cos(phase), b * math.sin(phase)), 2.7, 2.7)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.restore()


class MicSignal(QWidget):
    """Audio-level strip only displays a measured level; no synthetic signal."""

    def __init__(self):
        super().__init__()
        self.active = False
        self.level = 0
        self.setFixedHeight(10)
        self.setAccessibleName('Microphone audio level')

    def set_level(self, level):
        self.level = max(0, min(100, level)) if self.active else 0
        self.update()

    def set_active(self, active):
        self.active = active
        if not active:
            self.set_level(0)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        count = 45
        width = self.width() * .68
        for i in range(count):
            p.setBrush(QColor(GREEN if self.active and i < round(count * self.level / 100) else EDGE))
            p.drawRect(QRectF((self.width() - width) / 2 + width * i / count,
                              4, max(1, width / count - 2), 2))


class AttachmentDrop(QPushButton):
    """Accept only selected local OS paths; staging still uses existing limits."""

    def __init__(self, stage):
        super().__init__('＋  DROP A FILE OR FOLDER')
        self.stage = stage
        self.setObjectName('mcoreDrop')
        self.setAccessibleName('Drop local attachment or open Files and Folders')
        self.setToolTip('Files stay in local staging until separately approved for one turn.')
        self.setAcceptDrops(True)

    @staticmethod
    def valid_paths(paths):
        return bool(paths) and all(p and Path(p).is_absolute()
                                   and p[:2].replace(chr(92), '/') != '//' for p in paths)

    @staticmethod
    def paths(mime):
        urls = mime.urls() if mime.hasUrls() else []
        if not urls or any(not u.isLocalFile() or u.host() for u in urls):
            return []
        paths = [u.toLocalFile() for u in urls]
        return paths if AttachmentDrop.valid_paths(paths) else []

    def dragEnterEvent(self, event):
        if self.isEnabled() and self.paths(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self.paths(event.mimeData())
        if self.isEnabled() and paths and self.stage(paths):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()


class MCoreCockpit(QScrollArea):
    """Reversible whole-window view of the same runtime, with a narrow stack."""

    section = 'M-CORE'

    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        self.setObjectName('mcoreCockpit')
        self.setAccessibleName('JARVIS M-CORE cockpit')
        self.setWidgetResizable(True)
        # A wide desktop view is a preference, not a window minimum.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.surface = QWidget()
        self.surface.setObjectName('mcoreSurface')
        self.setWidget(self.surface)
        self.outer = QVBoxLayout(self.surface)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(0)
        self._compact = None
        self._log = ()
        self._tasks = ''
        self.build_header()
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(14, 13, 14, 13)
        self.grid.setSpacing(12)
        self.outer.addWidget(self.body, 1)
        self.build_panels()
        self.build_footer()
        self.setStyleSheet(STYLE)
        self.reflow()
        self.update_clock()
        self.clock = QTimer(self, interval=1000)
        self.clock.timeout.connect(self.update_clock)
        self.update_attachments(window.attachments)
        window.voice_panel.audio_level.connect(self.signal.set_level)

    def build_header(self):
        self.header = QWidget()
        self.header.setObjectName('mcoreHeader')
        self.header_grid = QGridLayout(self.header)
        self.header_grid.setContentsMargins(15, 9, 15, 9)
        self.header_grid.setSpacing(6)
        self.brand = QWidget()
        brand = QHBoxLayout(self.brand)
        brand.setContentsMargins(0, 0, 0, 0)
        brand.addWidget(label('◉', 'mcoreEmblem'))
        title = QVBoxLayout()
        title.setSpacing(1)
        title.addWidget(label(APP_NAME, 'mcoreBrand'))
        title.addWidget(label('PERSONAL AI SYSTEM', 'mcoreMeta'))
        brand.addLayout(title)
        self.header_actions = QWidget()
        controls = QHBoxLayout(self.header_actions)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        window = self.window_ref
        self.settings_button = action('⚙ Settings', lambda: window.open_section('Settings & Safety'))
        controls.addWidget(self.settings_button)
        self.prime_button = action('PRIME', window.return_from_cockpit,
                                   accessible='Return to PRIME, camera, Terminal and Media')
        controls.addWidget(self.prime_button)
        self.state_chip = label('IDLE', 'mcoreState')
        self.state_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_chip.setMaximumWidth(270)
        self.state_chip.setMinimumWidth(184)
        self.clock_box = QWidget()
        time = QVBoxLayout(self.clock_box)
        time.setContentsMargins(0, 0, 0, 0)
        time.setSpacing(0)
        self.clock_label = label(name='mcoreClock')
        self.date_label = label(name='mcoreMeta')
        for component in (self.clock_label, self.date_label):
            component.setAlignment(Qt.AlignmentFlag.AlignRight)
            time.addWidget(component)
        self.fullscreen_button = action('⛶', window.toggle_fullscreen,
                                       accessible='Toggle full screen')
        self.fullscreen_button.setToolTip('Toggle full screen (F11)')
        self.outer.addWidget(self.header)

    @staticmethod
    def text_panel(placeholder):
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setFrameShape(QFrame.Shape.NoFrame)
        output.setMinimumHeight(42)
        output.setPlainText(placeholder)
        return output

    def build_panels(self):
        window = self.window_ref
        self.systems = Panel('SYSTEMS', 'LOCAL')
        meters = QGridLayout()
        meters.setSpacing(3)
        self.metrics = {}
        for i, (title, key, suffix) in enumerate((
            ('CPU', 'cpu_usage_percent', '%'), ('MEMORY', 'ram_usage_percent', '%'),
            ('GPU', 'gpu_usage_percent', '%'), ('TEMP', 'cpu_temperature_c', '°C'),
        )):
            gauge = self.metrics[key] = Gauge(title, suffix)
            meters.addWidget(gauge, i // 2, i % 2)
        self.systems.body.addLayout(meters, 1)

        self.status = Panel('STATUS')
        details = QGridLayout()
        details.setSpacing(5)
        self.fields = {}
        for row, title in enumerate(('UPTIME', 'PROCESSES', 'NETWORK', 'PLATFORM', 'ENGINE', 'VOICE')):
            details.addWidget(label(title, 'mcoreMeta'), row, 0)
            value = self.fields[title] = label('N/A')
            value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            details.addWidget(value, row, 1)
        self.status.body.addLayout(details, 1)

        self.tasks = Panel('TASKS', control=action(
            'Queue', lambda: window.open_section('Task Queue')))
        self.task_output = self.text_panel('No queued tasks.')
        self.task_output.setAccessibleName('Local task queue status')
        self.tasks.body.addWidget(self.task_output, 1)

        self.voice = Panel('VOICE INTERFACE')
        self.orbit = Orbit()
        self.voice.body.addWidget(self.orbit, 1)
        voice_brand = label(APP_NAME, 'mcoreMeta')
        voice_brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice.body.addWidget(voice_brand)
        self.voice_state = label('IDLE', 'mcoreVoiceState')
        self.voice_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice.body.addWidget(self.voice_state)
        self.signal = MicSignal()
        self.voice.body.addWidget(self.signal)
        voice_controls = QHBoxLayout()
        self.speak_button = action('Speak', window.listen_to_user)
        voice_controls.addWidget(self.speak_button)
        self.live_button = action('Live Voice', window.toggle_live_voice)
        voice_controls.addWidget(self.live_button)
        self.voice.body.addLayout(voice_controls)

        self.news = Panel('NEWS', control=action('Briefing', window.open_news_briefing))
        self.news_output = self.text_panel('No briefing yet. Choose Briefing to fetch news.')
        self.news_output.setAccessibleName('Latest requested news briefing')
        self.news.body.addWidget(self.news_output, 1)

        self.comms = Panel('COMMUNICATIONS', 'LOG')
        self.comms_output = self.text_panel('No messages yet.')
        self.comms_output.setAccessibleName('Current conversation')
        self.comms.body.addWidget(self.comms_output, 1)

        self.command = Panel('COMMAND', 'INPUT')
        self.drop = AttachmentDrop(self.stage_dropped)
        self.drop.clicked.connect(lambda: window.open_section('Files & Folders'))
        self.command.body.addWidget(self.drop)
        self.attachment_label = label('No files staged.', 'mcoreMeta')
        self.attachment_label.setWordWrap(True)
        self.command.body.addWidget(self.attachment_label)
        entry = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setAccessibleName('Type a command or question')
        self.prompt.setPlaceholderText('Type a command or question…')
        self.prompt.returnPressed.connect(self.send_command)
        entry.addWidget(self.prompt, 1)
        self.send = action('➤', self.send_command, accessible='Send command or question')
        entry.addWidget(self.send)
        self.command.body.addLayout(entry)
        buttons = QHBoxLayout()
        self.mic_button = action('Mic: off', self.toggle_microphone, 'mcoreMic')
        buttons.addWidget(self.mic_button, 1)
        self.interrupt_button = action('■  Interrupt', self.interrupt_reply, 'mcoreInterrupt')
        buttons.addWidget(self.interrupt_button, 1)
        self.command.body.addLayout(buttons)
        safety = QHBoxLayout()
        self.stop_button = action('Emergency stop', window.stop, 'mcoreInterrupt')
        safety.addWidget(self.stop_button)
        self.resume_button = action('Resume', window.resume)
        self.resume_button.hide()
        safety.addWidget(self.resume_button)
        self.review_button = action('Review approval', lambda: window.open_section('JARVIS Chat'))
        self.review_button.hide()
        safety.addWidget(self.review_button, 1)
        self.command.body.addLayout(safety)

    def build_footer(self):
        self.footer = QWidget()
        self.footer.setObjectName('mcoreFooter')
        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(14, 5, 14, 5)
        self.link_badges = label(name='mcoreMeta')
        self.link_badges.setWordWrap(True)
        layout.addWidget(self.link_badges, 1)
        shortcuts = 'F4 MUTE  ·  F11 FULLSCREEN  ·  ESC INTERRUPT'
        if not (hasattr(self.window_ref, 'hud_interrupt_reply')
                and hasattr(self.window_ref, 'hud_toggle_microphone')):
            shortcuts = 'F11 FULLSCREEN'
        keys = label(f'{shortcuts}  ·  {APP_NAME}', 'mcoreMeta')
        keys.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        keys.setWordWrap(True)
        layout.addWidget(keys, 1)
        self.outer.addWidget(self.footer)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_clock()
        self.clock.start()
        self.reflow()

    def hideEvent(self, event):
        self.clock.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        # QAbstractScrollArea delivers the viewport's Resize event here.
        # Use its new size before QScrollArea recalculates child/scrollbar
        # geometry against the old wide layout's minimum-size hint.
        if hasattr(self, 'grid'):
            self.reflow(event.size().width())
        super().resizeEvent(event)

    def reflow(self, viewport_width=None):
        width = self.viewport().width() if viewport_width is None else viewport_width
        compact = width < 960
        if self._compact == compact:
            return
        self._compact = compact
        for layout in (self.grid, self.header_grid):
            while layout.count():
                layout.takeAt(0)
        if compact:
            for row, panel in enumerate((
                self.voice, self.command, self.comms, self.news, self.systems, self.status, self.tasks,
            )):
                self.grid.addWidget(panel, row, 0)
                panel.setMinimumHeight(270 if panel is self.voice else 177)
            for column in range(3):
                self.grid.setColumnStretch(column, int(column == 0))
            for row in range(9):
                self.grid.setRowStretch(row, 0)
            self.header_grid.addWidget(self.brand, 0, 0)
            self.header_grid.addWidget(self.clock_box, 0, 1)
            self.header_grid.addWidget(self.fullscreen_button, 0, 2)
            self.header_grid.addWidget(self.header_actions, 1, 0)
            self.header_grid.addWidget(self.state_chip, 1, 1, 1, 2)
        else:
            for panel, row, col, rowspan, height in (
                (self.systems, 0, 0, 3, 163), (self.status, 3, 0, 3, 149),
                (self.tasks, 6, 0, 3, 125), (self.voice, 0, 1, 6, 278),
                (self.news, 6, 1, 3, 145), (self.comms, 0, 2, 6, 250),
                (self.command, 6, 2, 3, 205),
            ):
                self.grid.addWidget(panel, row, col, rowspan, 1)
                panel.setMinimumHeight(height)
            for column, stretch in enumerate((20, 49, 31)):
                self.grid.setColumnStretch(column, stretch)
            for row in range(9):
                self.grid.setRowStretch(row, 1)
            self.header_grid.addWidget(self.brand, 0, 0)
            self.header_grid.addWidget(self.header_actions, 0, 1)
            self.header_grid.addWidget(self.state_chip, 0, 2)
            self.header_grid.setAlignment(self.state_chip, Qt.AlignmentFlag.AlignHCenter)
            self.header_grid.addWidget(self.clock_box, 0, 3)
            self.header_grid.addWidget(self.fullscreen_button, 0, 4)
        for column in range(5):
            self.header_grid.setColumnStretch(column, int(column == (1 if compact else 2)))
        self.surface.updateGeometry()

    def update_clock(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime('%H:%M:%S'))
        self.date_label.setText(now.strftime('%a %d %b %Y'))
        self.clock_box.setAccessibleName(now.strftime('%A, %d %B %Y, %H:%M:%S'))

    def update_metrics(self, data):
        for key, gauge in self.metrics.items():
            gauge.set_value(data.get(key))
        self.fields['NETWORK'].setText(str(data.get('network_status', 'N/A')))
        self.fields['PLATFORM'].setText(platform.system().upper() or 'N/A')
        if self.isVisible():
            try:
                seconds = max(0, int(datetime.now().timestamp() - psutil.boot_time()))
                self.fields['UPTIME'].setText(f'{seconds // 3600} h {(seconds // 60) % 60:02d} m')
                self.fields['PROCESSES'].setText(str(len(psutil.pids())))
            except (OSError, RuntimeError, psutil.Error):
                self.fields['UPTIME'].setText('N/A')
                self.fields['PROCESSES'].setText('N/A')

    def update_runtime(self, state, chat_route):
        window = self.window_ref
        live = window.live_voice
        live_connected = bool(live and live.active and live.state != 'connecting')
        live_mic = bool(live_connected and getattr(live, 'input', None) is not None
                        and live.state != 'speaking')
        panel = window.voice_panel
        active = state != 'stopped' and not panel.microphone_muted and (panel.listening or live_mic)
        connecting = window.live_voice_starting or (live and live.state == 'connecting')
        if live_connected:
            route = 'Active route: Gemini Live'
        elif connecting:
            route = 'Connecting to Gemini Live'
        else:
            title = 'Request route' if window.worker is not None else 'Selected chat route'
            route = title + ': ' + chat_route.removeprefix('Active brain: ')
        status = STATES[state][0].upper()
        tone = (GREEN if state == 'listening' else RED if state in ('stopped', 'error')
                else AMBER if state in ('approval', 'thinking') else CYAN)
        self.orbit.set_state(state)
        self.orbit.set_motion(not window.store.get('omega:reduced', False))
        self.signal.set_active(active)
        for component in (self.state_chip, self.voice_state):
            component.setText(('●  ' if component is self.state_chip else '') + status)
            component.setStyleSheet(f'color: {tone};')
        self.fields['ENGINE'].setText(route)
        voice = ('Gemini Live' if live_connected else 'Connecting' if connecting
                 else 'Speaking' if panel.speaking else 'Not speaking')
        self.fields['VOICE'].setText(voice)
        if panel.microphone_muted:
            mic_label = 'Mic: muted'
        elif active:
            mic_label = 'MIC ACTIVE'
        elif connecting:
            mic_label = 'Mic: connecting'
        elif live_connected:
            mic_label = 'Mic: playback paused' if live.state == 'speaking' else 'Mic: unavailable'
        elif window.audio_test.mode == 'microphone':
            mic_label = 'Mic: testing'
        elif panel.worker is not None and panel.worker.isRunning():
            mic_label = 'Mic: closing'
        else:
            mic_label = 'Mic: ready' if panel.consent.listening else 'Mic: off'
        self.mic_button.setText(mic_label)
        self.mic_button.setAccessibleName(mic_label + '. Microphone access controls')
        self.mic_button.setStyleSheet(f'color: {GREEN if active else ICE};')
        self.mic_button.setEnabled(state != 'stopped')
        # Keep a single truthful provider description; do not infer an active engine
        # from the configured preference.
        self.link_badges.setText(f'● {route}   ·   {mic_label}   ·   PROTOCOL M')
        self.drop.setEnabled(state != 'stopped')
        self.send.setEnabled(state != 'stopped')
        self.resume_button.setVisible(state == 'stopped')
        self.review_button.setVisible(state == 'approval')
        self.live_button.setText('Stop Live Voice' if connecting or (live and live.active)
                                 else 'Live Voice')
        self.live_button.setEnabled(state != 'stopped')
        self.speak_button.setEnabled(state != 'stopped' and not (live and live.active)
                                     and not window.voice_panel.playback_busy)
        self.speak_button.setText('Cancel mic' if window.voice_panel.listening else 'Speak')
        can_interrupt = getattr(window, 'hud_can_interrupt_reply', lambda: live_connected)
        self.interrupt_button.setEnabled(state != 'stopped' and can_interrupt())

    def toggle_microphone(self):
        window = self.window_ref
        fallback = window.prime_shell.mic_mute_button.click
        getattr(window, 'hud_toggle_microphone', fallback)()

    def interrupt_reply(self):
        window = self.window_ref
        getattr(window, 'hud_interrupt_reply', window.interrupt_live_voice)()

    def render(self, messages):
        messages = tuple((row['role'], row['content']) for row in messages)
        if self._log == messages:
            return
        self._log = messages
        if not messages:
            text = 'No messages yet.'
        else:
            text = '\n\n'.join(
                f'{("YOU" if role in ("user", "local command") else APP_NAME)}\n{content}'
                for role, content in messages
            )
        self.comms_output.setPlainText(text)
        self.comms_output.moveCursor(QTextCursor.MoveOperation.End)

    def update_tasks(self, jobs):
        value = '\n'.join(f"{row['app']}: {row['status']}" for row in jobs[:12]) or 'No queued tasks.'
        if value != self._tasks:
            self._tasks = value
            self.task_output.setPlainText(value)

    def update_news(self, text):
        self.news_output.setPlainText(text or 'No briefing yet. Choose Briefing to fetch news.')

    def update_attachments(self, staged):
        text = f'{len(staged)} staged locally. Open Files to review sharing.' if staged else 'No files staged.'
        self.attachment_label.setText(text)

    def stage_dropped(self, paths):
        window = self.window_ref
        if window.policy.stopped or not AttachmentDrop.valid_paths(paths):
            return False
        # A drop never grants provider consent, even if the previous selection
        # had been approved for the next turn. All additions here succeed or none do.
        window.files_share_once.setChecked(False)
        try:
            folders = [path for path in paths if Path(path).is_dir()]
            if folders:
                if len(paths) != 1:
                    raise AttachmentError('Drop one folder or up to 12 files at a time.')
                staged, skipped, truncated = stage_folder(folders[0], window.attachments)
                window.statusBar().showMessage(
                    f'Folder scan: {len(staged)} staged locally, {skipped} skipped'
                    + ('; limit reached, not the entire folder' if truncated else ''), 18000)
            else:
                staged = stage_files(paths, window.attachments)
        except AttachmentError as error:
            window.statusBar().showMessage(str(error), 15000)
            return False
        window.attachments = staged
        window.update_attachment_display()
        return True

    def send_command(self):
        window = self.window_ref
        text = self.prompt.text().strip()
        if not text:
            return
        previous = window.prompt.toPlainText()
        if previous.strip() and previous.strip() != text:
            window.statusBar().showMessage('There is an unsent draft in Chat. Send or clear it there first.', 12000)
            return
        window.prompt.setPlainText(text)
        window.send()
        if not window.prompt.toPlainText().strip():
            self.prompt.clear()
        elif not previous:
            window.prompt.clear()


STYLE = f"""
QWidget#mcoreSurface, QScrollArea#mcoreCockpit {{
    background: {DARK}; color: {ICE};
}}
QWidget#mcoreHeader, QWidget#mcoreFooter {{
    background: #05161e; border: 0px; border-bottom: 1px solid {EDGE};
}}
QWidget#mcoreFooter {{ border-top: 1px solid {EDGE}; border-bottom: none; }}
QWidget#mcoreSurface QLabel {{ color: {ICE}; background: transparent; }}
QWidget#mcoreSurface QLabel#mcorePanelTitle {{ color: {CYAN}; font-weight: 700; letter-spacing: 2px; }}
QWidget#mcoreSurface QLabel#mcorePip {{ color: {AMBER}; }}
QWidget#mcoreSurface QLabel#mcoreEmblem {{ color: {CYAN}; font-size: 28px; }}
QWidget#mcoreSurface QLabel#mcoreBrand {{ color: {ICE}; font-size: 22px; letter-spacing: 4px; }}
QWidget#mcoreSurface QLabel#mcoreMeta {{ color: {DIM}; font-size: 10px; letter-spacing: 1px; }}
QWidget#mcoreSurface QLabel#mcoreClock {{ color: {ICE}; font-size: 23px; letter-spacing: 2px; }}
QWidget#mcoreSurface QLabel#mcoreState {{
    background: #031c22; border: 1px solid {EDGE}; padding: 5px 12px;
    font-weight: 700; letter-spacing: 2px;
}}
QWidget#mcoreSurface QLabel#mcoreVoiceState {{ font-size: 15px; font-weight: 700; letter-spacing: 3px; }}
QFrame#mcoreLine {{ background: {EDGE}; border: none; }}
QWidget#mcoreSurface QPushButton {{
    border: 1px solid {EDGE}; background: #061b24; color: {ICE}; padding: 5px 8px;
}}
QWidget#mcoreSurface QPushButton:hover, QWidget#mcoreSurface QPushButton:focus {{
    border-color: {CYAN};
}}
QWidget#mcoreSurface QPushButton:disabled {{ color: {DIM}; background: #06121a; }}
QWidget#mcoreSurface QPushButton#mcoreDrop {{
    border: 1px dashed {CYAN}; padding: 10px 4px; letter-spacing: 1px; color: {CYAN};
}}
QWidget#mcoreSurface QPushButton#mcoreMic {{ color: {GREEN}; }}
QWidget#mcoreSurface QPushButton#mcoreInterrupt {{ color: {RED}; border-color: #713143; }}
QWidget#mcoreSurface QLineEdit {{
    border: 1px solid {EDGE}; background: #04151d; color: {ICE}; padding: 7px;
}}
QWidget#mcoreSurface QLineEdit:focus {{ border-color: {CYAN}; }}
QWidget#mcoreSurface QPlainTextEdit {{
    background: #04141b; color: {ICE}; border: none; padding: 2px;
    selection-background-color: #17526b;
}}
QWidget#mcoreSurface QScrollBar:vertical {{ background: #04141b; width: 8px; }}
QWidget#mcoreSurface QScrollBar::handle:vertical {{
    background: #1a576b; min-height: 25px;
}}
"""
