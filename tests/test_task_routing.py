from PySide6.QtWidgets import QApplication
from desktop.app import Window


def test_chat_routes_known_tasks_without_provider_request(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        for command, section in [
            ("MP4 export பண்ணு", "Video Editor"),
            ("After Effects timeline தயார் செய்", "Video Editor"),
            ("render after effects", "Video Editor"),
            ("Fiverr client reply, ask for footage", "Business"),
        ]:
            window.prompt.setPlainText(command)
            window.send()
            assert window.pages.currentIndex() == window.page_indices[section]
            assert window.worker is None
            assert window.prompt.toPlainText() == ""
        assert window.business_brief.toPlainText() == "ask for footage"
        assert window.store.messages(window.session) == []
        window.stop()
        window.prompt.setPlainText("render after effects")
        window.send()
        assert window.prompt.toPlainText() == "render after effects"
    finally:
        window.close()
        app.processEvents()


def test_natural_task_preserves_brief_and_leaves_questions_in_chat(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        request = "என் Fiverr வாடிக்கையாளருக்கு பதில் எழுது. Footage கேள்."
        window.prompt.setPlainText(request)
        window.send()
        assert window.pages.currentIndex() == window.page_indices["Business"]
        assert window.business_task.currentText() == "Fiverr client reply"
        assert window.business_brief.toPlainText() == request
        assert window.worker is None
        assert window.route_task("In After Effects, build a timeline from these clips")
        assert not window.route_task("How do I export an MP4?")
        assert not window.route_task("CapCut-ல் MP4 export பண்ணு")
        assert not window.route_task("Build an After Effects timeline and render it to MP4")
        window.voice_panel.allow.setChecked(True)
        window.on_voice_transcript("Google Flow prompts தயார் செய். Opening close-up.")
        assert window.video_brief.toPlainText() == "Google Flow prompts தயார் செய். Opening close-up."
    finally:
        window.close()
        app.processEvents()
