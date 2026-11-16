from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton

from desktop.app import Window
from desktop.omega import DESTINATIONS
from security.policy import Action


def launch(path):
    app = QApplication.instance() or QApplication([])
    window = Window(path)
    window.enable_omega(smoke=True)
    window.showNormal()
    window.resize(1320, 820)
    app.processEvents()
    return app, window, window.omega


def test_modes_return_to_same_window_and_keep_saved_preferences(tmp_path):
    app, window, ui = launch(tmp_path)
    try:
        ui.set_theme('Apple Silver')
        ui.set_background('Horizon')
        ui.set_reduced(True)
        for mode in ('Island', 'Stealth'):
            ui.switch(mode)
            app.processEvents()
            assert window.isHidden() and ui.floating.isVisible()
            assert not ui.floating.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
            ui.floating.flip()
            assert ui.floating.command.isVisible()
        ui.set_pin(True)
        assert ui.floating.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        ui.floating.close()
        assert not window.isHidden() and ui.floating.isHidden()
        ui.switch('Island')
    finally:
        window.close()
        app.processEvents()
    restored = Window(tmp_path)
    try:
        restored.enable_omega()
        view = restored.omega
        assert view.mode == 'Island' and view.floating.isVisible()
        assert view.theme == 'Apple Silver' and view.home.background == 'Horizon'
        assert view.reduced and view.pin
        assert not view.floating.orb.timer.isActive()
    finally:
        restored.close()


def test_dock_links_keyboard_and_order(tmp_path):
    app, window, ui = launch(tmp_path)
    try:
        for destination in tuple(ui.dock.buttons):
            destination.click()
            section = DESTINATIONS[destination.name][0]
            assert window.pages.currentIndex() == window.page_indices[section]
            assert destination.property('active') is True
        ui.dock.buttons[0].setFocus()
        QTest.keyClick(ui.dock.buttons[0], Qt.Key.Key_Right)
        assert ui.dock.buttons[1].hasFocus()
        ui.order_items.setCurrentText('AI Chat')
        ui.move_dock(-1)
        assert ui.dock.buttons[0].name == 'AI Chat'
        assert window.store.get('omega:order')[0] == 'AI Chat'
        ui.set_auto_hide(True)
        assert ui.dock.isHidden()
        ui.reveal.click()
        assert ui.dock.isVisible()
        window.resize(720, 770)
        ui.open_page('Omega Home')
        app.processEvents()
        assert ui.home.compact
        assert ui.dock.buttons[0].toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    finally:
        window.close()


def test_live_activity_approval_and_emergency_stop(tmp_path, monkeypatch):
    _app, window, ui = launch(tmp_path)
    try:
        ui.set_voice('listening')
        ui.audio_level(50)
        assert ui.reactor.activity == 'listening' and ui.signal_meter.level == 50
        ui.set_voice('thinking')
        assert ui.signal_meter.level == 0
        assert ui.activity_label.text() == 'Thinking'
        old_worker, old_kind = window.worker, window.worker_kind
        window.worker, window.worker_kind = object(), 'codex_review'
        ui.refresh_state()
        assert ui.activity_label.text() == 'Coding'
        window.worker, window.worker_kind = old_worker, old_kind

        def inspect(*_args):
            assert ui.activity_label.text() == 'Approval required'
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, 'question', inspect)
        assert not window.confirm(Action('launch_app', 'Notepad'))
        assert ui.activity_label.text() == 'Thinking'
        window.stop()
        assert ui.activity_label.text() == 'Stopped'
        assert not ui.send.isEnabled()
        assert not ui.refresh_feed.isEnabled()
        window.resume()
        assert ui.send.isEnabled()
    finally:
        window.close()


def test_quick_command_goes_through_existing_chat_handler(tmp_path, monkeypatch):
    _app, window, ui = launch(tmp_path)
    dispatch = Mock()
    monkeypatch.setattr(window, 'send', dispatch)
    try:
        ui.switch('Stealth')
        ui.floating.flip()
        ui.floating.command.setText('/time')
        ui.floating.command.returnPressed.emit()
        dispatch.assert_called_once_with()
        assert window.prompt.toPlainText() == '/time'
        assert window.pages.currentIndex() == window.page_indices['JARVIS Chat']
        window.stop()
        ui.command.setText('queued')
        ui.command.returnPressed.emit()
        dispatch.assert_called_once_with()
    finally:
        window.close()


def test_feeds_report_partial_and_missing_data_explicitly(tmp_path, monkeypatch):
    _app, window, ui = launch(tmp_path)
    try:
        def fixture(url, _limit, callback):
            if 'open-meteo' in url:
                callback('{"current":{"temperature_2m":12,"time":"2026-11-16T12:00"},'
                         '"current_units":{"temperature_2m":"°C"}}'.encode())
            elif 'franceinfo' in url:
                callback(b'<rss><channel><item><title>Fixture headline</title></item></channel></rss>')
            else:
                callback(b'')
        monkeypatch.setattr(ui.feeds, 'request', fixture)
        ui.feeds.refresh()
        assert ui.weather_value.text() == '12 °C'
        assert ui.news_value.text() == 'franceinfo  ·  Fixture headline'
        assert ui.news_detail.text() == 'Some feeds unavailable'
        monkeypatch.setattr(ui.feeds, 'request', lambda _url, _limit, complete: complete(b''))
        ui.feeds.refresh()
        assert ui.weather_value.text() == 'Unavailable'
        assert ui.news_value.text() == 'Headlines unavailable'
        assert '0 paired' in ui.devices.text()
        assert 'stopped' in ui.devices.text()
    finally:
        window.close()
