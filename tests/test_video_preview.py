"""Exercise the real FFmpeg preview pipeline and preservation on cancellation."""
import json
from shutil import which
import subprocess

import pytest

from security.policy import Stopped
from video_studio.preview import render_preview

pytestmark = pytest.mark.skipif(
    not (which("ffmpeg") and which("ffprobe")), reason="FFmpeg and ffprobe are required")


def test_vertical_preview_with_audio_and_captions(tmp_path):
    capabilities = subprocess.check_output(["ffmpeg", "-hide_banner", "-filters"], text=True)
    if " subtitles " not in capabilities:
        pytest.skip("FFmpeg lacks libass subtitles")
    paths = []
    for index, color in enumerate(("red", "green", "blue", "yellow")):
        path = tmp_path / f"clip {index}.mp4"
        args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color={color}:s=144x100:d=1"]
        if index == 0:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
        subprocess.run([*args, "-c:v", "libx264", str(path)], check=True)
        paths.append(path)
    narration = tmp_path / "Tamil narration.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=880:duration=3", str(narration)], check=True)
    boundaries = [0, 6750, 15_000, 23_000, 30_000]
    plan = {"shots": [
        {"start_ms": start, "end_ms": end, "english_subtitle": "Hello from AI Mystery World"}
        for start, end in zip(boundaries, boundaries[1:])
    ]}
    output = tmp_path / "vertical preview.mp4"
    assert render_preview(plan, paths, output, lambda: None, narration=narration) == output
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)
    ]))
    video, audio = probe["streams"]
    assert (video["width"], video["height"], video["codec_name"]) == (1080, 1920, "h264")
    assert int(video["nb_frames"]) == 900
    assert audio["codec_name"] == "aac"
    assert float(probe["format"]["duration"]) == pytest.approx(30, abs=0.04)
    # The letterbox at the bottom is black except for the burned-in English caption.
    frame = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(output), "-frames:v", "1",
        "-vf", "crop=1080:300:0:1500,format=gray", "-f", "rawvideo", "-"
    ])
    assert max(frame) > 180

    original = output.read_bytes()

    def cancel():
        raise Stopped("Cancelled")

    with pytest.raises(Stopped):
        render_preview(plan, paths, output, cancel)
    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".jarvis-preview-*"))


def test_capcut_exports_separate_editable_captions(tmp_path):
    from video_studio.capcut import export_capcut

    clip = tmp_path / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=144x100:d=1",
        "-c:v", "libx264", str(clip),
    ], check=True)
    plan = {"shots": [{"start_ms": 0, "end_ms": 30000, "english_subtitle": "Editable caption"}]}
    folder = export_capcut(plan, [clip], tmp_path, lambda: None)
    assert (folder / "english.srt").read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:30,000\nEditable caption\n")
    frame = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(folder / "video.mp4"),
        "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-",
    ])
    assert frame and max(frame) == 0
    assert not list(tmp_path.glob(".jarvis-capcut-*"))
