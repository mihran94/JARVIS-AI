"""Omega presentation for the existing JARVIS window and services."""
from datetime import datetime, timezone
import json
from urllib.parse import urlencode
from xml.etree.ElementTree import ParseError

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QSize, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from desktop.global_hotkey import DEFAULT_SHORTCUT
from desktop.omega_visuals import BACKGROUNDS, THEMES, Backdrop, Reactor, SignalMeter, dock_icon, theme_sheet
from news.briefing import FEEDS, MAX_FEED_BYTES, parse_feed


DESTINATIONS = {
    'Home': ('JARVIS Chat', '⌂'),
    'AI Chat': ('JARVIS Chat', '▤'),
    'Code Studio': ('Coding Assistant', '‹›'),
    'PC Control': ('PC Control', '▣'),
    'Devices': ('Phone Remote', '◇'),
    'Memory': ('Memory', '◎'),
    'Mission': ('Mission Control', '◈'),
    'Cybersecurity': ('Cybersecurity', '⬢'),
    'Player': ('Quantum Visual Player', '▶'),
    'Creative Studio': ('Video Editor', '▷'),
    'Automation': ('Step Workflows', '⇄'),
    'Security': ('Settings & Safety', '⬡'),
    'Settings': ('Settings & Safety', '⚙'),
}
MODES = ('Omega', 'Island')
ACTIVITY = {
    'idle': 'Idle', 'listening': 'Listening', 'thinking': 'Thinking',
    'responding': 'Answering', 'speaking': 'Speaking', 'coding': 'Coding',
    'working': 'Working', 'approval': 'Approval required', 'stopped': 'Stopped',
}


def setting(store, key, choices, default):
    candidate = store.get('omega:' + key, default)
    return candidate if candidate in choices else default


