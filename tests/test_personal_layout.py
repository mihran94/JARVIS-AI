"""Prevent the vertically compressed Chat and Phone Remote layouts."""
from PySide6.QtWidgets import QApplication, QTabWidget

from desktop.app import STYLE, Window


def test_chat_and_phone_stay_readable_at_narrow_desktop_size(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous_style = app.styleSheet()
    app.setStyleSheet(STYLE)
    window = Window(tmp_path)
    try:
        window.resize(680, 510)
        window.show()
        app.processEvents()
        chat = window.pages.currentWidget()
        assert chat.horizontalScrollBar().maximum() == 0
        assert window.transcript.height() >= 150
        assert window.send_button.isVisible()
        assert not window.backup_provider.isVisible()
        # Advanced chat controls are deliberately accessible from Settings,
        # not inside an extra set of chat options on the narrow main screen.
        window.open_section("Settings & Safety")
        app.processEvents()
        assert window.backup_provider.isVisible()
        window.open_section("JARVIS Chat")
        app.processEvents()
        assert not window.backup_provider.isVisible()

        window.open_section("Phone Remote")
        tabs = window.bridge.findChild(QTabWidget)
        assert [tabs.tabText(index) for index in range(tabs.count())] == [
            "Set up iPhone", "Set up Android", "Advanced connection", "Job approvals",
        ]
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            app.processEvents()
            assert tabs.currentWidget().horizontalScrollBar().maximum() == 0
        assert window.bridge.host.height() >= 30
        assert not window.bridge.listener.running
    finally:
        window.close()
        # The window is destroyed, not just closed: a closed window keeps its
        # widgets and its OpenGL resources alive, and the next test then
        # renders far more slowly than it should.
        window.deleteLater()
        app.setStyleSheet(previous_style)
        app.processEvents()
