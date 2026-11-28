"""On-demand tabbed browser, isolated from app keys."""
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget, QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel


def web_address(text):
    text = text.strip()
    if not text or len(text) > 8192 or any(char.isspace() for char in text):
        raise ValueError('Enter a website address, for example https://example.com.')
    url = QUrl(text if '://' in text else 'https://' + text)
    if (not url.isValid() or url.scheme() not in ('https', 'http') or not url.host()
            or url.userName() or url.password()):
        raise ValueError('Use an HTTP or HTTPS website address without embedded credentials.')
    return url


class WebPanel(QWidget):
    closed = Signal()
    title_changed = Signal(str)
    new_tab_requested = Signal(str)

    def __init__(self, parent=None, profile_owner=None):
        super().__init__(parent)
        self.profile_owner = profile_owner
        self.view = None
        self.setAccessibleName('Built-in browser')
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.back = QPushButton('←')
        self.forward = QPushButton('→')
        self.reload = QPushButton('↻')
        for button, name in ((self.back, 'Back'), (self.forward, 'Forward'),
                             (self.reload, 'Reload')):
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setFixedWidth(34)
            button.setEnabled(False)
            controls.addWidget(button)
        self.address = QLineEdit()
        self.address.setAccessibleName('Website address')
        self.address.setPlaceholderText('https://example.com')
        self.address.returnPressed.connect(lambda: self.open_url(self.address.text()))
        controls.addWidget(self.address, 1)
        self.go = QPushButton('Go')
        self.go.clicked.connect(lambda: self.open_url(self.address.text()))
        controls.addWidget(self.go)
        self.layout_.addLayout(controls)
        self.status = QLabel('Enter a website address to browse inside JARVIS.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.layout_.addWidget(self.status)
        self.home = QPushButton('Back to hologram')
        self.home.clicked.connect(self.leave)
        self.layout_.addWidget(self.home)

    def ensure_view(self):
        if self.view is not None:
            return True
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            self.status.setText('The built-in browser is unavailable on this installation.')
            return False

        class WebPage(QWebEnginePage):
            def acceptNavigationRequest(page, url, kind, main_frame):
                return url.scheme() in ('http', 'https') or (
                    url.toString() == 'about:blank')

            def chooseFiles(page, mode, old_files, accepted_mime_types):
                # Local files remain under the existing JARVIS attachment workflow.
                return []

        self.view = QWebEngineView(self)
        self.view.setAccessibleName('Website content')
        if self.profile_owner is not None:
            if self.profile_owner.profile is None:
                self.profile_owner.profile = QWebEngineProfile(self.profile_owner)
                self.profile_owner.profile.downloadRequested.connect(lambda item: item.cancel())
            self.profile = self.profile_owner.profile
        else:
            self.profile = QWebEngineProfile(self.view)
            self.profile.downloadRequested.connect(lambda item: item.cancel())
        self.page = WebPage(self.profile, self.view)
        self.page.permissionRequested.connect(lambda request: request.deny())
        self.page.fileSystemAccessRequested.connect(lambda request: request.reject())
        self.page.certificateError.connect(lambda error: error.rejectCertificate())
        self.page.newWindowRequested.connect(self.request_new_tab)
        settings = self.page.settings()
        for attribute in (QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                          QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                          QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                          QWebEngineSettings.WebAttribute.FullScreenSupportEnabled):
            settings.setAttribute(attribute, False)
        self.view.setPage(self.page)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.layout_.insertWidget(2, self.view, 1)
        self.back.clicked.connect(self.view.back)
        self.forward.clicked.connect(self.view.forward)
        self.reload.clicked.connect(self.view.reload)
        self.view.urlChanged.connect(self.address_changed)
        self.view.titleChanged.connect(self.title_changed)
        self.view.loadStarted.connect(lambda: self.status.setText('Loading…'))
        self.view.loadFinished.connect(self.loaded)
        self.view.renderProcessTerminated.connect(
            lambda *_: self.status.setText('The page stopped responding. Reload to try again.'))
        return True

    def request_new_tab(self, request):
        if request.isUserInitiated():
            try:
                url = web_address(request.requestedUrl().toString())
            except ValueError:
                return
            self.new_tab_requested.emit(url.toString())

    def open_url(self, text=''):
        if not text:
            self.address.setFocus()
            return
        try:
            url = web_address(text)
        except ValueError as error:
            self.status.setText(str(error))
            return
        if self.ensure_view():
            self.address.setText(url.toString())
            self.view.setUrl(url)

    def address_changed(self, url):
        self.address.setText(url.toString())
        self.back.setEnabled(self.view.history().canGoBack())
        self.forward.setEnabled(self.view.history().canGoForward())
        self.reload.setEnabled(True)

    def loaded(self, ok):
        self.address_changed(self.view.url())
        self.status.setText('Private session · Website permissions and downloads disabled.' if ok
                            else 'Could not load this page. Check the address or connection, then Reload.')

    def stop(self):
        if self.view is not None:
            self.view.stop()
            self.view.setUrl(QUrl('about:blank'))

    def leave(self):
        self.stop()
        self.closed.emit()


class BrowserWindow(QDialog):
    """One resizable browser panel; each tab owns its navigation and renderer."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle('JARVIS Browser')
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.resize(1080, 740)
        self.setMinimumSize(500, 360)
        self.profile = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName('Browser tabs')
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.tabs)
        self.add_button = QPushButton('+')
        self.add_button.setFixedWidth(36)
        self.add_button.setAccessibleName('New tab')
        self.add_button.setToolTip('New tab (Ctrl+T)')
        self.add_button.clicked.connect(lambda: self.add_tab())
        self.tabs.setCornerWidget(self.add_button)
        for key, action in (('Ctrl+T', self.add_tab),
                            ('Ctrl+W', lambda: self.close_tab(self.tabs.currentIndex())),
                            ('Ctrl+L', self.focus_address)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

    def focus_address(self):
        panel = self.tabs.currentWidget()
        if panel is not None:
            panel.address.setFocus()
            panel.address.selectAll()

    def add_tab(self, url=''):
        panel = WebPanel(self, profile_owner=self)
        panel.home.hide()
        index = self.tabs.addTab(panel, 'New tab')
        self.tabs.setCurrentIndex(index)
        panel.title_changed.connect(lambda title: self.update_title(panel, title))
        panel.new_tab_requested.connect(self.add_tab)
        panel.open_url(url)
        panel.address.setFocus()
        return panel

    def update_title(self, panel, title):
        index = self.tabs.indexOf(panel)
        if index >= 0:
            self.tabs.setTabText(index, (title or 'New tab')[:32])
            self.tabs.setTabToolTip(index, title or 'New tab')

    def close_tab(self, index):
        panel = self.tabs.widget(index)
        if panel is None:
            return
        panel.stop()
        self.tabs.removeTab(index)
        panel.deleteLater()
        if self.tabs.count() == 0:
            self.add_tab()

    def open_url(self, url=''):
        if url or self.tabs.count() == 0:
            self.add_tab(url)
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self.focus_address()

    def stop(self):
        for index in range(self.tabs.count()):
            self.tabs.widget(index).stop()

    def clear_tabs(self):
        self.stop()
        while self.tabs.count():
            panel = self.tabs.widget(0)
            self.tabs.removeTab(0)
            panel.deleteLater()

    def closeEvent(self, event):
        self.clear_tabs()
        event.accept()

    def reject(self):
        self.clear_tabs()
        super().reject()