def label(text='', style=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if style:
        widget.setObjectName(style)
    return widget


def button(layout, title, callback, *, primary=False):
    control = QPushButton(title)
    control.clicked.connect(lambda _checked=False: callback())
    if primary:
        control.setObjectName('omegaPrimary')
    layout.addWidget(control)
    return control


def frame(layout, object_name='omegaCard'):
    panel = QFrame()
    panel.setObjectName(object_name)
    inner = QVBoxLayout(panel)
    inner.setContentsMargins(17, 15, 17, 15)
    inner.setSpacing(10)
    layout.addWidget(panel)
    return inner


class DockButton(QToolButton):
    def __init__(self, name, symbol, action, parent):
        super().__init__(parent)
        self.name = name
        self.symbol = symbol
        self.power = True
        self.setText('Creative' if name == 'Creative Studio' else name)
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(61)
        self.setIconSize(QSize(25, 25))
        self.clicked.connect(action)
        self.zoom = QVariantAnimation(self)
        self.zoom.setDuration(135)
        self.zoom.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.zoom.valueChanged.connect(self.scale_icon)

    def scale_icon(self, value):
        self.setIconSize(QSize(int(value), int(value)))

    def magnify(self, target):
        self.zoom.stop()
        if not self.power:
            self.scale_icon(25)
            return
        self.zoom.setStartValue(self.iconSize().width())
        self.zoom.setEndValue(target)
        self.zoom.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.magnify(39)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.magnify(25)

    def keyPressEvent(self, event):
        key = event.key()
        siblings = self.parent().buttons
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
            index = siblings.index(self)
            if key == Qt.Key.Key_Home:
                index = 0
            elif key == Qt.Key.Key_End:
                index = -1
            else:
                index += 1 if key == Qt.Key.Key_Right else -1
            siblings[index % len(siblings)].setFocus()
            event.accept()
        else:
            super().keyPressEvent(event)


class Dock(QFrame):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setObjectName('omegaDock')
        self.setAccessibleName('JARVIS application dock')
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(6, 5, 6, 5)
        self.row.setSpacing(4)
        self.buttons = []
        self.reorder()

    def reorder(self):
        for control in self.buttons:
            self.row.removeWidget(control)
            control.deleteLater()
        self.buttons.clear()
        for name in self.controller.order:
            page, symbol = DESTINATIONS[name]
            control = DockButton(name, symbol,
                                 lambda _checked=False, page=page: self.controller.open_page(page), self)
            self.buttons.append(control)
            self.row.addWidget(control, 1)
        self.sync_style()
        self.update_active()

    def sync_style(self):
        palette = THEMES[self.controller.theme]
        for item in self.buttons:
            item.power = not self.controller.reduced
            item.setIcon(dock_icon(item.symbol, palette[0] if item.property('active') else palette[5]))
            if not item.power:
                item.magnify(25)

    def update_active(self):
        window = self.controller.window
        for item in self.buttons:
            active = window.pages.currentIndex() == window.page_indices[DESTINATIONS[item.name][0]]
            if item.property('active') != active:
                item.setProperty('active', active)
                item.style().unpolish(item)
                item.style().polish(item)
                palette = THEMES[self.controller.theme]
                item.setIcon(dock_icon(item.symbol, palette[0] if active else palette[5]))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if self.width() < 965
                 else Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for item in self.buttons:
            item.setToolButtonStyle(style)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.controller.auto_hide and not any(item.hasFocus() for item in self.buttons):
            self.controller.show_dock(False)


class FloatingAssistant(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setObjectName('omegaFloat')
        self.setWindowTitle('JARVIS floating assistant')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.drag = None
        self.origin = None
        self.moved = False
        self.expanded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        panel = QWidget()
        panel.setObjectName('omegaFloatPanel')
        layout.addWidget(panel)
        interior = QVBoxLayout(panel)
        interior.setContentsMargins(8, 6, 8, 6)
        row = QHBoxLayout()
        interior.addLayout(row)
        self.orb = Reactor(compact=True)
        self.orb.setFixedSize(48, 48)
        self.orb.installEventFilter(self)
        row.addWidget(self.orb)
        self.handle = label('JARVIS · Idle', 'omegaState')
        self.handle.installEventFilter(self)
        row.addWidget(self.handle, 1)
        self.toggle = button(row, 'Expand', self.flip)
        self.toggle.setAccessibleName('Expand or collapse assistant')
        self.contents = QWidget()
        expanded = QVBoxLayout(self.contents)
        expanded.setContentsMargins(3, 4, 3, 4)
        controls = QHBoxLayout()
        self.mic = button(controls, 'Talk', controller.toggle_mic)
        self.assistant = button(controls, 'Assistant', lambda: controller.open_page('JARVIS Chat'))
        button(controls, 'Stop', controller.window.stop)
        expanded.addLayout(controls)
        self.command = QLineEdit()
        self.command.setAccessibleName('Quick command')
        self.command.setPlaceholderText('Ask JARVIS…')
        self.command.returnPressed.connect(lambda: controller.submit(self.command))
        expanded.addWidget(self.command)
        self.notice = label('', 'omegaMuted')
        self.notice.setMaximumHeight(48)
        expanded.addWidget(self.notice)
        interior.addWidget(self.contents)

    def apply_flags(self):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.controller.pin:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.windowFlags() != flags:
            visible = self.isVisible()
            self.setWindowFlags(flags)
            if visible:
                self.show()

    def set_mode(self, mode):
        self.apply_flags()
        self.expanded = False
        self.sync_shape()
        self.place_on_screen()

    def sync_shape(self):
        # The retired Stealth presentation is gone: the mode is validated
        # against MODES on read and on switch, so only Omega and Island exist.
        self.handle.setVisible(True)
        self.toggle.setVisible(True)
        self.contents.setVisible(self.expanded)
        self.toggle.setText('Collapse' if self.expanded else 'Expand')
        self.setFixedWidth(348 if self.expanded else 286)
        self.layout().activate()
        self.setFixedHeight(self.sizeHint().height())

    def flip(self):
        self.expanded = not self.expanded
        self.sync_shape()
        self.place_on_screen()
        if self.expanded and not self.controller.reduced:
            fade_in(self.contents, 190)

    def place_on_screen(self, pos=None):
        if pos is None:
            saved = self.controller.store.get('omega:float_position')
            pos = QPoint(*saved) if isinstance(saved, list) and len(saved) == 2 and all(
                type(point) is int for point in saved) else None
        screen = QGuiApplication.screenAt(pos) if pos is not None else None
        screen = screen or self.controller.window.screen() or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if pos is None:
            pos = QPoint(area.right()-self.width()-24, area.top()+28)
        self.move(max(area.left(), min(pos.x(), area.right()-self.width()+1)),
                  max(area.top(), min(pos.y(), area.bottom()-self.height()+1)))

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.drag, self.origin = event.globalPosition().toPoint(), self.pos()
            self.moved = False
            obj.grabMouse()
            return True
        if kind == QEvent.Type.MouseMove and self.drag is not None:
            delta = event.globalPosition().toPoint() - self.drag
            if self.moved or delta.manhattanLength() >= 5:
                self.moved = True
                self.place_on_screen(self.origin + delta)
            return True
        if kind == QEvent.Type.MouseButtonRelease and self.drag is not None:
            self.drag = None
            obj.releaseMouse()
            if self.moved:
                self.controller.store.set('omega:float_position', [self.x(), self.y()])
            else:
                self.flip()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.controller.switch('Omega')
            event.accept()
        elif event.key() == Qt.Key.Key_Space and self.focusWidget() is not self.command:
            self.flip()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.controller.switch('Omega')


def fade_in(widget, milliseconds):
    previous = getattr(widget, '_omega_fade', None)
    if previous is not None:
        previous.stop()
        previous.deleteLater()
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    fade = QVariantAnimation(widget)
    fade.setDuration(milliseconds)
    fade.setStartValue(.30)
    fade.setEndValue(1.0)
    fade.valueChanged.connect(effect.setOpacity)
    fade.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._omega_fade = fade
    fade.start()


class Feeds:
    def __init__(self, controller):
        self.controller = controller
        self.manager = QNetworkAccessManager(controller.window)
        self.replies = set()
        self.job = 0

    def abort(self):
        self.job += 1
        for reply in list(self.replies):
            reply.abort()
        self.controller.refresh_feed.setEnabled(not self.controller.window.policy.stopped)

    def request(self, url, limit, consume):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(7000)
        request.setRawHeader(b'User-Agent', b'JARVIS AI Omega')
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.manager.get(request)
        self.replies.add(reply)

        def progress(received, _total):
            if received > limit:
                reply.abort()

        def finish():
            self.replies.discard(reply)
            code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            payload = bytes(reply.readAll()) if code == 200 and reply.error().value == 0 else b''
            reply.deleteLater()
            consume(payload if len(payload) <= limit else b'')

        reply.downloadProgress.connect(progress)
        reply.finished.connect(finish)

    def refresh(self):
        ui = self.controller
        if self.replies or ui.window.policy.stopped:
            return
        self.job += 1
        generation = self.job
        ui.refresh_feed.setEnabled(False)
        ui.weather_value.setText('Fetching…')
        ui.news_value.setText('Fetching…')
        place = ui.location.text().strip() or 'Selected coordinates'
        pending = len(FEEDS) + 1
        headlines = {}

        def finish():
            nonlocal pending
            pending -= 1
            if not pending:
                ui.refresh_feed.setEnabled(not ui.window.policy.stopped)

        def weather(payload):
            if generation != self.job:
                return
            try:
                data = json.loads(payload)
                value = data['current']['temperature_2m']
                units = data['current_units']['temperature_2m']
                stamp = datetime.fromisoformat(data['current']['time'])
                if type(value) not in (float, int) or units != '°C':
                    raise ValueError('Invalid temperature')
                ui.weather_value.setText(f'{value:.0f} °C')
                ui.weather_detail.setText(
                    f'{place} · {stamp:%H:%M} local · Open-Meteo')
            except (TypeError, KeyError, ValueError):
                ui.weather_value.setText('Unavailable')
                ui.weather_detail.setText(f'{place} · Open-Meteo')
            finish()

        def news(region, publisher, payload):
            if generation != self.job:
                return
            try:
                rows = parse_feed(payload, region, publisher) if payload else []
            except (ValueError, ParseError):
                rows = []
            headlines[region] = [f'{publisher}  ·  {row.title}' for row in rows[:1]]
            if len(headlines) == len(FEEDS):
                lines = [line for area in FEEDS for line in headlines[area]]
                ui.news_value.setText('\n\n'.join(lines) or 'Headlines unavailable')
                ui.news_detail.setText(
                    'Some feeds unavailable' if 0 < len(lines) < len(FEEDS)
                    else 'franceinfo & EconomyNext')
            finish()

        query = urlencode({'latitude': ui.latitude.value(), 'longitude': ui.longitude.value(),
                           'current': 'temperature_2m', 'timezone': 'auto'})
        self.request('https://api.open-meteo.com/v1/forecast?' + query, 64000, weather)
        for region, (publisher, url) in FEEDS.items():
            self.request(url, MAX_FEED_BYTES,
                         lambda payload, region=region, publisher=publisher: news(region, publisher, payload))


class HomeBackdrop(Backdrop):
    def set_columns(self, columns, sides):
        self.columns = columns
        self.sides = sides
        self.compact = False

    def apply_compact(self):
        """Reflow for the width the backdrop has right now.

        The window can be resized and a page can be opened in the same step,
        and the layout runs after both. Reading the width in the resize
        event alone therefore uses the width from before the reflow, and the
        home stays wide when it should be compact.
        """
        compact = self.width() < 850
        if hasattr(self, 'columns') and compact != self.compact:
            self.compact = compact
            for group in self.sides:
                self.columns.removeItem(group)
            left, middle, right = self.sides
            if compact:
                self.columns.addLayout(middle, 0, 0, 1, 2)
                self.columns.addLayout(left, 1, 0)
                self.columns.addLayout(right, 1, 1)
                self.columns.setColumnStretch(0, 1)
                self.columns.setColumnStretch(1, 1)
                self.columns.setColumnStretch(2, 0)
            else:
                self.columns.addLayout(left, 0, 0)
                self.columns.addLayout(middle, 0, 1)
                self.columns.addLayout(right, 0, 2)
                self.columns.setColumnStretch(0, 2)
                self.columns.setColumnStretch(1, 4)
                self.columns.setColumnStretch(2, 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_compact()


class Omega:
    def __init__(self, window):
        self.window = window
        self.store = window.store
        self.theme = window.interface_theme
        self.background = setting(self.store, 'background', BACKGROUNDS, BACKGROUNDS[0])
        self.mode = setting(self.store, 'mode', MODES, 'Omega')
        self.reduced = bool(self.store.get('omega:reduced', False))
        self.pin = bool(self.store.get('omega:pin', False))
        self.auto_hide = bool(self.store.get('omega:auto_hide', False))
        # The old dashboard/dock is kept as a harmless internal fixture for
        # compatibility tests, never as an alternative production interface.
        raw_order = self.store.get('omega:order', [])
        self.order = list(dict.fromkeys(name for name in raw_order if isinstance(name, str)
                                        and name in DESTINATIONS)) if isinstance(raw_order, list) else []
        self.order.extend(name for name in DESTINATIONS if name not in self.order)
        self.voice_state = 'idle'
        self.approval = False
        self.build_home()
        self.build_settings()
        self.floating = FloatingAssistant(self)
        self.feeds = Feeds(self)
        self.dock = Dock(self)
        self.dock.setParent(window)
        self.reveal = QPushButton('Show dock', window)
        self.reveal.setAccessibleName('Show or hide application dock')
        self.reveal.clicked.connect(lambda: self.show_dock(not self.dock.isVisible()))
        window.pages.currentChanged.connect(self.dock.update_active)
        window.statusBar().messageChanged.connect(self.on_notice)
        self.apply_theme()
        self.show_dock(not self.auto_hide)

    def build_home(self):
        home = HomeBackdrop()
        home.setObjectName('omegaFrame')
        self.home = home
        outer = QVBoxLayout(home)
        outer.setContentsMargins(18, 12, 18, 13)
        outer.setSpacing(12)
        top = QHBoxLayout()
        title = QVBoxLayout()
        self.brand = label('JARVIS  OMEGA', 'omegaTitle')
        title.addWidget(self.brand)
        title.addWidget(label('COMMAND CENTER', 'omegaEyebrow'))
        top.addLayout(title, 1)
        self.startup = label('', 'omegaState')
        top.addWidget(self.startup)
        self.skip = button(top, 'Skip Animation', self.finish_intro)
        self.skip.hide()
        self.activity_label = label('Idle', 'omegaState')
        self.clock = label('', 'omegaMuted')
        top.addWidget(self.activity_label)
        self.signal_meter = SignalMeter()
        top.addWidget(self.signal_meter)
        top.addWidget(self.clock)
        button(top, 'Island', lambda: self.switch('Island'))
        button(top, 'Window', self.window.toggle_fullscreen)
        outer.addLayout(top)

        center = QGridLayout()
        center.setHorizontalSpacing(15)
        center.setColumnStretch(0, 2)
        center.setColumnStretch(1, 4)
        center.setColumnStretch(2, 2)
        left = QVBoxLayout()
        system = frame(left)
        system.addWidget(label('PC TELEMETRY', 'omegaEyebrow'))
        self.metric_values = {}
        self.metric_bars = {}
        for title, key in (('CPU', 'cpu_usage_percent'), ('RAM', 'ram_usage_percent')):
            row = QHBoxLayout()
            row.addWidget(label(title), 1)
            value = label('Collecting…', 'omegaValue')
            row.addWidget(value)
            self.metric_values[key] = value
            system.addLayout(row)
            meter = QProgressBar()
            meter.setRange(0, 100)
            meter.setTextVisible(False)
            meter.setFixedHeight(4)
            meter.setAccessibleName(title + ' usage')
            meter.hide()
            self.metric_bars[key] = meter
            system.addWidget(meter)
        self.network = label('', 'omegaMuted')
        system.addWidget(self.network)
        device = frame(left)
        device.addWidget(label('DEVICES', 'omegaEyebrow'))
        self.devices = label('Bridge stopped')
        device.addWidget(self.devices)
        button(device, 'Manage devices', lambda: self.open_page('Phone Remote'))
        routines = frame(left)
        routines.addWidget(label('WORKSPACE', 'omegaEyebrow'))
        button(routines, 'Memory', lambda: self.open_page('Memory'))
        button(routines, 'Automation', lambda: self.open_page('Step Workflows'))
        left.addStretch(1)
        center.addLayout(left, 0, 0)

        middle = QVBoxLayout()
        self.reactor = Reactor()
        middle.addWidget(self.reactor, 1)
        self.ai_note = label('', 'omegaMuted')
        self.ai_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle.addWidget(self.ai_note)
        center.addLayout(middle, 0, 1)

        right = QVBoxLayout()
        weather = frame(right)
        weather.addWidget(label('CURRENT WEATHER', 'omegaEyebrow'))
        self.weather_value = label('—', 'omegaValue')
        self.weather_detail = label('Open-Meteo · refresh to load', 'omegaMuted')
        weather.addWidget(self.weather_value)
        weather.addWidget(self.weather_detail)
        news = frame(right)
        news.addWidget(label('TOP HEADLINES', 'omegaEyebrow'))
        self.news_value = label('Refresh to load France and Sri Lanka headlines.')
        self.news_value.setMaximumHeight(170)
        news.addWidget(self.news_value)
        self.news_detail = label('franceinfo & EconomyNext', 'omegaMuted')
        news.addWidget(self.news_detail)
        self.refresh_feed = button(news, 'Refresh weather and news', lambda: self.feeds.refresh())
        button(news, 'Open Tamil briefing', self.window.open_news_briefing)
        right.addStretch(1)
        center.addLayout(right, 0, 2)
        home.set_columns(center, (left, middle, right))
        outer.addLayout(center, 1)

        composer_panel = QFrame()
        composer_panel.setObjectName('omegaComposer')
        composer = QHBoxLayout(composer_panel)
        self.mic = button(composer, 'Talk', self.toggle_mic)
        self.command = QLineEdit()
        self.command.setAccessibleName('JARVIS command')
        self.command.setPlaceholderText('Ask JARVIS anything…')
        self.command.returnPressed.connect(lambda: self.submit(self.command))
        composer.addWidget(self.command, 1)
        self.send = button(composer, 'Send', lambda: self.submit(self.command), primary=True)
        outer.addWidget(composer_panel)
        home.setParent(self.window)
        home.hide()

    def build_settings(self):
        page = QWidget()
        page.setObjectName('omegaFrame')
        form = QFormLayout(page)
        form.addRow(label('Omega Settings', 'omegaTitle'))
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(THEMES)
        self.theme_selector.setCurrentText(self.theme)
        self.theme_selector.currentTextChanged.connect(self.set_theme)
        form.addRow('Theme', self.theme_selector)
        background = QComboBox()
        background.addItems(BACKGROUNDS)
        background.setCurrentText(self.background)
        background.currentTextChanged.connect(self.set_background)
        form.addRow('Background', background)
        self.mode_select = QComboBox()
        self.mode_select.addItems(MODES)
        self.mode_select.setCurrentText(self.mode)
        self.mode_select.currentTextChanged.connect(self.switch)
        form.addRow('Display mode', self.mode_select)
        for key, title, current, callback in (
            ('reduced', 'Reduce motion', self.reduced, self.set_reduced),
            ('pin', 'Keep floating assistant above other windows', self.pin, self.set_pin),
            ('auto_hide', 'Auto-hide dock', self.auto_hide, self.set_auto_hide),
            ('intro', 'Play startup animation', bool(self.store.get('omega:intro', True)), None),
            ('greet', 'Speak a greeting on startup', bool(self.store.get('omega:greet', False)), None),
        ):
            check = QCheckBox(title)
            check.setChecked(current)
            check.toggled.connect(callback or (lambda enabled, key=key: self.store.set('omega:' + key, enabled)))
            form.addRow(check)

        self.greeting = QLineEdit(self.store.get(
            'omega:greeting', 'Welcome. JARVIS is ready for your command.'))
        self.greeting.setMaxLength(160)
        self.greeting.editingFinished.connect(
            lambda: self.store.set('omega:greeting', self.greeting.text().strip()))
        form.addRow('Startup greeting', self.greeting)

        self.location = QLineEdit(self.store.get('omega:location', 'Paris, France'))
        self.location.setMaxLength(80)
        self.location.editingFinished.connect(
            lambda: self.store.set('omega:location', self.location.text().strip()))
        form.addRow('Weather label', self.location)
        self.latitude = QDoubleSpinBox()
        self.longitude = QDoubleSpinBox()
        for spin, key, bound, value in (
            (self.latitude, 'latitude', 90, 48.8566),
            (self.longitude, 'longitude', 180, 2.3522),
        ):
            spin.setRange(-bound, bound)
            spin.setDecimals(4)
            spin.setValue(self.store.get('omega:' + key, value))
            spin.valueChanged.connect(lambda selected, key=key: self.store.set('omega:' + key, selected))
            form.addRow(key.title(), spin)
        order = QHBoxLayout()
        self.order_items = QComboBox()
        self.order_items.addItems(self.order)
        order.addWidget(self.order_items, 1)
        button(order, 'Move left', lambda: self.move_dock(-1))
        button(order, 'Move right', lambda: self.move_dock(1))
        form.addRow('Dock order', order)
        dock_controls = QHBoxLayout()
        button(dock_controls, 'Toggle advanced dock',
               lambda: self.show_dock(not self.dock.isVisible()))
        form.addRow(dock_controls)
        hotkey_row = QHBoxLayout()
        self.hotkey_input = QLineEdit(str(self.store.get('hotkey:shortcut', DEFAULT_SHORTCUT)))
        self.hotkey_input.setMaxLength(40)
        self.hotkey_input.setPlaceholderText(DEFAULT_SHORTCUT)
        self.hotkey_input.setToolTip(
            'Press this key in any application to bring JARVIS up. It does not open the microphone.')
        hotkey_row.addWidget(self.hotkey_input, 1)
        button(hotkey_row, 'Apply', lambda: self.window.apply_hotkey(self.hotkey_input.text()))
        form.addRow('Key that brings JARVIS up', hotkey_row)
        self.hotkey_status = QLabel(getattr(self.window, 'hotkey_status', ''))
        self.hotkey_status.setWordWrap(True)
        form.addRow(self.hotkey_status)
        tools = QHBoxLayout()
        button(tools, 'AI providers', lambda: self.open_page('AI Providers'))
        button(tools, 'Voice settings', lambda: self.open_page('Voice / Hey Jarvis'))
        button(tools, 'Settings & safety', lambda: self.open_page('Settings & Safety'))
        form.addRow(tools)
        page.setParent(self.window)
        page.hide()

    def start(self, *, smoke=False):
        # PRIME is the only production desktop interface. Island remains the
        # compact companion; older presentation preferences cannot revive the
        # retired OMEGA dashboard, dock or animated introduction.
        self.switch('Omega' if smoke else self.mode, persist=False)
        if self.mode == 'Omega':
            self.open_page('JARVIS Chat')
        self.show_dock(False)
        self.refresh_state()
        if not smoke and self.store.get('omega:greet', False):
            QTimer.singleShot(700, self.greet)

    def greet(self):
        text = self.greeting.text().strip()
        if text and not self.window.policy.stopped:
            self.window.voice_panel.speak_response(text)

    def finish_intro(self):
        if hasattr(self, 'intro_timer'):
            self.intro_timer.stop()
        self.stop_fade(self.brand)
        self.startup.clear()
        self.skip.hide()
        self.refresh_state()

    def open_page(self, page):
        # Old links and saved commands must resolve into PRIME, never into
        # the retired OMEGA dashboard or duplicate settings panel.
        page = {'Omega Home': 'JARVIS Chat',
                'Omega Settings': 'Settings & Safety'}.get(page, page)
        if self.mode != 'Omega':
            self.switch('Omega')
        self.window.open_section(page)
        if self.auto_hide:
            self.show_dock(False)
        # The layout runs after the page is opened, so the home is reflowed
        # for the width it really has.
        QTimer.singleShot(0, self.home.apply_compact)

    def switch(self, mode, persist=True):
        if mode not in MODES:
            return
        self.mode = mode
        if persist:
            self.store.set('omega:mode', mode)
        previous = self.mode_select.blockSignals(True)
        self.mode_select.setCurrentText(mode)
        self.mode_select.blockSignals(previous)
        if mode == 'Omega':
            self.floating.hide()
            # Keep the taskbar/window controls accessible in ordinary desktop mode.
            # F11 and the Window control remain available for optional fullscreen.
            self.window.showMaximized()
        else:
            self.window.hide()
            self.floating.set_mode(mode)
            self.floating.show()
        self.refresh_state()

    def set_theme(self, theme):
        if theme not in THEMES:
            return
        self.theme = self.window.interface_theme = theme
        self.store.set('omega:theme', theme)
        for selector in (self.theme_selector, self.window.theme_choice):
            blocked = selector.blockSignals(True)
            selector.setCurrentText(theme)
            selector.blockSignals(blocked)
        self.apply_theme()

    def apply_theme(self):
        sheet = theme_sheet(self.theme)
        self.window.setStyleSheet(sheet)
        self.floating.setStyleSheet(sheet)
        self.home.theme = self.theme
        self.signal_meter.theme = self.theme
        self.signal_meter.update()
        self.home.background = self.background
        for widget in (self.reactor, self.floating.orb, self.window.chat_reactor):
            widget.theme = self.theme
            widget.set_motion(not self.reduced)
        self.dock.sync_style()
        self.home.update()

    def set_background(self, selected):
        self.background = self.home.background = selected
        self.store.set('omega:background', selected)
        self.home.update()

    def set_reduced(self, enabled):
        self.reduced = enabled
        self.store.set('omega:reduced', enabled)
        if enabled:
            self.finish_intro()
            self.stop_fade(self.floating.contents)
        self.apply_theme()

    @staticmethod
    def stop_fade(widget):
        animation = getattr(widget, '_omega_fade', None)
        if animation is not None:
            animation.stop()
            widget.setGraphicsEffect(None)
            animation.deleteLater()
            widget._omega_fade = None

    def set_pin(self, enabled):
        self.pin = enabled
        self.store.set('omega:pin', enabled)
        self.floating.apply_flags()

    def set_auto_hide(self, enabled):
        self.auto_hide = enabled
        self.store.set('omega:auto_hide', enabled)
        self.show_dock(not enabled)

    def show_dock(self, _visible):
        self.dock.hide()
        self.reveal.hide()

    def move_dock(self, direction):
        index = self.order_items.currentIndex()
        target = index + direction
        if not 0 <= index < len(self.order) or not 0 <= target < len(self.order):
            return
        self.order[index], self.order[target] = self.order[target], self.order[index]
        self.store.set('omega:order', self.order)
        self.order_items.clear()
        self.order_items.addItems(self.order)
        self.order_items.setCurrentIndex(target)
        self.dock.reorder()

    def update_metrics(self, data):
        now = datetime.now()
        self.clock.setText(now.strftime('%H:%M · %d %b'))
        for key, widget in self.metric_values.items():
            if key in data:
                value = data.get(key)
                widget.setText('Unavailable' if value is None else f'{value:.0f}%')
                meter = self.metric_bars[key]
                meter.setVisible(value is not None)
                if value is not None:
                    meter.setValue(round(value))
        if data.get('network_status'):
            self.network.setText(data['network_status'])
        elif not self.network.text():
            self.network.setText('Collecting local metrics…')
        bridge = self.window.bridge
        paired = [device for device in bridge.pairing.devices() if not device.revoked]
        readings = [device.last_seen_epoch_ms for device in paired if device.last_seen_epoch_ms]
        suffix = ('\nLast check-in ' + datetime.fromtimestamp(
            max(readings)/1000, tz=timezone.utc).astimezone().strftime('%d %b %H:%M')) if readings else ''
        self.devices.setText(
            f'Bridge {"listening" if bridge.listener.running else "stopped"} · {len(paired)} paired'
            + suffix)

    def set_voice(self, state):
        if state != 'listening' and self.voice_state == 'listening':
            self.audio_level(0)
        self.voice_state = state
        self.refresh_state()

    def set_approval(self, waiting):
        self.approval = waiting
        self.refresh_state()

    def refresh_state(self):
        state = self.voice_state
        window = self.window
        if window.policy.stopped:
            state = 'stopped'
        elif self.approval or window.chat_launch is not None:
            state = 'approval'
        elif window.worker_kind in ('coding', 'code_generation', 'code_repair', 'codex_review') and window.worker is not None:
            state = 'coding'
        elif getattr(window, 'coding_worker', None) is not None:
            # The personal coding assistant runs its own worker, so the Omega
            # modes still show that work in progress.
            state = 'coding'
        elif window.worker_kind == 'video_export' and window.worker is not None:
            state = 'working'
        activity = ACTIVITY[state]
        self.activity_label.setText(activity)
        self.floating.handle.setText(f'JARVIS · {activity}')
        self.floating.assistant.setText('Review' if state == 'approval' else 'Assistant')
        for orb in (self.reactor, self.floating.orb, window.chat_reactor):
            orb.set_activity(state)
        for mic in (self.mic, self.floating.mic):
            mic.setText('Cancel mic' if window.voice_panel.listening else 'Talk')
            mic.setEnabled(not window.policy.stopped and not window.voice_panel.playback_busy)
        self.send.setEnabled(not window.policy.stopped and window.worker is None)
        self.ai_note.setText(window.brain_label.text() or 'Local interface ready')

    def audio_level(self, level):
        self.signal_meter.set_level(level)
        for widget in (self.reactor, self.floating.orb, self.window.chat_reactor):
            widget.set_level(level)

    def toggle_mic(self):
        if self.window.policy.stopped:
            return
        if self.window.voice_panel.listening:
            self.window.voice_panel.cancel_listening()
        else:
            if self.mode != 'Omega' and not self.window.voice_panel.consent.listening:
                self.switch('Omega')
            self.window.listen_to_user()

    def submit(self, source):
        text = source.text().strip()
        if not text or self.window.policy.stopped or self.window.worker is not None:
            return
        self.open_page('JARVIS Chat')
        if self.window.prompt.toPlainText().strip():
            self.window.statusBar().showMessage('Review the existing chat draft before replacing it.', 9000)
            self.window.prompt.setFocus()
            return
        source.clear()
        self.window.prompt.setPlainText(text)
        self.window.send()

    def on_notice(self, value):
        self.floating.notice.setText(value[:180])

    def on_stop(self):
        if self.feeds.replies:
            self.weather_value.setText('Refresh cancelled')
            self.news_value.setText('Refresh cancelled')
        self.feeds.abort()
        self.refresh_state()

    def shutdown(self):
        self.feeds.abort()
        self.floating.hide()
