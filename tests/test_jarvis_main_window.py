"""One friendly JARVIS Windows surface; hidden advanced tools remain usable."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from desktop.app import Window


def test_only_six_primary_sections_and_one_main_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        names = [win.nav.item(i).text() for i in range(win.nav.count())]
        assert names == [
            "JARVIS Chat", "PC Control", "Coding Assistant",
            "Voice / Hey Jarvis", "Phone Remote", "Settings & Safety"
        ]
        assert win.pages.count() == 12
        assert win.nav.currentRow() == 0
        assert win.pages.currentIndex() == 0
        assert win.orb._state == "idle"
        assert "CPU" in win.system_metrics_label.text()
        assert not win.bridge.listener.running
        assert not win.voice_panel.consent.granted
        win.open_section("Coding Assistant")
        assert win.pages.currentIndex() == win.page_indices["Coding Assistant"]
        win.open_section("AI Providers")
        assert win.pages.currentIndex() == win.page_indices["AI Providers"]
        win.open_section("JARVIS Chat")
        assert win.nav.currentRow() == 0
        assert win.pages.currentIndex() == 0
    finally:
        win.close()
        app.processEvents()


def test_hey_jarvis_only_drafts_a_chat_message(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        before = len(win.store.tasks())
        win.open_section("PC Control")
        win.voice_panel.allow.setChecked(True)
        win.voice_panel.on_wake_call("Hey Jarvis", "help me write Python")
        app.processEvents()
        assert win.pages.currentIndex() == win.page_indices["JARVIS Chat"]
        assert win.prompt.toPlainText() == "help me write Python"
        assert len(win.store.tasks()) == before
        assert not win.bridge.listener.running
        assert win.worker is None
        win.stop()
        assert win.voice_panel.consent.stopped
        assert not win.voice_panel.consent.granted
        win.prompt.clear()
        win.voice_panel.on_wake_call("Hey Jarvis", "open settings")
        assert win.prompt.toPlainText() == ""
        win.resume()
        assert not win.voice_panel.consent.granted
    finally:
        win.close()
        app.processEvents()


def test_continuous_wake_requires_permission_and_is_opt_in():
    app = QApplication.instance() or QApplication([])
    from desktop.voice_panel import VoicePanel
    panel = VoicePanel()
    assert not panel.continuous_button.isEnabled()
    assert panel.worker is None
    panel.allow.setChecked(True)
    assert panel.continuous_button.isEnabled()
    panel.stop_voice()
    assert not panel.continuous_button.isEnabled()
    panel.resume_voice()
    assert not panel.continuous_button.isEnabled()
    panel.close()
    app.processEvents()
