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
        assert not window.hud.isVisibleTo(window)
        assert shell.state_chip.isVisibleTo(window)
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
        assert shell.state_chip.isVisibleTo(window)
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
        assert window.pages.currentWidget() is window.prime_chat
        assert window.prime_chat.task_area.isAncestorOf(panel)
        assert window.prime_chat.chat_history.isVisibleTo(window)
        assert window.send_button.isVisibleTo(window)
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
        dialog = window.prime_shell.settings_dialog
        assert not window.reply_language.isVisibleTo(dialog)
        window.advanced_voice_toggle.setChecked(True)
        assert not window.reply_language.isVisibleTo(dialog)
        assert window.reply_language.currentData() == 'auto'
        assert window.reply_tone.currentData() == 'friendly'
        tabs = window.settings_categories
        system_tab = tabs.findText('System')
        tabs.setCurrentIndex(system_tab)
        app.processEvents()
        assert not window.reply_language.isVisibleTo(dialog)
        scroll = scroller.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        assert scroll.value() > 0
        window.open_section('Settings & Safety')
        assert scroll.value() == 0
        assert dialog.isVisible()
        assert window.get_key('Gemini') == 'test-key'

        window.open_section('JARVIS Chat')
        window.prompt.setPlainText('Namma ippo enna pesalam?')
        window.send()
        assert 'Latin script for Tanglish' in sent[-1][0]['content']
        assert 'Talk like a helpful colleague' in sent[-1][0]['content']

        window.open_section('Settings & Safety')
        window.reply_language.setCurrentIndex(window.reply_language.findData('tanglish'))
        window.reply_tone.setCurrentIndex(window.reply_tone.findData('direct'))
        window.open_section('JARVIS Chat')
        assert window.prime_chat.assistant.title.text() == 'What can I help with?'
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
        assert window.prime_chat.assistant.title.text() == 'What can I help with?'
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
        assert set(shell.menu_items) == {'JARVIS Chat', 'PC Control'}
        assert {'Projects', 'Files & folders', 'Task queue', 'Workflows', 'Review changes'} <= set(
            window.automation_tools)
    finally:
        window.close()


def test_the_composer_uses_the_real_prompt_and_the_real_buttons(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        assert chat.chat_history.isAncestorOf(chat.conversation)
        assert chat.chat_column.isAncestorOf(window.prompt)
        assert chat.command_panel.isAncestorOf(window.prompt)
        assert chat.chat_history.isAncestorOf(chat.assistant.heard)
        assert chat.chat_column.layout().indexOf(chat.chat_history) < chat.chat_column.layout().indexOf(chat.command_panel)
        assert chat.composer.body.itemAt(0).widget() is window.attach_button
        entry = chat.composer.body.itemAt(1).layout()
        assert entry.itemAt(0).widget() is window.prompt
        assert entry.itemAt(1).widget() is window.send_button
        controls = chat.composer.controls
        found = [controls.itemAt(index).widget()
                 for index in range(controls.count())
                 if controls.itemAt(index).widget() is not None]
        assert found == [window.prime_shell.mic_mute_button, window.camera_toggle]
        assert chat.voice_button.isHidden()
        assert chat.suggestions_button.isHidden()
        chat.populate_suggestions()
        assert 'Suggest next steps' in [action.text() for action in chat.suggestions_menu.actions()]
        window.prompt.setPlainText('Open Calculator')
        chat.populate_suggestions()
        assert 'Suggest with Gemini' in [
            action.text() for action in chat.suggestions_menu.actions()]
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
        chat = window.prime_chat
        chat.render([{'role': 'assistant', 'content': 'This wraps across several lines. ' * 9}
                     for _ in range(14)])
        for _ in range(4):
            app.processEvents()
        window.open_section('Settings & Safety')
        for _ in range(4):
            app.processEvents()
        bar = conversation.verticalScrollBar()
        last = conversation.bubbles[-1]
        assert bar.value() == bar.maximum()
        assert conversation.viewport().rect().contains(
            last.mapTo(conversation.viewport(), last.rect().bottomLeft()))
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
        assert window.prime_shell.mark.text() == 'M'
        assert window.prime_chat.assistant.orb.state == 'listening'
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
            'Chat', 'Automation']
        assert shell.mini_view_button.text() == 'Mini view'
    finally:
        window.close()


