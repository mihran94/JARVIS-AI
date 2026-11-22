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


@pytest.mark.parametrize(("command", "brief", "engine", "label"), [
    ("வீடியோ எடிட்டர், archive footage", "archive footage", "Google Flow", "Flow prompt"),
    ("Higgsfield prompts தயார் செய்", "Higgsfield prompts தயார் செய்", "Higgsfield", "Google Flow fallback (adapt for Higgsfield)"),
])
def test_voice_drafts_then_explicit_gemini_click_exports_plan(
    tmp_path, monkeypatch, command, brief, engine, label
):
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
        win.on_wake_detected("Hey Jarvis", command)
        assert win.video_brief.toPlainText() == brief
        assert win.video_engine.currentText() == engine
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
        assert body["messages"][-1]["content"] == brief
        assert engine in body["messages"][0]["content"]
        assert f"{label}: Slow push-in." in win.video_preview.toPlainText()
        if engine == "Higgsfield":
            assert "PARTIAL PLAN" in win.video_preview.toPlainText()
            assert "Higgsfield prompt: (not specified)" in win.video_preview.toPlainText()
        assert win.store.messages(win.session) == []

        approvals = []
        win.confirm = lambda action: approvals.append(action) or True
        for button in win.video_export_buttons:
            button.click()
        paths = [win.workspace.path(action.target) for action in approvals]
        assert paths[0].parent == paths[1].parent
        saved = json.loads(paths[0].read_text(encoding="utf-8"))
        assert saved["height"] == 1920
        assert saved["engine"] == engine
        srt = paths[1].read_text(encoding="utf-8")
        assert "00:00:21,000 --> 00:00:30,000\nWhat happened?" in srt

        win.video_engine.setCurrentIndex(1 - win.video_engine.currentIndex())
        assert not any(button.isEnabled() for button in win.video_export_buttons)
    finally:
        win.close()
        win.deleteLater()
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
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("valid", [True, False])
def test_editopro_reply_reviews_input_and_copies_only_english(tmp_path, monkeypatch, valid):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    requests = []
    brief = "Can you animate my lyrics? Please tell me the price."
    summary = "வாடிக்கையாளருக்கு பாடல் வரிகள் animation வேண்டும்."
    reply = "Hi! Please share the song length and a style reference so I can prepare a quote."

    def complete(request):
        requests.append(json.loads(request.content))
        draft = {"english_reply": reply}
        if valid:
            draft["tamil_summary"] = summary
        payload = json.dumps(draft)
        chunk = {"choices": [{"delta": {"content": f"```json\n{payload}\n```"}}]}
        return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(win.vault, "get", lambda provider: "fake-gemini-key")
    win.router = ProviderRouter(transport=httpx.MockTransport(complete))
    clipboard = QApplication.clipboard()
    before = clipboard.text()
    try:
        win.prompt.setPlainText("JARVIS, Editopro reply: " + brief)
        win.send()
        assert win.business_task.currentText() == "Editopro reply (Tamil + English)"
        assert win.business_brief.toPlainText() == brief
        assert win.worker is None
        assert not requests

        win.business_generate.click()
        deadline = time.monotonic() + 5
        while win.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert win.worker is None
        assert len(requests) == 1
        assert requests[0]["messages"][-1]["content"] == brief
        assert win.store.messages(win.session) == []
        if valid:
            assert summary in win.business_preview.toPlainText()
            assert reply in win.business_preview.toPlainText()
            assert win.business_copy.text() == "Copy English reply"
            win.business_copy.click()
            assert clipboard.text() == reply
            win.business_brief.setPlainText("A different client")
            assert not win.business_copy.isEnabled()
        else:
            assert not win.business_preview.toPlainText()
            assert not win.business_copy.isEnabled()
            assert "omitted" in win.business_status.text()
    finally:
        clipboard.setText(before)
        win.close()
        win.deleteLater()
        app.processEvents()
