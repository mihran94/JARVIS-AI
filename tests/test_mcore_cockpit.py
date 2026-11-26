"""Native M-CORE layout and safety contracts; all fixtures are isolated."""
import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

from desktop.app import Window


@pytest.fixture
def opened_cockpit(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.resize(1227, 912)
        window.show()
        app.processEvents()
        assert window.pages.currentWidget() is window.prime_chat
        assert 'M-CORE' not in {window.nav.item(i).text() for i in range(window.nav.count())}
        window.prime_shell.cockpit_button.click()
        app.processEvents()
        yield window, window.mcore_cockpit, app
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_cockpit_uses_reference_columns_and_keeps_settings_reachable(opened_cockpit):
    window, cockpit, app = opened_cockpit
    assert window.pages.currentWidget() is cockpit
    assert not window.prime_shell.top_bar.isVisible()
    assert not cockpit._compact
    panels = (
        cockpit.systems, cockpit.status, cockpit.tasks, cockpit.voice,
        cockpit.news, cockpit.comms, cockpit.command,
    )
    assert [panel.accessibleName() for panel in panels] == [
        'Systems panel', 'Status panel', 'Tasks panel', 'Voice Interface panel',
        'News panel', 'Communications panel', 'Command panel',
    ]
    assert all(panel.isVisible() for panel in panels)
    assert cockpit.systems.x() < cockpit.voice.x() < cockpit.comms.x()
    assert cockpit.systems.y() < cockpit.status.y() < cockpit.tasks.y()
    assert cockpit.voice.y() < cockpit.news.y()
    assert cockpit.comms.y() < cockpit.command.y()
    assert str(datetime.now().year) in cockpit.date_label.text()
    cockpit.update_metrics({})
    assert cockpit.metrics['gpu_usage_percent'].readout == 'N/A'
    cockpit.update_metrics(window.cockpit_usage)
    assert 'No briefing yet' in cockpit.news_output.toPlainText()
    assert 'Mic: off' == cockpit.mic_button.text()

    screenshot = os.environ.get('JARVIS_MCORE_TEST_SCREENSHOT')
    if screenshot:
        # Optional hosted desktop artifact: only isolated fixture data.
        window.show_local_system_reply('Local smoke check', 'JARVIS is ready for a command.')
        app.processEvents()
        destination = Path(screenshot).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert cockpit.grab().save(str(destination), 'PNG')

    cockpit.settings_button.click()
    app.processEvents()
    assert window.prime_shell.settings_dialog.isVisible()
    assert window.pages.currentWidget() is cockpit
    window.prime_shell.settings_dialog.close()
    cockpit.prime_button.click()
    app.processEvents()
    assert window.pages.currentWidget() is window.prime_chat
    assert window.prime_shell.top_bar.isVisible()


def test_cockpit_narrow_layout_is_vertical_not_clipped(opened_cockpit):
    window, cockpit, app = opened_cockpit
    window.resize(740, 720)
    app.processEvents()
    assert cockpit._compact
    assert cockpit.voice.x() == cockpit.command.x() == cockpit.comms.x()
    assert cockpit.voice.y() < cockpit.command.y() < cockpit.comms.y()
    assert cockpit.prompt.width() > 120
    assert cockpit.verticalScrollBar().maximum() > 0
    assert cockpit.horizontalScrollBar().maximum() == 0


def test_cockpit_command_reuses_local_reply_without_provider(opened_cockpit, monkeypatch):
    window, cockpit, _ = opened_cockpit
    monkeypatch.setattr(window, 'send_chat_reply', lambda *_a, **_k: pytest.fail('No provider call'))
    cockpit.prompt.setText('What time is it')
    cockpit.send.click()
    assert not cockpit.prompt.text()
    assert not window.prompt.toPlainText()
    assert 'What time is it' in cockpit.comms_output.toPlainText()
    assert 'JARVIS M' in cockpit.comms_output.toPlainText()
    assert not window.voice_panel.consent.listening


def test_cockpit_never_bypasses_chat_approval(opened_cockpit, monkeypatch):
    window, cockpit, _ = opened_cockpit
    monkeypatch.setattr('desktop.app.launch_app', lambda *_: pytest.fail('Ignored approval'))
    cockpit.prompt.setText('Open Calculator and calculate: 17 * 23')
    cockpit.send.click()
    assert window.chat_launch is not None
    assert window.prime_shell.state_chip.text() == 'APPROVAL REQUIRED'
    if window.pages.currentWidget() is cockpit:
        assert cockpit.review_button.isVisible()
        cockpit.review_button.click()
    assert window.pages.currentWidget() is window.prime_chat


def test_cockpit_drop_stages_selected_files_and_forgets_sharing(opened_cockpit, tmp_path):
    window, cockpit, _ = opened_cockpit
    first, second = tmp_path / 'first.txt', tmp_path / 'second.md'
    first.write_text('one', encoding='utf-8')
    second.write_text('two', encoding='utf-8')
    folder = tmp_path / 'example'
    folder.mkdir()
    (folder / 'notes.txt').write_text('local notes', encoding='utf-8')
    local = QMimeData()
    local.setUrls([QUrl.fromLocalFile(str(first))])
    assert [Path(name) for name in cockpit.drop.paths(local)] == [first]
    assert cockpit.stage_dropped(cockpit.drop.paths(local))
    window.files_share_once.setChecked(True)
    assert cockpit.stage_dropped([str(second)])
    assert len(window.attachments) == 2
    assert not window.files_share_once.isChecked()
    assert '2 staged locally' in cockpit.attachment_label.text()
    assert cockpit.stage_dropped([str(folder)])
    assert '3 staged locally' in cockpit.attachment_label.text()
    remote = QMimeData()
    remote.setUrls([QUrl('file://server/private/file.txt')])
    assert not cockpit.drop.paths(remote)
    remote.setUrls([QUrl('https://example.com/file.txt')])
    assert not cockpit.drop.paths(remote)
    assert window.worker is None


def test_cockpit_reports_capture_not_just_provider_selection(opened_cockpit):
    from types import SimpleNamespace

    window, cockpit, _ = opened_cockpit
    window.live_voice = SimpleNamespace(active=True, state='connecting', input=None)
    try:
        window.refresh_prime_state()
        assert cockpit.mic_button.text() == 'Mic: connecting'
        assert not cockpit.signal.active
        window.live_voice.state = 'listening'
        window.refresh_prime_state()
        assert not cockpit.signal.active
        assert cockpit.mic_button.text() == 'Mic: unavailable'
        window.live_voice.input = object()
        window.refresh_prime_state()
        assert cockpit.signal.active
        assert cockpit.mic_button.text() == 'MIC ACTIVE'
        window.live_voice.state = 'speaking'
        window.refresh_prime_state()
        assert not cockpit.signal.active
        assert cockpit.mic_button.text() == 'Mic: playback paused'
    finally:
        window.live_voice = None


def test_cockpit_return_preserves_original_prime_displays(opened_cockpit, monkeypatch):
    window, cockpit, app = opened_cockpit
    chat = window.prime_chat
    launch = lambda *_a, **_k: pytest.fail('No audio or camera device may start')
    monkeypatch.setattr(window, 'toggle_live_voice', launch)
    monkeypatch.setattr(window.camera_panel, 'start', launch, raising=False)

    # Exercise widget selection only. Never toggle camera capture or fetch Media.
    chat.show_camera_preview(True)
    assert chat.displays.currentWidget() is chat.camera_preview
    cockpit.prime_button.click()
    app.processEvents()
    assert window.pages.currentWidget() is chat
    assert chat.displays.currentWidget() is window.camera_panel.preview
    terminal = chat.terminal
    chat.show_display('media')
    window.prime_shell.cockpit_button.click()
    cockpit.prime_button.click()
    app.processEvents()
    assert chat.displays.currentWidget() is chat.youtube
    assert chat.terminal is terminal


def test_cockpit_offers_existing_news_without_auto_fetch(opened_cockpit, monkeypatch):
    window, cockpit, app = opened_cockpit
    monkeypatch.setattr(window, 'start_news_briefing', lambda *_a: pytest.fail('No news fetch'))
    # Basic navigation is offline; only a user pressing Fetch in the real News panel requests it.
    window.open_news_briefing()
    app.processEvents()
    assert window.prime_shell.drawer_content.currentWidget() is window.news_panel
    assert window.pages.currentWidget() is cockpit
    window.news_panel.output.setPlainText('Offline fixture: briefing result.')
    assert cockpit.news_output.toPlainText() == 'Offline fixture: briefing result.'
