"""Editing checklists and handoff packages for CapCut and DaVinci Resolve.

WHAT THIS IS
    The shot plan tells the editor what to make. This tells the editor what to
    DO with what was made: which clip goes where, how long it should be, what
    the camera, lighting and sound cues were, and what the English subtitle
    says for that shot.

WHY TWO CHECKLISTS
    CapCut and DaVinci Resolve are different tools with different habits. A
    checklist that mixed the two would send the editor to the wrong menu. So
    each tool gets its own steps, in its own order, and both are built from
    the same plan.

WHAT IS ESTIMATED AND WHAT IS NOT
    The timings come from the plan. The plan was written before the voiceover
    was recorded, so the caption timings are an ESTIMATE and the checklist says
    so, in the place where the editor will read it. Nothing here claims the
    captions are frame-accurate against a recording that does not exist yet.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from video_studio.planning import NOT_SPECIFIED, english_srt, plan_engine, prompt_sheet
from video_studio.preview import render_preview


#: The two editors the handoff is written for.
EDITORS = ('CapCut Desktop', 'DaVinci Resolve')

#: The file name a generated clip should be given.
def clip_name(number):
    """The name a generated clip should be given, so the edit can find it."""
    return f"shot-{number:02d}.mp4"


def _value(shot, name):
    return shot.get(name) or NOT_SPECIFIED


def shot_checklist(plan):
    """The per-shot checklist: clip, length, camera, lighting, sound, subtitle."""
    lines = []
    for number, shot in enumerate(plan["shots"], 1):
        length = f"{(shot['end_ms'] - shot['start_ms']) / 1000:.1f} s"
        lines.extend([
            f"Shot {number}  ·  target length {length}  ·  clip {clip_name(number)}",
            f"  [ ] Camera: {_value(shot, 'camera')}",
            f"  [ ] Lighting: {_value(shot, 'lighting')}",
            f"  [ ] Sound cue: {_value(shot, 'sound')}",
            f"  [ ] English subtitle: {shot['english_subtitle'] or '(silent shot)'}",
            f"  [ ] Edit and sound: {shot['edit_and_sound']}",
        ])
    return "\n".join(lines)


def capcut_checklist(plan):
    """The CapCut Desktop steps."""
    return "\n".join([
        "CapCut Desktop",
        f"  [ ] Import video.mp4 and english.srt into the SAME project.",
        "  [ ] Set the canvas to 9:16, 1080 x 1920, 30 fps.",
        "  [ ] Add english.srt as a caption track and check every line against the voiceover.",
        "  [ ] Keep the narration above the ambience; duck the music under it.",
        "  [ ] Trim each clip to the shot length listed above.",
        "  [ ] Export H.264 at 1080 x 1920.",
    ])


def davinci_checklist(plan):
    """The DaVinci Resolve steps."""
    return "\n".join([
        "DaVinci Resolve",
        "  [ ] Import video.mp4 into the media pool.",
        "  [ ] Create a 1080 x 1920, 30 fps timeline and lay the clips down in shot order.",
        "  [ ] Import english.srt onto a track above the video, then check the timings.",
        "  [ ] In Fairlight, duck the music under the narration.",
        "  [ ] Trim each clip to the shot length listed above.",
        "  [ ] Deliver H.264 at 1080 x 1920.",
        "  [ ] Build the timeline by hand. JARVIS hands over the MP4, the English SRT and",
        "      this checklist, not a Resolve XML timeline.",
    ])


def editing_checklist(plan):
    """The whole checklist: prepare, every shot, then each editor."""
    title = plan.get("title", "Reel")
    lines = [
        f"{title} — editing checklist",
        f"30 seconds · {plan.get('width', 1080)} x {plan.get('height', 1920)} · "
        f"{plan.get('engine', 'Google Flow')}",
        "",
        "ESTIMATED TIMINGS — the caption times come from the plan, not from a recorded",
        "voiceover. Check every caption against the recording before you deliver.",
    ]
    if not plan.get("detailed", False):
        lines.extend(["",
                      "PARTIAL PLAN — some fields were not supplied by the model and are",
                      "marked " + NOT_SPECIFIED + "."])
    lines.extend([
        "",
        "Prepare",
        "  [ ] Generate one clip per shot and name it as listed below.",
        "  [ ] Record the Tamil voiceover as one track.",
        "",
        "Shots",
        shot_checklist(plan),
        "",
        capcut_checklist(plan),
        "",
        davinci_checklist(plan),
    ])
    return "\n".join(lines)


def export_davinci(plan, clips, destination, check_cancelled, *, narration=None):
    """A DaVinci Resolve handoff: the assembled video, the captions and the checklist.

    Resolve reads an SRT directly, so the same caption file that CapCut uses
    is handed over here too. The timeline itself is not written: Resolve's own
    XML is a format this project does not produce, and a hand-written one that
    Resolve silently ignored would be worse than a checklist. The checklist
    says exactly where every clip goes.
    """
    destination = Path(destination).resolve(strict=True)
    output = destination / f"JARVIS-DaVinci-{uuid4().hex[:12]}"
    with TemporaryDirectory(prefix=".jarvis-davinci-", dir=destination) as directory:
        package = Path(directory) / "export"
        package.mkdir()
        render_preview(
            plan, clips, package / "video.mp4", check_cancelled,
            narration=narration, burn_captions=False,
        )
        (package / "english.srt").write_text(english_srt(plan), encoding="utf-8")
        (package / "editing-checklist.txt").write_text(editing_checklist(plan), encoding="utf-8")
        (package / "shot-prompts.txt").write_text(
            prompt_sheet(plan, plan_engine(plan)), encoding="utf-8")
        check_cancelled()
        package.rename(output)
    return output
