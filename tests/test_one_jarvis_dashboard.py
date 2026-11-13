"""The unified JARVIS desktop keeps one command center and one safety policy."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.app import STYLE, Window
from desktop.blue_orb import BlueOrb
from desktop.blue_theme import FUTURISTIC_BLUE
from desktop.network_metrics import NetworkSampler, format_network
from desktop.voice_commands import parse_voice_command


def test_one_dashboard_has_orb_read_only_metrics_and_existing_pages(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = Window(tmp_path)
    try:
        assert STYLE == FUTURISTIC_BLUE
        assert isinstance(window.orb, BlueOrb)
        assert window.pages.count() == 12
        assert 'CPU' in window.system_metrics_label.text()
        assert window.nav.item(5).text() == 'Mobile Bridge'
        assert window.nav.item(6).text() == 'Voice'
        assert window.orb._state == 'idle'
        window.set_ai_visual_state('thinking')
        assert window.orb._state == 'thinking'
        window.stop()
        assert window.orb._state == 'stopped'
        window.resume()
        assert window.orb._state == 'idle'
        # Painting and passive metrics do not start the bridge listener.
        assert not window.bridge.listener.running
    finally:
        window.close()
        app.processEvents()


def test_missing_optional_network_sampler_does_not_break_dashboard():
    sampler = NetworkSampler(counter_reader=lambda: None)
    assert sampler.sample() is None
    assert 'unavailable' in format_network(None)


def test_imported_tamil_intent_remains_allowlisted():
    assert parse_voice_command('நோட்பேட் திற') == 'Notepad'
    assert parse_voice_command('open notepad and delete everything') is None
