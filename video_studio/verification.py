"""Checking that a rendered file is really the media it claims to be.

WHAT THIS IS
    "The export finished" is not the same as "the export is good". This
    reads the file that was produced and says what is actually inside
    it: how long it is, how big the picture is, whether it has a sound
    track, and whether that is what was asked for.

    It is the check that stands between a finished render and a
    successful one. A file of zero bytes, a file that is not media at
    all, a file that is shorter than the plan asked for, and a file with
    no picture in it are all things that can happen, and all of them
    are caught here.

WHAT THIS IS NOT
    * It does not judge the content. It measures it.
    * It does not need a network, and it does not upload anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

#: How much the real duration may differ from the expected one.
DURATION_TOLERANCE = 0.5

#: The shortest a file may be and still count as media.
MIN_MEDIA_BYTES = 1024


class MediaVerificationError(RuntimeError):
    """The file could not be checked."""


@dataclass
class MediaInfo:
    """What is really inside a media file."""

    path: str = ''
    exists: bool = False
    bytes: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    has_video: bool = False
    has_audio: bool = False
    codec: str = ''
    format_name: str = ''

    def as_dict(self) -> dict:
        return {'path': self.path, 'exists': self.exists, 'bytes': self.bytes,
                'duration': self.duration, 'width': self.width, 'height': self.height,
                'has_video': self.has_video, 'has_audio': self.has_audio,
                'codec': self.codec, 'format_name': self.format_name}


@dataclass
class Verification:
    """The outcome of checking a file."""

    ok: bool = False
    info: MediaInfo = field(default_factory=MediaInfo)
    problems: list = field(default_factory=list)
    message: str = ''

    def as_dict(self) -> dict:
        return {'ok': self.ok, 'info': self.info.as_dict(),
                'problems': list(self.problems), 'message': self.message}


def ffprobe_executable() -> str:
    """The probe, or a sentence saying what to install."""
    found = shutil.which('ffprobe')
    if found:
        return found
    raise MediaVerificationError(
        'FFmpeg with ffprobe is needed to check a rendered file. Install FFmpeg, '
        'add it to the PATH and restart JARVIS.')


def probe(path) -> MediaInfo:
    """What is really inside a media file."""
    source = Path(path)
    info = MediaInfo(path=str(source), exists=source.is_file())
    if not info.exists:
        return info
    try:
        info.bytes = source.stat().st_size
    except OSError:
        return info
    try:
        executable = ffprobe_executable()
    except MediaVerificationError:
        return info
    try:
        result = subprocess.run(
            [executable, '-v', 'error', '-print_format', 'json', '-show_format',
             '-show_streams', str(source)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return info
    if result.returncode != 0:
        return info
    import json

    try:
        data = json.loads(result.stdout or '{}')
    except ValueError:
        return info
    fmt = data.get('format') or {}
    info.format_name = str(fmt.get('format_name', ''))
    try:
        info.duration = float(fmt.get('duration', 0) or 0)
    except (TypeError, ValueError):
        info.duration = 0.0
    for stream in data.get('streams') or []:
        kind = stream.get('codec_type')
        if kind == 'video' and not (stream.get('disposition') or {}).get('attached_pic'):
            info.has_video = True
            info.width = int(stream.get('width', 0) or 0)
            info.height = int(stream.get('height', 0) or 0)
            info.codec = str(stream.get('codec_name', ''))
        elif kind == 'audio':
            info.has_audio = True
    return info


def verify_media(path, *, expect_duration=None, expect_video=True,
                 expect_audio=None) -> Verification:
    """Check that a rendered file is the media it was asked to be.

    The checks are the ones that catch a broken render: a file that is
    not there, a file with nothing in it, a file that is not media, a
    file that is shorter than the plan asked for, and a file with no
    picture in it.
    """
    result = Verification()
    source = Path(path)
    result.info = probe(source)
    info = result.info

    if not info.exists:
        result.problems.append('The file was not produced.')
        result.message = 'The file was not produced.'
        return result
    if info.bytes < MIN_MEDIA_BYTES:
        result.problems.append(f'The file holds only {info.bytes:,} bytes.')
    if not info.has_video and not info.has_audio:
        result.problems.append('The file is not media that anything can play.')

    if expect_video and not info.has_video:
        result.problems.append('The file has no picture in it.')
    if expect_audio is True and not info.has_audio:
        result.problems.append('The file has no sound in it.')
    if expect_audio is False and info.has_audio:
        result.problems.append('The file has sound in it, but none was asked for.')
    if expect_duration:
        difference = abs(info.duration - float(expect_duration))
        if difference > DURATION_TOLERANCE:
            result.problems.append(
                f'The file is {info.duration:.1f} seconds long, and '
                f'{float(expect_duration):.1f} seconds were asked for.')

    if result.problems:
        result.ok = False
        result.message = 'The render did not come out right: ' + '; '.join(result.problems)
        return result

    result.ok = True
    shape = f'{info.width}x{info.height}' if info.has_video else 'sound only'
    sound = ' with sound' if info.has_audio else ''
    result.message = (f'The file is real: {shape}{sound}, {info.duration:.1f} seconds, '
                       f'{info.bytes:,} bytes.')
    return result


__all__ = ['DURATION_TOLERANCE', 'MIN_MEDIA_BYTES', 'MediaInfo', 'MediaVerificationError',
           'Verification', 'ffprobe_executable', 'probe', 'verify_media']
