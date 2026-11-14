"""Create a CapCut Desktop handoff with a video and an editable caption file."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from video_studio.planning import english_srt
from video_studio.preview import render_preview


def export_capcut(plan, clips, destination, check_cancelled, *, narration=None):
    destination = Path(destination).resolve(strict=True)
    output = destination / f"JARVIS-CapCut-{uuid4().hex[:12]}"
    with TemporaryDirectory(prefix=".jarvis-capcut-", dir=destination) as directory:
        package = Path(directory) / "export"
        package.mkdir()
        render_preview(
            plan, clips, package / "video.mp4", check_cancelled,
            narration=narration, burn_captions=False,
        )
        (package / "english.srt").write_text(english_srt(plan), encoding="utf-8")
        check_cancelled()
        package.rename(output)
    return output