def test_activity_panel_shows_live_state_and_persisted_action_result(tmp_path):
    app, window = make_window(tmp_path)
    try:
        shell = window.prime_shell
        window.prime_chat.show_display('timeline')
        timeline = window.prime_chat.timeline
        assert timeline.isVisibleTo(window)
        assert timeline.empty.isVisibleTo(window)

        ident = window.store.task('open_app', 'Awaiting approval')
        window.refresh_history()
        assert timeline.records.currentItem().text() == 'Open app\nPending'
        assert 'Awaiting approval' in timeline.details.toPlainText()

        window.store.finish(ident, 'dispatched', 'Started process. Window unverified.')
        window.refresh_history()
        assert timeline.records.currentItem().text() == 'Open app\nDispatched'
        assert 'Window unverified.' in timeline.details.toPlainText()

        window.stop()
        assert timeline.state.text() == 'Stopped'
        assert shell.state_chip.text() == 'STOPPED'
        shell.open_task_history()
        app.processEvents()
        assert not timeline.isVisibleTo(window)
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
        window.prime_chat.show_display('timeline')
        assert window.prime_chat.timeline.isVisibleTo(window)
        window.open_news_briefing()
        assert window.news_panel.isVisibleTo(window)
        assert not window.news_panel.isWindow()
        window.prime_shell.close_drawer()
        window.open_section('Quantum Visual Player')
        assert window.prime_chat.displays.isAncestorOf(window.player_panel)
        assert window.player_panel.isVisibleTo(window)
        window.prime_chat.show_display('hologram')

        window.voice_panel.allow.setChecked(True)
        window.on_voice_transcript('நாளைக்கு ஒரு quick break')
        assert 'quick break' in window.prime_chat.assistant.heard.toPlainText()
        full_sentence = ('இன்னைக்கு meeting முடிஞ்சதும் ஒரு quick break எடுக்கலாம். ' * 4).strip()
        window.prime_chat.assistant.show_heard(full_sentence)
        assert window.prime_chat.assistant.heard.toPlainText().endswith(full_sentence)
        assert window.prime_chat.assistant.heard.isReadOnly()
        window.prime_shell.mic_mute_button.click()
        assert window.voice_panel.consent.listening
        assert window.voice_panel.microphone_muted
        assert not window.voice_panel.listen_button.isEnabled()
        window.prime_shell.mic_mute_button.click()
        assert not window.voice_panel.microphone_muted
        window.prime_shell.output_mute_button.click()
        assert window.voice_panel.muted
        assert window.voice_panel.consent.listening
        window.voice_panel.mute_button.click()
        assert not window.prime_shell.output_mute_button.isChecked()

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


