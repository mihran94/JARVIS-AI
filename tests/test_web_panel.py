"""Exercise the actual renderer in an isolated process, without public websites."""
import os
import subprocess
import sys

import pytest

from desktop.web_panel import web_address


@pytest.mark.parametrize('value', ['javascript:alert(1)', 'file:///tmp/a', 'data:text/html,test',
                                   'https://user:secret@example.com', '', 'https://a b.com'])
def test_browser_rejects_non_web_or_credential_addresses(value):
    with pytest.raises(ValueError):
        web_address(value)


def test_browser_defaults_to_https():
    assert web_address('example.com/path?q=test').toString() == 'https://example.com/path?q=test'


def test_browser_uses_existing_display_and_keeps_chat(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QPushButton
    from desktop.app import Window
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        chat = window.prime_chat
        panel = chat.web_panel
        opened = []
        monkeypatch.setattr(panel, 'open_url', opened.append)
        window.prompt.setPlainText('/web https://example.com')
        window.send()
        assert opened == ['https://example.com']
        assert chat.displays.currentWidget() is panel
        assert chat.conversation.parent() is not None
        assert window.prompt.toPlainText() == ''
        panel.home.click()
        assert chat.displays.currentWidget() is chat.assistant
        browser = next(button for button in window.prime_shell.drawer.findChildren(QPushButton)
                       if button.text() == 'Browser')
        browser.click()
        assert chat.displays.currentWidget() is panel
        assert opened == ['https://example.com', '']
        assert not window.prime_shell.drawer.isVisible()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_real_browser_navigation_and_return_to_hologram():
    code = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading, time
from PySide6.QtWidgets import QApplication
from desktop.web_panel import WebPanel
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(('<title>JARVIS browser test</title><h1>'+self.path+'</h1>').encode())
    def log_message(self, *_): pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QApplication([])
panel = WebPanel()
assert panel.view is None
panel.open_url('http://127.0.0.1:%s/one' % server.server_port)
def until(predicate):
    end = time.monotonic()+12
    while time.monotonic()<end:
        app.processEvents()
        if predicate(): return
        time.sleep(.01)
    raise AssertionError(panel.status.text())
until(lambda: panel.view.title() == 'JARVIS browser test' and 'Private session' in panel.status.text())
assert panel.profile.isOffTheRecord()
assert not panel.page.acceptNavigationRequest(__import__('PySide6.QtCore', fromlist=['QUrl']).QUrl('file:///tmp/a'), None, True)
assert panel.page.chooseFiles(None, [], []) == []
panel.open_url('http://127.0.0.1:%s/two' % server.server_port)
until(lambda: panel.view.url().path() == '/two' and panel.back.isEnabled())
panel.back.click()
until(lambda: panel.view.url().path() == '/one' and panel.forward.isEnabled())
panel.forward.click()
until(lambda: panel.view.url().path() == '/two')
closed=[]
panel.closed.connect(lambda: closed.append(True))
panel.home.click()
until(lambda: panel.view.url().toString() == 'about:blank')
assert closed == [True]
panel.deleteLater()
app.sendPostedEvents(None, 52)
app.processEvents()
server.shutdown()
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,
                            text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
