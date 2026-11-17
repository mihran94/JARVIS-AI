"""Exercise the Video Editing Studio: one Tamil brief, two engines, two editors.

WHAT IS COVERED
    * One Tamil brief becomes a cinematic shot list that shows the duration,
      the camera movement, the lighting, the sound cues and the English
      subtitle for every shot.
    * The SAME brief produces a copy-ready prompt for Google Flow AND a
      copy-ready prompt for Higgsfield, without a second model call.
    * The editing checklist covers CapCut Desktop and DaVinci Resolve, and
      lists every shot.
    * A plan that arrives without every field is labelled partial instead of
      being shown as if it were complete.
    * The CapCut and DaVinci handoff packages really contain the video, the
      captions and the checklist.
    * Everything above is driven through the JARVIS window, not around it.
"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import time
from shutil import which

import httpx
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QPushButton
import pytest

from desktop.app import Window
from desktop.video_export import PreviewInputs
from providers.router import ProviderRouter
from video_studio.editing import clip_name, editing_checklist
from video_studio.planning import (
    NOT_SPECIFIED, parse_plan, prompt_sheet, shot_list, spoken_brief,
)

requires_ffmpeg = pytest.mark.skipif(
    not (which("ffmpeg") and which("ffprobe")), reason="FFmpeg and ffprobe are required")

BRIEF = "அய்யன் மரக்கன் தொடர்பான கதை — திறப்பு தரைப்பாடு, புதிய காட்சி, முடிவு"


def detailed_draft():
    """A plan the way the model is now asked to answer."""
    return {
        "title": "AI Mystery World",
        "verification_notes": "Confirm the date before publication.",
        "shots": [
            {
                "end_ms": end,
                "camera": "Slow push-in",
                "lighting": "Low key, single practical",
                "sound": "Room tone under narration",
                "tamil_voiceover": "என்ன நடந்தது?",
                "english_subtitle": "What happened?",
                "visual": "Presenter close-up",
                "flow_prompt": "Flow: slow push-in on the presenter, preserve her face.",
                "higgsfield_prompt": "Higgsfield: the presenter turns slowly, low key practical, moody.",
                "edit_and_sound": "Keep narration above ambience.",
            }
            for end in (5000, 12_000, 21_000, 30_000)
        ],
    }


def legacy_draft():
    """A plan the way the model answered before this section."""
    return {
        "title": "AI Mystery World",
        "verification_notes": "Confirm the date before publication.",
        "shots": [
            {
                "end_ms": end,
                "tamil_voiceover": "என்ன நடந்தது?",
                "english_subtitle": "What happened?",
                "visual": "Presenter close-up",
                "flow_prompt": "Slow push-in. Preserve the presenter's face.",
                "edit_and_sound": "Keep narration above ambience.",
            }
            for end in (5000, 12_000, 21_000, 30_000)
        ],
    }


def generate(win, draft, brief=BRIEF):
    """Type a brief and press Generate, the way the owner does."""
    requests = []

    def complete(request):
        requests.append((request.url.host, json.loads(request.content)))
        chunk = {"choices": [{"delta": {"content": json.dumps(draft)}}]}
        return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    win.router = ProviderRouter(transport=httpx.MockTransport(complete))
    win.video_brief.setPlainText(brief)
    win.video_generate_button.click()
    app = QApplication.instance()
    deadline = time.monotonic() + 5
    while win.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert win.worker is None
    return requests


def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    monkeypatch.setattr(win.vault, "get", lambda provider: "fake-gemini-key")
    monkeypatch.setattr(win, "get_key", lambda provider: "fake-gemini-key")
    return win, app


# ── one Tamil brief ──────────────────────────────────────────────────────────

def test_a_tamil_voice_brief_is_recognised():
    assert spoken_brief("வீடியோ எடிட்டர், " + BRIEF) == BRIEF
    assert spoken_brief("cinematic reel: " + BRIEF) == BRIEF
    assert spoken_brief(BRIEF) is None


def test_the_tamil_brief_reaches_the_provider_unchanged(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        requests = generate(win, detailed_draft())
        assert len(requests) == 1
        host, body = requests[0]
        assert host == "generativelanguage.googleapis.com"
        assert body["messages"][-1]["content"] == BRIEF
        # The instruction must ask for BOTH engines, so one brief is enough.
        assert "Google Flow" in body["messages"][0]["content"]
        assert "Higgsfield" in body["messages"][0]["content"]
        assert "flow_prompt" in body["messages"][0]["content"]
        assert "higgsfield_prompt" in body["messages"][0]["content"]
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


# ── the shot list ────────────────────────────────────────────────────────────

def test_the_shot_list_shows_duration_camera_lighting_sound_and_subtitles(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, detailed_draft())
        listing = win.video_preview.toPlainText()
        assert "Camera: Slow push-in" in listing
        assert "Lighting: Low key, single practical" in listing
        assert "Sound: Room tone under narration" in listing
        assert "English: What happened?" in listing
        assert "5.0 s" in listing
        assert "00:00:00,000" in listing and "00:00:30,000" in listing
        assert "PARTIAL PLAN" not in listing
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_a_plan_without_the_cinematic_fields_is_labelled_partial(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, legacy_draft())
        listing = win.video_preview.toPlainText()
        assert "PARTIAL PLAN" in listing
        assert f"Camera: {NOT_SPECIFIED}" in listing
        assert f"Lighting: {NOT_SPECIFIED}" in listing
        assert f"Sound: {NOT_SPECIFIED}" in listing
        assert "English: What happened?" in listing
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


# ── one brief, two engines ───────────────────────────────────────────────────

def test_one_brief_produces_a_prompt_for_both_engines(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, detailed_draft())
        plan = win.video_plan[1]
        assert plan["shots"][0]["flow_prompt"].startswith("Flow:")
        assert plan["shots"][0]["higgsfield_prompt"].startswith("Higgsfield:")

        win.video_sheet_kind.setCurrentText('Flow prompts')
        flow = win.video_sheet.toPlainText()
        win.video_sheet_kind.setCurrentText('Higgsfield prompts')
        higgs = win.video_sheet.toPlainText()

        assert "Flow: slow push-in on the presenter" in flow
        assert "Higgsfield: the presenter turns slowly" in higgs
        assert "Flow: slow push-in on the presenter" not in higgs
        # The sheet is copy-ready: prompts only, one after another.
        assert flow.count("Shot ") == 4
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('make_draft', [legacy_draft, detailed_draft])
def test_the_higgsfield_sheet_labels_a_missing_prompt(tmp_path, monkeypatch, make_draft):
    draft = make_draft()
    draft['shots'][0].pop('higgsfield_prompt', None)
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, draft)
        win.video_sheet_kind.setCurrentText('Higgsfield prompts')
        sheet = win.video_sheet.toPlainText()
        assert "PARTIAL PLAN" in win.video_preview.toPlainText()
        assert "PARTIAL PLAN" in sheet
        assert f"Higgsfield prompt: {NOT_SPECIFIED}" in sheet
        assert f"Google Flow fallback (adapt for Higgsfield): {draft['shots'][0]['flow_prompt']}" in sheet
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


# ── the editing checklist ────────────────────────────────────────────────────

def test_the_editing_checklist_covers_capcut_and_davinci_resolve(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, detailed_draft())
        win.video_sheet_kind.setCurrentText('Editing checklist')
        checklist = win.video_sheet.toPlainText()
        assert "CapCut Desktop" in checklist
        assert "DaVinci Resolve" in checklist
        assert "ESTIMATED TIMINGS" in checklist
        for number in range(1, 5):
            assert f"Shot {number}" in checklist
            assert clip_name(number) in checklist
        assert "Camera: Slow push-in" in checklist
        assert "English subtitle: What happened?" in checklist
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_checklist_is_built_from_the_plan_alone():
    plan = parse_plan(json.dumps(detailed_draft()))
    checklist = editing_checklist(plan)
    assert "CapCut Desktop" in checklist
    assert "DaVinci Resolve" in checklist
    assert "english.srt" in checklist
    assert "PARTIAL PLAN" not in checklist


# ── copy ready ───────────────────────────────────────────────────────────────

def test_the_copy_button_puts_the_sheet_on_the_clipboard(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, detailed_draft())
        win.video_sheet_kind.setCurrentText('Flow prompts')
        win.video_copy_button.click()
        clipboard = QApplication.clipboard().text()
        assert "Flow: slow push-in on the presenter" in clipboard
        win.video_sheet_kind.setCurrentText('Editing checklist')
        win.video_copy_button.click()
        assert "DaVinci Resolve" in QApplication.clipboard().text()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_browser_handoff_copies_only_the_selected_shots_matching_prompt(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    opened = []
    monkeypatch.setattr('desktop.app.QDesktopServices.openUrl',
                        lambda url: opened.append(url.toString()) or True)
    draft = detailed_draft()
    draft['shots'][1]['flow_prompt'] = 'Flow shot two: dolly left.'
    draft['shots'][1]['higgsfield_prompt'] = 'Higgsfield shot two: track left.'
    try:
        generate(win, draft)
        win.video_handoff_shot.setCurrentIndex(1)
        win.video_tool_buttons['Google Flow'].click()
        assert QApplication.clipboard().text() == 'Flow shot two: dolly left.'
        win.video_tool_buttons['Higgsfield'].click()
        assert QApplication.clipboard().text() == 'Higgsfield shot two: track left.'
        assert opened == ['https://flow.google.com/', 'https://higgsfield.ai/ai-video']
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_browser_handoff_keeps_clipboard_when_the_matching_prompt_is_missing(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    opened = []
    monkeypatch.setattr('desktop.app.QDesktopServices.openUrl',
                        lambda url: opened.append(url.toString()) or True)
    QApplication.clipboard().setText('keep this text')
    try:
        assert not win.video_handoff_shot.isEnabled()
        win.video_tool_buttons['Google Flow'].click()
        assert QApplication.clipboard().text() == 'keep this text'
        generate(win, legacy_draft())
        win.video_tool_buttons['Higgsfield'].click()
        assert QApplication.clipboard().text() == 'keep this text'
        assert 'no Higgsfield prompt to copy' in win.statusBar().currentMessage()
        assert opened == ['https://flow.google.com/', 'https://higgsfield.ai/ai-video']
        win.video_brief.setPlainText('Updated brief')
        assert win.video_handoff_shot.count() == 0
        win.stop()
        assert not win.video_tool_buttons['Google Flow'].isEnabled()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


# ── the handoff packages ─────────────────────────────────────────────────────

def make_clips(tmp_path, count=4):
    """One clip per shot, the way the export expects them."""
    clips = []
    for index in range(count):
        clip = tmp_path / f"clip {index}.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=144x100:d=1",
            "-c:v", "libx264", str(clip),
        ], check=True)
        clips.append(clip)
    return clips


@requires_ffmpeg
def test_the_davinci_button_exports_video_captions_and_checklist(tmp_path, monkeypatch):
    clips = make_clips(tmp_path)
    win, app = window(tmp_path, monkeypatch)
    generate(win, detailed_draft())
    assert win.davinci_button.isEnabled()
    seen = []

    def choose_folder(_dialog, title, _initial):
        assert title == 'Choose export folder'
        seen.append('folder')
        return str(tmp_path)

    def accept_dialog(dialog):
        assert dialog.windowTitle() == 'Export for DaVinci Resolve'
        for field, clip in zip(dialog.clips, clips):
            field.setText(str(clip))
        button = next((button for button in dialog.findChildren(QPushButton)
                       if button.text() == 'Choose export folder…'), None)
        assert button is not None
        button.click()
        assert dialog.ok.isEnabled()
        return QDialog.DialogCode.Accepted

    def approve(action):
        seen.append(action.kind)
        assert action.target == str(tmp_path)
        return True

    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', choose_folder)
    monkeypatch.setattr(PreviewInputs, 'exec', accept_dialog)
    monkeypatch.setattr(win, 'confirm', approve)
    try:
        win.davinci_button.click()
        assert seen == ['folder', 'export_for_davinci']
        deadline = time.monotonic() + 90
        while win.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert win.worker is None
        folders = list(tmp_path.glob("JARVIS-DaVinci-*"))
        assert len(folders) == 1, win.video_status.text()
        folder = folders[0]
        assert (folder / "video.mp4").is_file()
        assert (folder / "english.srt").read_text(encoding="utf-8").startswith(
            "1\n00:00:00,000 --> 00:00:05,000\nWhat happened?")
        checklist = (folder / "editing-checklist.txt").read_text(encoding="utf-8")
        assert "CapCut Desktop" in checklist and "DaVinci Resolve" in checklist
        assert "not a Resolve XML timeline" in checklist
        assert "Shot 1" in (folder / "shot-prompts.txt").read_text(encoding="utf-8")
        assert not list(tmp_path.glob(".jarvis-davinci-*"))
    finally:
        if win.worker is not None:
            win.worker.requestInterruption()
            win.worker.wait()
            app.processEvents()
        win.close()
        win.deleteLater()
        app.processEvents()


@requires_ffmpeg
def test_the_capcut_handoff_still_works(tmp_path):
    from video_studio.capcut import export_capcut

    clips = make_clips(tmp_path)
    plan = parse_plan(json.dumps(detailed_draft()))
    folder = export_capcut(plan, clips, tmp_path, lambda: None)
    assert (folder / "video.mp4").is_file()
    assert (folder / "english.srt").read_text(encoding="utf-8").startswith(
        "1\n00:00:00,000 --> 00:00:05,000\nWhat happened?")
    assert not list(tmp_path.glob(".jarvis-capcut-*"))


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_video_page_offers_the_sheets_the_copy_and_the_resolve_export(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        kinds = [win.video_sheet_kind.itemText(index)
                 for index in range(win.video_sheet_kind.count())]
        assert kinds == ['Shot list', 'Flow prompts', 'Higgsfield prompts', 'Editing checklist']
        assert win.video_copy_button.text() == 'Copy to clipboard'
        assert win.davinci_button.text() == 'Export for DaVinci Resolve'
        assert win.capcut_button.text() == 'Export for CapCut Desktop'
        # Nothing is exportable before a plan exists.
        assert not win.davinci_button.isEnabled()
        assert not win.capcut_button.isEnabled()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_sheet_list_is_the_same_shot_list_the_preview_shows(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        generate(win, detailed_draft())
        win.video_sheet_kind.setCurrentText('Shot list')
        assert win.video_sheet.toPlainText() == win.video_preview.toPlainText()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_video_editor_page_stays_readable_at_narrow_desktop_size(tmp_path, monkeypatch):
    """The page must not ask to scroll sideways on a narrow window.

    A long button label sets a wide minimum on the whole page, and a page
    wider than the window can only be reached by scrolling sideways.
    """
    win, app = window(tmp_path, monkeypatch)
    try:
        win.resize(680, 510)
        win.show()
        app.processEvents()
        win.open_section('Video Editor')
        app.processEvents()
        page = win.pages.currentWidget()
        assert page.horizontalScrollBar().maximum() == 0
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
