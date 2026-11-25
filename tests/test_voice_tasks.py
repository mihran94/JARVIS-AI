from desktop.app import Window
from desktop.voice_tasks import local_voice_request
from PySide6.QtWidgets import QApplication


def test_live_voice_calculation_parses_mixed_language():
    route, request = local_voice_request('JARVIS M, Calculator-la 17 times 23 calculate pannu')
    assert route == 'desktop'
    assert request.app == 'Calculator'
    assert request.text == '17 * 23'
    assert local_voice_request('கால்குலேட்டரில் பதினேழு பெருக்கல் இருபத்து மூன்று கணக்கு போடு')[1] == request
    assert local_voice_request('I said Calculator-la 17 times 23 calculate pannu') is None


def test_live_transcript_requests_approval_in_the_same_app(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        assert window.windowTitle() == 'JARVIS M'
        window.save_live_voice_turn('Calculator-la 17 times 23 calculate pannu', '')
        assert window.chat_launch is not None
        assert '17 * 23' in window.chat_approval_label.text()
        assert window.desktop_pending is None
        window.finish_chat_launch(False)
        window.save_live_voice_turn('என்னோட saved projects list காட்டு', '')
        messages = window.store.messages(window.session)
        assert messages[-2]['content'] == 'என்னோட saved projects list காட்டு'
        assert 'No saved projects' in messages[-1]['content']
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
