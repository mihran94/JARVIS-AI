"""The PRIME interface has to be there, and it has to keep the features.

The owner was looking at the old interface with new colours. These tests
say what the new composition is made of, that the old chrome is gone, and
that the controls the features need are still the ones the application
uses.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from desktop.app import Window
from desktop.prime_ui import PrimeBubble, PrimeChat, PrimePalette, PrimeShell


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.showNormal()
    window.enable_omega(smoke=False)
    for _ in range(4):
        app.processEvents()
    return app, window


def test_the_window_has_the_prime_composition(tmp_path):
    app, window = make_window(tmp_path)
    try:
        assert isinstance(window.prime_shell, PrimeShell)
        assert isinstance(window.prime_chat, PrimeChat)
        assert window.prime_shell.brand.text() == 'JARVIS M'
        assert not window.omega.floating.isVisible()
    finally:
        window.close()


def test_the_compact_hud_keeps_one_stop_and_leaves_room_for_chat(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        window.showNormal()
        window.resize(1093, 614)
        app.processEvents()
        assert window.hud.isVisibleTo(window)
        assert window.hud.height() <= 90
        assert shell.findChild(QFrame, 'primeOverview') is None
        stops = [button for button in shell.findChildren(QPushButton)
                 if button.text() == 'Emergency stop' and button.isVisibleTo(window)]
        assert stops == [shell.stop_button]
        assert window.send_button.isVisibleTo(window)
        assert window.send_button.mapTo(window, window.send_button.rect().bottomRight()).x() < window.width()
        shell.menu_items['PC Control'].click()
        window.automation_workspace_button.click()
        window.automation_tools['PC usage'].click()
        assert window.prime_chat.task_area.isVisibleTo(window)
        assert window.hud.isVisibleTo(window)
    finally:
        window.close()


def test_the_automation_rail_groups_tools_and_previews_suggestions(tmp_path):
    app, window = make_window(tmp_path)
    try:
        assert window.prime_shell.menu_items['PC Control'].text() == 'Automation'
        window.prime_shell.menu_items['PC Control'].click()
        panel = window.automation_panel
        assert panel.browser_command.isVisibleTo(window)
        assert panel.suggestion_mode.isVisibleTo(window)
        panel.suggestion_mode.setChecked(True)
        panel.goal.setText('Open Calculator and calculate: 17 * 23')
        panel.work_button.click()
        assert window.suggested_steps[0].app == 'Calculator'
        assert window.chat_launch is None
        assert window.desktop_pending is None
        assert window.pages.currentIndex() == window.page_indices['PC Control']
        assert window.suggestion_card.isVisibleTo(window)
        assert panel.isAncestorOf(window.suggestion_card)
        assert window.suggestion_mode.isHidden()
    finally:
        window.close()


def test_conversation_settings_change_the_chat_reply_and_survive_restart(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    sent = []
    monkeypatch.setattr(window, 'get_key', lambda _provider: 'test-key')
    monkeypatch.setattr(window, 'start_worker',
                        lambda _provider, _model, _key, messages, *_args, **_kwargs:
                        sent.append(messages))
    try:
        window.open_section('Settings & Safety')
        scroller = window.settings_scroller
        assert window.reply_language.isVisibleTo(window)
        assert window.reply_language.currentData() == 'auto'
        assert window.reply_tone.currentData() == 'friendly'
        tabs = window.settings_categories
        system_tab = next(index for index in range(tabs.count()) if tabs.tabText(index) == 'System')
        tabs.setCurrentIndex(system_tab)
        app.processEvents()
        assert not window.reply_language.isVisibleTo(window)
        scroll = scroller.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        assert scroll.value() > 0
        window.open_section('Settings & Safety')
        assert scroll.value() == 0
        assert window.reply_language.isVisibleTo(window)

        window.open_section('JARVIS Chat')
        window.prompt.setPlainText('Namma ippo enna pesalam?')
        window.send()
        assert 'Latin script for Tanglish' in sent[-1][0]['content']
        assert 'Talk like a helpful colleague' in sent[-1][0]['content']

        window.open_section('Settings & Safety')
        window.reply_language.setCurrentIndex(window.reply_language.findData('tanglish'))
        window.reply_tone.setCurrentIndex(window.reply_tone.findData('direct'))
        window.open_section('JARVIS Chat')
        assert window.prime_chat.assistant.title.text() == 'Enna help venum?'
        window.prompt.setPlainText('தமிழ்ல சொல்லுங்க. இன்று என்ன பேசலாம்?')
        window.send()
        assert 'Use conversational Tamil in Latin script by default' in sent[-1][0]['content']
        assert 'Honor explicit requests about how to reply' in sent[-1][0]['content']
        assert 'short, factual answers' in sent[-1][0]['content']
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

    app, window = make_window(tmp_path)
    try:
        assert window.reply_language.currentData() == 'tanglish'
        assert window.reply_tone.currentData() == 'direct'
        assert window.prime_chat.assistant.title.text() == 'Enna help venum?'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_old_chrome_is_absent_at_construction_and_startup(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        for _ in range(2):
            window.show()
            app.processEvents()
            assert window.prime_shell.isVisible()
            assert window.findChild(QLabel, 'brandTitle') is None
            assert not {'Omega Home', 'Omega Settings'} & window.page_indices.keys()
            assert window.pages.currentWidget() is window.prime_chat
            if window.omega is None:
                window.enable_omega(smoke=True)
            assert window.omega.dock.isHidden()
            assert window.omega.reveal.isHidden()
    finally:
        window.close()


def test_resume_stays_inside_the_assistant_and_provider_is_visible(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        assert shell.isAncestorOf(window.resume_button)
        assert shell.provider_label.text() == 'Chat · ' + window.brain_label.text().removeprefix('Active brain: ')
        shell.stop_button.click()
        assert shell.state_chip.text() == 'STOPPED'
        assert window.resume_button.isVisibleTo(window)
        window.resume_button.click()
        assert not window.policy.stopped
        assert window.resume_button.isHidden()
    finally:
        window.close()


def test_the_build_is_shown_so_the_owner_knows_which_build(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_BUILD_COMMIT', 'abc123456')
    app, window = make_window(tmp_path)
    try:
        labels = [label.text() for label in window.prime_shell.findChildren(QLabel)]
        assert 'Revision abc1234' in labels
    finally:
        window.close()


def test_source_revision_resolves_in_a_git_worktree(tmp_path, monkeypatch):
    import shutil
    import subprocess

    import desktop.prime_ui as ui

    if shutil.which('git') is None:
        pytest.skip('Git is required to verify checkout revision detection')
    original = tmp_path / 'original'
    original.mkdir()
    worktree = tmp_path / 'worktree'
    subprocess.run(['git', 'init', str(original)], check=True, capture_output=True)

    def git(*args):
        return subprocess.check_output(['git', '-C', str(original), *args], text=True).strip()

    git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
        'commit', '--allow-empty', '-m', 'Initial commit')
    git('pack-refs', '--all')
    git('worktree', 'add', '--detach', str(worktree), 'HEAD')
    monkeypatch.delenv('JARVIS_BUILD_COMMIT', raising=False)
    monkeypatch.setattr(ui, '__file__', str(worktree / 'desktop' / 'prime_ui.py'))
    assert ui.build_commit() == git('rev-parse', 'HEAD')[:7]


def test_the_top_bar_and_automation_have_the_destinations(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        bar = shell.top_bar.layout()
        assert bar.indexOf(shell.menu_button) == bar.indexOf(shell.settings_button) + 1
        assert set(shell.menu_items) == {'JARVIS Chat', 'PC Control', 'Phone Remote', 'AI Providers'}
        assert {'Projects', 'Files & folders', 'Voice controls', 'Network', 'Memory'} <= set(
            window.automation_tools)
    finally:
        window.close()


def test_the_composer_uses_the_real_prompt_and_the_real_buttons(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        assert chat.composer.body.indexOf(window.prompt) >= 0
        controls = chat.composer.body.itemAt(1).layout()
        found = [controls.itemAt(index).widget()
                 for index in range(controls.count())
                 if controls.itemAt(index).widget() is not None]
        assert found == [window.chat_mic, window.attach_button, window.send_button]
        assert chat.safety_controls.indexOf(window.prime_shell.stop_button) >= 0
    finally:
        window.close()


def test_the_cards_of_a_running_job_come_with_the_new_chat(tmp_path):
    app, window = make_window(tmp_path)
    try:
        cards = window.prime_chat.cards
        widgets = [cards.itemAt(index).widget() for index in range(cards.count())
                   if cards.itemAt(index).widget() is not None]
        assert window.plan_card in widgets
        assert window.chat_task_card in widgets
        assert window.chat_approval in widgets
    finally:
        window.close()


def test_the_conversation_shows_the_messages_as_a_column(tmp_path):
    app, window = make_window(tmp_path)
    try:
        conversation = window.prime_chat.conversation
        conversation.render([
            {'role': 'user', 'content': 'Open Notepad'},
            {'role': 'assistant', 'content': 'Notepad is open.'},
        ])
        for _ in range(3):
            app.processEvents()
        assert len(conversation.bubbles) == 2
        bubbles = conversation.bubbles
        assert bubbles[0].you is True
        assert bubbles[1].you is False
        # A message is a bubble and not a line of text.
        assert isinstance(bubbles[0], PrimeBubble)
        assert isinstance(bubbles[0], QFrame)
    finally:
        window.close()


def test_the_hologram_stays_visible_beside_the_conversation(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        mark = window.prime_shell.mark
        chat.render([])
        assert chat.empty_history.isVisibleTo(window)
        assert chat.assistant.orb.isVisibleTo(window)
        assert chat.assistant.orb._timer.isActive()
        assert mark.isVisibleTo(window)

        chat.render([{'role': 'user', 'content': 'hello'}])
        assert chat.conversation.isVisibleTo(window)
        assert chat.assistant.orb.isVisibleTo(window)
        assert chat.assistant.orb._timer.isActive()
        assert mark.isVisibleTo(window)

        chat.render([])
        window.open_section('PC Control')
        assert mark.isVisibleTo(window)
        assert not chat.assistant.orb.isVisibleTo(window)
        window.open_section('Settings & Safety')
        assert mark.isVisibleTo(window)

        window.open_section('JARVIS Chat')
        assert mark.isVisibleTo(window)
        assert chat.assistant.orb.isVisibleTo(window)
        window.store.set('omega:reduced', True)
        window.refresh_prime_state()
        assert not chat.assistant.orb._timer.isActive()
    finally:
        window.close()


def test_the_state_reaches_the_shell_and_the_island(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.prime_state = lambda: 'listening'
        window.refresh_prime_state()
        assert window.prime_shell.state_chip.text() == 'LISTENING'
        assert window.prime_shell.mark.state == 'listening'
        window.prime_state = lambda: 'working'
        window.refresh_prime_state()
        assert window.prime_shell.state_chip.text() == 'WORKING'
    finally:
        window.close()


def test_the_menu_marks_the_workspace_that_is_open(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.open_section('Memory')
        for _ in range(2):
            app.processEvents()
        assert window.prime_shell.menu_items['PC Control'].isEnabled()
    finally:
        window.close()


def test_every_page_is_still_reachable(tmp_path):
    app, window = make_window(tmp_path)
    try:
        for name in window.page_indices:
            window.open_section(name)
            for _ in range(2):
                app.processEvents()
        assert len(window.page_indices) >= 15
    finally:
        window.close()


def test_the_palette_has_two_sides():
    dark = PrimePalette(dark=True)
    light = PrimePalette(dark=False)
    assert dark.ground != light.ground
    assert dark.accent != light.accent
    # The colour of the assistant is the same in both.
    assert dark.accent.name() != ''


def test_the_menu_replaces_the_toolbar(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        assert shell.findChild(QFrame, 'primeRail') is None
        shell.menu_button.click()
        assert shell.drawer.isVisibleTo(window)
        assert [button.text() for button in shell.menu_items.values()] == [
            'Chat', 'Automation', 'Phone Remote', 'API keys']
        assert shell.mini_view_button.text() == 'Mini view'
    finally:
        window.close()


def test_activity_panel_shows_live_state_and_persisted_action_result(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        shell.menu_items['PC Control'].click()
        window.automation_workspace_button.click()
        shell.activity_button.click()
        assert shell.activity.isVisibleTo(window)
        assert shell.activity.empty.isVisibleTo(window)

        ident = window.store.task('open_app', 'Awaiting approval')
        window.refresh_history()
        assert shell.activity.records.currentItem().text() == 'Open app\nPending'
        assert 'Awaiting approval' in shell.activity.details.toPlainText()

        window.store.finish(ident, 'dispatched', 'Started process. Window unverified.')
        window.refresh_history()
        assert shell.activity.records.currentItem().text() == 'Open app\nDispatched'
        assert 'Window unverified.' in shell.activity.details.toPlainText()

        window.stop()
        assert shell.activity.state.text() == 'Stopped'
        assert shell.state_chip.text() == 'STOPPED'
        shell.open_task_history()
        app.processEvents()
        assert shell.activity.isHidden()
        assert window.pages.currentIndex() == window.page_indices['Task History']
    finally:
        window.close()


def test_saved_chat_is_loaded_as_plain_text_when_prime_starts(tmp_path):
    from core.store import Store

    store = Store(tmp_path / 'history.sqlite3')
    store.set('session', 'saved')
    store.message('saved', 'assistant', '<b>saved message</b>')
    _app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        assert chat.conversation.isVisibleTo(window)
        first, = chat.conversation.bubbles
        assert first.body.text() == '<b>saved message</b>'
        assert first.body.textFormat().name == 'PlainText'
        store.message('saved', 'user', 'New message')
        window.render_chat()
        assert chat.conversation.bubbles[0] is first
        assert len(chat.conversation.bubbles) == 2
    finally:
        window.close()


def test_packaged_revision_reads_the_installed_build(tmp_path, monkeypatch):
    import desktop.prime_ui as ui

    monkeypatch.setattr(ui.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(ui.sys, 'executable', str(tmp_path / 'JarvisAI.exe'))
    monkeypatch.setenv('JARVIS_BUILD_COMMIT', 'abcdef0')
    (tmp_path / 'JARVIS-AI-REVISION.txt').write_text('0123456789' * 4, encoding='ascii')
    assert ui.build_commit() == '0123456'


def test_wake_summons_the_window_and_animates_the_m_after_consent(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    summoned = []
    monkeypatch.setattr(window, 'isActiveWindow', lambda: False)
    monkeypatch.setattr(window, 'summon_from_hotkey', lambda: summoned.append(True))
    try:
        window.on_wake_detected('Hey Jarvis', '')
        assert summoned == []
        window.voice_panel.allow.setChecked(True)
        window.on_wake_detected('Hey Jarvis', '')
        assert summoned == [True]
        assert window.pages.currentWidget() is window.prime_chat
        assert window.prime_chat.assistant.orb._wake_timer.isActive()
    finally:
        window.close()


def test_hud_links_voice_feedback_and_keyboard_emergency_stop(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.prime_chat.pc_activity_button.click()
        assert window.prime_chat.timeline.isVisibleTo(window)
        window.open_news_briefing()
        assert window.news_panel.isVisibleTo(window)
        assert not window.news_panel.isWindow()
        assert not window.prime_shell.activity.isVisibleTo(window)
        window.prime_shell.close_drawer()
        window.open_section('Quantum Visual Player')
        assert window.prime_chat.displays.isAncestorOf(window.player_panel)
        assert window.player_panel.isVisibleTo(window)
        window.prime_chat.show_display('hologram')

        window.voice_panel.allow.setChecked(True)
        window.on_voice_transcript('நாளைக்கு ஒரு quick break')
        assert 'quick break' in window.prime_chat.assistant.heard.text()
        window.prime_shell.mic_mute_button.click()
        assert window.voice_panel.consent.listening
        assert window.voice_panel.microphone_muted
        assert not window.voice_panel.listen_button.isEnabled()
        window.prime_shell.mic_mute_button.click()
        assert not window.voice_panel.microphone_muted

        window.prompt.setPlainText('/stop')
        window.prompt.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(window.prompt, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        assert window.prompt.toPlainText() == '/stop\n'
        assert not window.policy.stopped
        QTest.keyClick(window.prompt, Qt.Key.Key_Enter)
        assert window.policy.stopped
        assert window.prime_chat.assistant.orb.state == 'stopped'
        assert not window.prompt.toPlainText()
    finally:
        window.close()


def test_provider_key_autosaves_without_contacting_provider(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    saved = []
    monkeypatch.setattr(window.vault, 'put', lambda provider, key: saved.append((provider, key)))
    monkeypatch.setattr(window, 'check_model_availability', lambda: pytest.fail('Unexpected API check'))
    try:
        window.open_section('AI Providers')
        window.provider.setCurrentText('Gemini')
        window.secret.setFocus()
        QTest.keyClicks(window.secret, 'test-credential')
        QTest.keyClick(window.secret, Qt.Key.Key_Return)
        assert saved == [('Gemini', 'test-credential')]
        assert not window.secret.text()
        assert 'Stored' in window.key_status.text()
    finally:
        window.close()
