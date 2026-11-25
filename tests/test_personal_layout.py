"""Prevent the vertically compressed Chat and Phone Remote layouts."""
from PySide6.QtWidgets import QApplication, QTabWidget

from desktop.app import Window


def test_mission_button_stays_clickable_in_the_hud_composer(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.resize(1180, 820)
        window.show()
        composer = window.prime_chat.composer
        button = window.mission_mode

        for width in (1180, 680, 1180):
            window.resize(width, 820)
            window.open_section('Settings & Safety')
            app.processEvents()
            assert not button.isVisible()
            window.open_section('JARVIS Chat')
            app.processEvents()

            assert button.isVisible()
            assert composer.controls.indexOf(button) >= 0
            assert composer.rect().contains(button.geometry())
            assert window.childAt(button.mapTo(window, button.rect().center())) is button
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_chat_and_phone_stay_readable_at_narrow_desktop_size(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.resize(680, 510)
        window.show()
        app.processEvents()
        chat = window.prime_chat.conversation
        assert chat.horizontalScrollBar().maximum() == 0
        assert window.prime_chat.states.height() >= 150
        assert window.send_button.isVisible()
        assert not window.backup_provider.isVisible()
        # Advanced chat controls are deliberately accessible from Settings,
        # not inside an extra set of chat options on the narrow main screen.
        window.open_section("Settings & Safety")
        app.processEvents()
        assert not window.backup_provider.isVisible()
        window.settings_mode_button.click()
        app.processEvents()
        assert window.settings_category.currentText() == "Chat options, audio tests and connections"
        assert window.backup_provider.isVisible()
        assert window.pages.currentWidget().horizontalScrollBar().maximum() == 0
        window.open_section("PC Control")
        app.processEvents()
        assert window.prime_chat.task_area.currentWidget().horizontalScrollBar().maximum() == 0
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
        app.processEvents()
