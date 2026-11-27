"""On-demand web browsing inside the assistant display, isolated from app keys."""
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel


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

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.profile = QWebEngineProfile(self.view)
        self.profile.downloadRequested.connect(lambda item: item.cancel())
        self.page = WebPage(self.profile, self.view)
        self.page.permissionRequested.connect(lambda request: request.deny())
        self.page.fileSystemAccessRequested.connect(lambda request: request.reject())
        self.page.certificateError.connect(lambda error: error.rejectCertificate())
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
        self.view.loadStarted.connect(lambda: self.status.setText('Loading…'))
        self.view.loadFinished.connect(self.loaded)
        self.view.renderProcessTerminated.connect(
            lambda *_: self.status.setText('The page stopped responding. Reload to try again.'))
        return True

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
