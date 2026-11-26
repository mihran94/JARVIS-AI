"""The unified JARVIS desktop keeps one command center and one safety policy."""
import os
import time
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.blue_orb import BlueOrb
from desktop.omega_visuals import DEFAULT_THEME, theme_sheet
from desktop.network_metrics import NetworkSampler, format_network
from desktop.voice_commands import parse_voice_command


def test_one_dashboard_has_orb_read_only_metrics_and_existing_pages(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        assert window.styleSheet() == theme_sheet(DEFAULT_THEME)
        assert isinstance(window.orb, BlueOrb)
        # Media uses the same dashboard and player as the file browser.
        assert window.page_indices['Quantum Visual Player'] == window.page_indices['JARVIS Chat']
        assert window.prime_chat.displays.isAncestorOf(window.player_panel)
        destinations = {window.nav.item(i).text() for i in range(window.nav.count())}
        assert 'CPU' in window.system_metrics_label.text()
        assert {'Phone Remote', 'Voice / Hey Jarvis', 'JARVIS Chat'} <= destinations
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
        # The window is destroyed, not just closed: a closed window keeps its
        # widgets and its OpenGL resources alive, and the next test then
        # renders far more slowly than it should.
        window.deleteLater()
        app.processEvents()


def test_missing_optional_network_sampler_does_not_break_dashboard():
    sampler = NetworkSampler(counter_reader=lambda: None)
    assert sampler.sample() is None
    assert 'unavailable' in format_network(None)


def test_imported_tamil_intent_remains_allowlisted():
    assert parse_voice_command('நோட்பேட் திற') == 'Notepad'
    assert parse_voice_command('open notepad and delete everything') is None


def test_hud_and_local_commands_use_the_same_counters(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('desktop.app.snapshot', lambda *_: {
        'cpu_cores': 8, 'cpu_usage_percent': 31.2, 'ram_usage_percent': 25.0,
        'ram_used_gib': 4.0, 'ram_total_gib': 16.0,
    })
    window = Window(tmp_path)

    def unexpected_key_request(_provider):
        raise AssertionError('System commands should not use an AI provider')

    monkeypatch.setattr(window, 'get_key', unexpected_key_request)
    try:
        window.show()
        window.open_section('Command Center')
        app.processEvents()
        label, meter = window.hud_meters['cpu_usage_percent']
        assert label.text() == '31.2%'
        assert meter.value() == 312
        assert window.hud_meters['ram_usage_percent'][0].text() == '25.0%'
        window.fullscreen_button.click()
        assert window.isFullScreen()
        window.fullscreen_button.click()
        assert not window.isFullScreen()

        window.open_section('JARVIS Chat')
        for prompt in ('/status', 'நேரம்'):
            window.prompt.setPlainText(prompt)
            window.send_button.click()
            assert window.worker is None
        messages = window.store.messages(window.session)
        assert '31.2% usage' in messages[1]['content']
        assert 'Phone Remote: Stopped' in messages[1]['content']
        assert len(messages[-1]['content'].split()[0]) == 5
        outbound = []
        monkeypatch.setattr(window, 'get_key', lambda _: 'test-key')
        monkeypatch.setattr(window, 'start_worker', lambda provider, model, key, messages, *a, **kw:
                            outbound.extend(messages))
        window.prompt.setPlainText('Explain how timelines work')
        window.send_button.click()
        assert [message['role'] for message in outbound] == ['system', 'user']
        assert outbound[-1]['content'] == 'Explain how timelines work'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_hud_says_listening_while_the_microphone_is_listening(tmp_path, monkeypatch):
    """The HUD must not say IDLE while the microphone is really listening.

    The worker thread is not running yet when start() returns, so the state
    read straight after the button is pressed can still say "not listening".
    The panel refreshes when the thread really starts, and the HUD follows.
    """
    from threading import Event

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    voice = window.voice_panel
    release = Event()

    class Recognizer:
        def wait_for_wake_phrase(self, timeout):
            release.wait(30)
            return '', ''

        def recognize_once(self, timeout):
            return ''

        def stop(self):
            pass

    monkeypatch.setattr(voice, '_recognizer_factory', lambda *_: Recognizer())
    try:
        window.open_section('Command Center')
        voice.allow.setChecked(True)
        voice.listen('continuous')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            app.processEvents()
            if window.hud_voice_status.text() == 'LISTENING':
                break
            time.sleep(0.01)
        assert window.hud_voice_status.text() == 'LISTENING', (
            'the HUD did not show LISTENING while the microphone was listening')
    finally:
        release.set()
        window.stop()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_voice_panel_refreshes_when_the_worker_thread_really_starts(tmp_path, monkeypatch):
    """The panel must refresh again when the worker thread really starts.

    The worker thread is not running yet when start() returns, so the state
    read straight afterwards can still say "not listening". On a loaded
    machine that is exactly when the HUD would keep saying IDLE while the
    microphone is live. The refresh has to happen again when the thread
    begins, so the status the owner reads is always the true one.
    """
    from threading import Event

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    voice = window.voice_panel
    release = Event()

    class Recognizer:
        def wait_for_wake_phrase(self, timeout):
            release.wait(30)
            return '', ''

        def recognize_once(self, timeout):
            return ''

        def stop(self):
            pass

    calls = []
    original_refresh = voice.refresh

    def counting_refresh():
        calls.append(1)
        original_refresh()

    monkeypatch.setattr(voice, '_recognizer_factory', lambda *_: Recognizer())
    monkeypatch.setattr(voice, 'refresh', counting_refresh)
    try:
        window.open_section('Command Center')
        voice.allow.setChecked(True)
        calls.clear()
        voice.listen('continuous')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(calls) < 2:
            app.processEvents()
            time.sleep(0.01)
        assert len(calls) >= 2, (
            'the voice panel did not refresh when the worker thread started')
    finally:
        release.set()
        window.stop()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_continuous_voice_waits_for_playback_before_listening_again(tmp_path, monkeypatch):
    from threading import Event

    from PySide6.QtTest import QTest

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    voice = window.voice_panel
    release_input = Event()
    release_audio = Event()
    playback_started = Event()
    recognizers = []
    replies = []

    class Recognizer:
        def wait_for_wake_phrase(self, timeout):
            if len(recognizers) == 1:
                # The stub holds for as long as the test needs. A short
                # timeout here ends the recognition before a slow machine
                # has delivered the state the test is waiting for.
                release_input.wait()
                return 'Hey Jarvis', ''
            voice.worker.msleep(20)
            return '', ''

        def recognize_once(self, timeout):
            return 'What time is it'

        def stop(self):
            pass

    class Speaker:
        def speak_interruptibly(self, text, should_stop):
            replies.append(text)
            playback_started.set()
            # The playback holds until the test says so, so the HUD is
            # SPEAKING for as long as the test waits for it.
            # The test's finally block always releases this event. A wall-clock
            # timeout can expire while a loaded CI runner paints other windows,
            # removing SPEAKING before the assertion can inspect it.
            release_audio.wait()

    def recognizer_factory(*_):
        recognizer = Recognizer()
        recognizers.append(recognizer)
        return recognizer

    def wait_for(condition):
        # The budget is generous on purpose. The states below arrive
        # across a thread boundary, and a slow or loaded machine needs
        # longer to deliver them than a quiet one does: the Windows
        # runner works through the whole suite in one process, and the
        # voice handoff has to win its turn in that queue. The assertion
        # is the same either way: the HUD must reach the state.
        for _ in range(900):
            app.processEvents()
            if condition():
                return
            QTest.qWait(10)
        assert condition()

    def unexpected_provider(_):
        raise AssertionError('Voice system commands must be handled locally')

    monkeypatch.setattr(window, 'get_key', unexpected_provider)
    voice._recognizer_factory = recognizer_factory
    voice._speaker_factory = Speaker
    # Exercise playback state deterministically without calling Gemini or
    # opening the host speaker. Production readout uses Gemini exclusively.
    monkeypatch.setattr(window, 'read_with_gemini', voice.speak_response)
    try:
        window.open_section('Command Center')
        voice.allow.setChecked(True)
        window.read_replies.setChecked(True)
        voice.listen('continuous')
        # The status arrives from the voice worker on its own thread, so the
        # event loop has to deliver it. Waiting for it is what the test is
        # about; the other states below are waited for the same way.
        wait_for(lambda: window.hud_voice_status.text() == 'LISTENING')
        release_input.set()
        wait_for(playback_started.is_set)
        wait_for(lambda: window.hud_voice_status.text() == 'SPEAKING')
        assert window.hud_orb._state == 'speaking'
        assert window.hud_voice_reply.text() == replies[0]
        assert not voice.listening
        QTest.qWait(400)
        assert len(recognizers) == 1
        release_audio.set()
        wait_for(lambda: len(recognizers) == 2)
        window.stop()
        assert window.hud_voice_status.text() == 'STOPPED'
        assert not voice.continuous
        assert not voice.wake_timer.isActive()
    finally:
        release_input.set()
        release_audio.set()
        window.close()
        window.deleteLater()
        app.processEvents()
