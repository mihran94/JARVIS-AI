"""Exercise the voiced brief, Gemini routing and approved subtitle export."""
import json
import time

import httpx
from PySide6.QtWidgets import QApplication
import pytest

from desktop.app import Window
from providers.router import ProviderRouter
from video_studio.planning import parse_plan


def draft():
    return {
        "title": "AI Mystery World",
        "verification_notes": "Confirm the date before publication.",
        "shots": [
            {
                "end_ms": end,
                "tamil_voiceover": "என்ன நடந்தது?",
                "english_subtitle": "What happened?",
                "visual": "Presenter close-up",
                "flow_prompt": "Slow push-in. Preserve the presenter’s face.",
                "edit_and_sound": "Keep narration above ambience.",
            }
            for end in (5000, 12_000, 21_000, 30_000)
        ],
    }


def test_rejects_incomplete_timeline():
    plan = draft()
    plan["shots"][-1]["end_ms"] = 29_000
    with pytest.raises(ValueError, match="end at 30 seconds"):
        parse_plan(json.dumps(plan))


def test_voice_drafts_then_explicit_gemini_click_exports_plan(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    requests = []

    def complete(request):
        requests.append((request.url.host, json.loads(request.content)))
        chunk = {"choices": [{"delta": {"content": json.dumps(draft())}}]}
        return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(win.vault, "get", lambda provider: "fake-gemini-key")
    monkeypatch.setattr(win.voice_panel, "listen", lambda mode: None)
    win.router = ProviderRouter(transport=httpx.MockTransport(complete))
    try:
        win.voice_panel.allow.setChecked(True)
        win.chat_provider.setCurrentText("Ollama")
        win.hands_free_voice.setChecked(True)
        win.on_wake_detected("Hey Jarvis", "வீடியோ எடிட்டர், archive footage")
        assert win.video_brief.toPlainText() == "archive footage"
        assert win.pages.currentIndex() == win.page_indices["Video Editor"]
        assert requests == []
        assert win.worker is None

        win.video_generate_button.click()
        deadline = time.monotonic() + 5
        while win.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert win.worker is None
        assert len(requests) == 1
        host, body = requests[0]
        assert host == "generativelanguage.googleapis.com"
        assert body["messages"][-1]["content"] == "archive footage"
        assert "Flow prompt: Slow push-in." in win.video_preview.toPlainText()
        assert win.store.messages(win.session) == []

        approvals = []
        win.confirm = lambda action: approvals.append(action) or True
        for button in win.video_export_buttons:
            button.click()
        paths = [win.workspace.path(action.target) for action in approvals]
        assert paths[0].parent == paths[1].parent
        assert json.loads(paths[0].read_text(encoding="utf-8"))["height"] == 1920
        srt = paths[1].read_text(encoding="utf-8")
        assert "00:00:21,000 --> 00:00:30,000\nWhat happened?" in srt

        win.video_brief.setPlainText("Another scene")
        assert not any(button.isEnabled() for button in win.video_export_buttons)
    finally:
        win.close()
        app.processEvents()


def test_business_voice_drafts_without_external_account_access(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    requests = []

    def complete(request):
        requests.append((request.url.host, json.loads(request.content)))
        chunk = {"choices": [{"delta": {"content": "Please share the clips and deadline."}}]}
        return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(win.vault, "get", lambda provider: "fake-gemini-key")
    win.router = ProviderRouter(transport=httpx.MockTransport(complete))
    try:
        win.voice_panel.allow.setChecked(True)
        win.on_wake_detected("Hey Jarvis", "Fiverr client reply, client wants a reel")
        assert win.pages.currentIndex() == win.page_indices["Business"]
        assert win.business_task.currentText() == "Fiverr client reply"
        assert win.business_brief.toPlainText() == "client wants a reel"
        assert requests == []

        win.business_generate.click()
        deadline = time.monotonic() + 5
        while win.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert win.worker is None
        assert len(requests) == 1
        assert requests[0][0] == "generativelanguage.googleapis.com"
        assert requests[0][1]["messages"][-1]["content"] == "client wants a reel"
        assert win.business_preview.toPlainText() == "Please share the clips and deadline."

        win.on_voice_transcript("Website update, rewrite the home page")
        assert win.business_task.currentText() == "Website content update"
        assert win.business_preview.toPlainText() == ""
        assert len(requests) == 1
        win.stop()
        assert not win.business_generate.isEnabled()
    finally:
        win.close()
        app.processEvents()