def test_welcome_and_spoken_update_use_the_existing_local_routes(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        spoken = []
        window.preferred_name.setText('தமிழ் பயனர்')
        window.preferred_name.editingFinished.emit()
        assert window.store.get('chat:preferred_name') == 'தமிழ் பயனர்'
        window.startup_greeting.setChecked(True)
        monkeypatch.setattr(window, 'read_with_gemini', spoken.append)
        window.start_window_audio()
        assert 'தமிழ் பயனர்' in window.prime_shell.startup_notice.text()
        assert spoken == [window.prime_shell.startup_notice.text()]

        opened = []
        monkeypatch.setattr(window, 'start_improvement',
                            lambda *, show_review: opened.append(
                                (window.improvement_goal.text(), show_review)))
        window.voice_panel.allow.setChecked(True)
        window.on_voice_transcript('Jarvis update pannu improve the mic indicator')
        assert opened == [('improve the mic indicator', True)]
        assert not window.route_self_update('I was asking about how update pannu works')
    finally:
        window.close()


def test_gemini_voice_waits_for_the_local_listener_to_release_the_mic(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    class LocalListener:
        running = True
        interrupted = False

        def isRunning(self):
            return self.running

        def isInterruptionRequested(self):
            return self.interrupted

        def requestInterruption(self):
            self.interrupted = True

    listener = LocalListener()
    opened = []
    monkeypatch.setattr(window, 'get_key', lambda _: 'test-key')
    monkeypatch.setattr(window, 'confirm', lambda _: True)
    monkeypatch.setattr(window, 'finish_live_voice_start', opened.append)
    try:
        window.voice_panel.allow.setChecked(True)
        window.voice_panel.worker = listener
        window.prime_chat.voice_button.click()
        assert listener.interrupted and window.live_voice_starting
        assert opened == []
        listener.running = False
        window.voice_panel.cycle_finished.emit()
        assert opened == ['test-key']
    finally:
        window.voice_panel.worker = None
        window.close()


def test_live_mixed_speech_is_saved_and_camera_requests_route(tmp_path, monkeypatch):
    from types import SimpleNamespace
    app, window = make_window(tmp_path)
    sent = []
    try:
        monkeypatch.setattr(window.camera_panel, 'snapshot', lambda: b'jpeg')
        window.live_voice = SimpleNamespace(look_at=lambda image, text: sent.append((image, text)) or True)
        assert window.route_camera_question('கேமரா விப் பண்ணி பாரு')
        assert sent == [(b'jpeg', 'கேமரா விப் பண்ணி பாரு')]
        window.live_voice = None
        spoken = 'இன்னைக்கு meeting முடிஞ்சதும் ஒரு quick break எடுக்கலாமா?'
        window.save_live_voice_turn(spoken, 'எடுக்கலாம் மிஹ்ரான் பாஸ்.')
        messages = window.store.messages(window.session)
        assert messages[-2]['content'] == spoken
        assert messages[-1]['content'] == 'எடுக்கலாம் மிஹ்ரான் பாஸ்.'
    finally:
        window.live_voice = None
        window.close()


def test_settings_close_outside_without_resizing_chat(tmp_path):
    app, window = make_window(tmp_path)
    try:
        geometry = window.prime_chat.geometry()
        window.open_section('Settings & Safety')
        app.processEvents()
        assert window.prime_chat.geometry() == geometry
        assert window.prime_shell.settings_dialog.isVisible()
        QTest.mouseClick(window.prime_shell.brand, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert not window.prime_shell.settings_dialog.isVisible()
        window.open_section('Settings & Safety')
        window.prime_shell.show_drawer('menu')
        assert not window.prime_shell.settings_dialog.isVisible()
        app.processEvents()
        assert window.prime_chat.geometry() == geometry
        assert window.prime_shell.drawer.height() < window.height()
        QTest.mouseClick(window.prime_shell.brand, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert not window.prime_shell.drawer.isVisible()
    finally:
        window.close()


def test_typed_chat_joins_the_running_voice_conversation(tmp_path):
    from types import SimpleNamespace
    app, window = make_window(tmp_path)
    packets = []
    try:
        window.live_voice = SimpleNamespace(active=True, send=packets.append)
        window.prompt.setPlainText('இன்னைக்கு ஒரு quick break எடுக்கலாம்')
        window.send()
        assert packets == [{'realtimeInput': {'text': 'இன்னைக்கு ஒரு quick break எடுக்கலாம்'}}]
        assert window.store.messages(window.session)[-1]['role'] == 'user'
        assert not window.prompt.toPlainText()
    finally:
        window.live_voice = None
        window.close()


def test_slash_suggestion_goes_to_gemini_without_running_a_pc_action(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    calls = []
    monkeypatch.setattr(window, 'send_chat_reply', lambda text, **options: calls.append((text, options)))
    try:
        window.prompt.setPlainText('/suggestion help me edit a short video')
        window.send()
        assert calls == [('help me edit a short video', {'suggestion': True, 'suggestions_online': True})]
        assert window.desktop_pending is None
        assert window.chat_launch is None
    finally:
        window.close()


def test_reference_footer_shortcuts_mute_close_settings_and_stop(tmp_path):
    app, window = make_window(tmp_path)
    try:
        QTest.keyClick(window, Qt.Key.Key_F4)
        app.processEvents()
        assert window.voice_panel.microphone_muted
        window.prime_shell.refresh_clock()
        assert 'MIC · MUTED' in window.prime_shell.footer_status.text()
        window.open_section('Settings & Safety')
        app.processEvents()
        window.prime_shell.interrupt_or_close()
        assert not window.prime_shell.settings_dialog.isVisible()
        assert not window.policy.stopped
        window.activateWindow()
        window.setFocus()
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Escape)
        app.processEvents()
        assert window.policy.stopped
    finally:
        window.close()


def test_reference_panels_show_real_status_and_keep_upload_with_command(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        chat.refresh_reference_panels({'network_status': '12 KB/s',
                                       'gpu_usage_percent': None, 'cpu_temperature_c': None})
        assert '12 KB/s' in chat.status_detail.text()
        assert chat.gpu_dial.text == 'N/A'
        assert chat.temperature_dial.text == 'N/A'
        assert 'Refresh' in chat.weather_detail.text()
        assert chat.command_panel.isAncestorOf(window.attach_button)
        assert chat.command_panel.isAncestorOf(window.send_button)
        assert chat.chat_history.isAncestorOf(chat.conversation)
        assert window.prime_shell.clock_label.text().count(':') == 2
    finally:
        window.close()
