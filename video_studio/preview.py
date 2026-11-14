"""Assemble user-selected clips into a vertical, subtitled preview."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from video_studio.planning import DURATION_MS, english_srt

FPS = 30
CLIP_EXTENSIONS = {".mp4", ".mov", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


def media_tools():
    tools = [shutil.which(name) for name in ("ffmpeg", "ffprobe")]
    if not all(tools):
        raise ValueError("Install FFmpeg with ffprobe and add both to PATH, then restart JARVIS.")
    return tools


def run_media_command(args, directory, check_cancelled, *, windows_tree=False):
    check_cancelled()
    with subprocess.Popen(
        args, cwd=directory, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        try:
            while True:
                check_cancelled()
                try:
                    output, error = process.communicate(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
                break
        finally:
            if process.poll() is None:
                if windows_tree and os.name == "nt":
                    try:
                        subprocess.run(
                            [os.path.join(os.environ["SystemRoot"], "System32", "taskkill.exe"),
                             "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                if process.poll() is None:
                    process.kill()
                process.communicate()
    check_cancelled()
    if process.returncode:
        detail = error.decode("utf-8", errors="replace").strip().splitlines()
        raise ValueError("Media processing failed. " + (detail[-1][:400] if detail else ""))
    return output


def local_media_path(path, extensions):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in extensions:
        raise ValueError("Select a supported local media file.")
    return path


def render_preview(plan, clips, output, check_cancelled, *, narration=None, burn_captions=True):
    """Trim in shot order, freeze short clips and mix narration."""
    shots = plan["shots"]
    if len(clips) != len(shots):
        raise ValueError("Select exactly one clip for each shot.")
    clips = [local_media_path(path, CLIP_EXTENSIONS) for path in clips]
    narration = local_media_path(narration, AUDIO_EXTENSIONS) if narration else None
    output = Path(output).resolve()
    if output.suffix.lower() != ".mp4" or output in clips or output == narration:
        raise ValueError("Choose a separate .mp4 output file.")

    ffmpeg, ffprobe = media_tools()
    options = ["-protocol_whitelist", "file"]
    # Stage next to the destination to allow atomic replacement on the same volume.
    with TemporaryDirectory(prefix=".jarvis-preview-", dir=output.parent) as directory:
        work = Path(directory)
        if burn_captions:
            (work / "captions.srt").write_text(english_srt(plan), encoding="utf-8")
        args = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-filter_complex_threads", "2"]
        graph = []
        pairs = []
        for index, (clip, shot) in enumerate(zip(clips, shots)):
            streams = json.loads(run_media_command(
                [ffprobe, "-v", "error", *options, "-show_entries", "stream=codec_type",
                 "-of", "json", str(clip)], work, check_cancelled,
            ))["streams"]
            kinds = {stream.get("codec_type") for stream in streams}
            if "video" not in kinds:
                raise ValueError(f"Shot {index + 1} needs a video clip.")
            frames = round(shot["end_ms"] * FPS / 1000) - round(shot["start_ms"] * FPS / 1000)
            duration = f"{frames / FPS:.9f}"
            args.extend(["-threads", "2", *options, "-i", str(clip)])
            graph.append(
                f"[{index}:v:0]fps={FPS},scale=1080:1920:force_original_aspect_ratio=decrease:"
                "force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration={duration},"
                f"trim=end_frame={frames},setpts=PTS-STARTPTS[v{index}]"
            )
            audio = f"[{index}:a:0]aresample=48000,apad" if "audio" in kinds else "anullsrc=r=48000:cl=stereo"
            graph.append(
                f"{audio},aformat=sample_rates=48000:channel_layouts=stereo,"
                f"atrim=end_sample={frames * (48000 // FPS)},asetpts=PTS-STARTPTS[a{index}]"
            )
            pairs.append(f"[v{index}][a{index}]")
        graph.append("".join(pairs) + f"concat=n={len(shots)}:v=1:a=1[video][clipaudio]")
        video_map = "[video]"
        if burn_captions:
            graph.append("[video]subtitles=captions.srt:force_style='Alignment=2,MarginV=36,FontSize=14'[captioned]")
            video_map = "[captioned]"
        audio_map = "[clipaudio]"
        if narration:
            args.extend([*options, "-i", str(narration)])
            graph.extend([
                "[clipaudio]volume=0.20[bed]",
                f"[{len(shots)}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
                "asetpts=PTS-STARTPTS[voice]",
                "[bed][voice]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[mixed]",
            ])
            audio_map = "[mixed]"
        staged = work / "preview.mp4"
        run_media_command(
            [*args, "-filter_complex", ";".join(graph), "-map", video_map, "-map", audio_map,
             "-t", str(DURATION_MS / 1000), "-c:v", "libx264", "-threads", "4", "-preset", "veryfast",
             "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(staged)],
            work, check_cancelled,
        )
        check_cancelled()
        os.replace(staged, output)
    return output
