"""YouTube playback in the media area, with navigation limited to YouTube."""
import re
from urllib.parse import parse_qs, quote_plus, urlsplit

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


def youtube_request(text):
    """Return an official watch or results URL for an explicit media request."""
    text = text.strip()
    links = re.findall(r'https://[^\s<>]+', text)
    if links:
        try:
            link = urlsplit(links[0].rstrip(').,!?'))
        except ValueError:
            return ''
        host = link.hostname
        if host in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
            video = parse_qs(link.query).get('v', [''])[0] if link.path == '/watch' else ''
            if link.path.startswith('/shorts/'):
                video = link.path.split('/')[2]
        elif host == 'youtu.be':
            video = link.path.strip('/')
        else:
            return ''
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
            return 'https://www.youtube.com/watch?v=' + video
        return ''
    match = re.fullmatch(r'(?:/youtube|play on youtube|youtube(?:[- ]la)?)\s+(.+)',
                         text, flags=re.IGNORECASE)
    if not match:
        match = re.fullmatch(r'play\s+(.+?)\s+on youtube[.!]?', text, flags=re.IGNORECASE)
    if match:
        title = re.sub(r'\s+(?:play\s+pannu|play\s+பண்ணு|போடு)[.!]?$',
                       '', match.group(1), flags=re.IGNORECASE).strip()
        if title and len(title) <= 240:
            return 'https://www.youtube.com/results?search_query=' + quote_plus(title)
    return ''


class YouTubePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = QUrl()
        self.view = None
        self.layout_ = QVBoxLayout(self)
        self.status = QLabel('Ask JARVIS to play a YouTube video, or paste its link in Chat.')
        self.status.setWordWrap(True)
        self.layout_.addWidget(self.status)
        self.external = QPushButton('Open on YouTube')
        self.external.clicked.connect(lambda: QDesktopServices.openUrl(self.url))
        self.external.hide()
        self.layout_.addWidget(self.external)

    def open_url(self, url):
        self.url = QUrl(url)
        if self.view is None:
            try:
                from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
                from PySide6.QtWebEngineWidgets import QWebEngineView
            except ImportError:
                self.status.setText('The in-app player is unavailable on this installation.')
                self.external.show()
                return

            class YouTubePage(QWebEnginePage):
                def acceptNavigationRequest(self, url, _kind, main_frame):
                    return (not main_frame or url.toString() == 'about:blank'
                            or (url.scheme() == 'https' and url.host() in (
                                'youtube.com', 'www.youtube.com', 'm.youtube.com')))

            self.view = QWebEngineView(self)
            self.view.setAccessibleName('YouTube player')
            self.profile = QWebEngineProfile(self.view)
            self.profile.downloadRequested.connect(lambda download: download.cancel())
            self.page = YouTubePage(self.profile, self.view)
            self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
            self.view.setPage(self.page)
            self.view.loadFinished.connect(self.loaded)
            self.layout_.addWidget(self.view, 1)
        self.status.setText('Loading YouTube…')
        self.status.show()
        self.external.show()
        self.view.setUrl(self.url)

    def loaded(self, ok):
        self.status.setVisible(not ok)
        if not ok:
            self.status.setText('YouTube did not load here.')
        elif self.url.path() == '/watch' and self.view.url().path() == '/watch':
            requested = QUrl(self.url)
            QTimer.singleShot(1200, self, lambda: self.start_playback(requested))

    def start_playback(self, requested):
        if self.view.url() != requested:
            return
        self.page.runJavaScript("""
            const video = document.querySelector('video');
            if (video && video.paused) {
                const button = document.querySelector('.ytp-large-play-button');
                if (button && button.getClientRects().length) button.click();
                else video.play().catch(() => {});
            }
        """)

    def stop(self):
        if self.view is not None:
            self.view.setUrl(QUrl('about:blank'))
