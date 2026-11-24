"""The creative adapters and the media they are checked against.

WHAT IS COVERED
    * The Photoshop script holds the calls for the edits that are
      supported, and an edit that is not supported is refused.
    * The After Effects script holds the calls for the changes that are
      supported, and a change that is not supported is refused.
    * The Resolve script renders a timeline and names the file it
      writes.
    * An application that is not installed is reported as missing, not
      as a broken edit.
    * A real rendered file is verified: its length, its picture and its
      sound.
    * A file that is empty, is not media, is shorter than it should be,
      or has no picture in it, is caught.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shutil
import subprocess

import pytest

from video_studio.creative import (
    CreativeError, after_effects_available, after_effects_script,
    photoshop_available, photoshop_script, resolve_available, resolve_script,
    resolve_script_path, run_photoshop,
)
from video_studio.verification import (
    MediaVerificationError, ffprobe_executable, probe, verify_media,
)

HAS_FFPROBE = shutil.which('ffprobe') is not None
needs_probe = pytest.mark.skipif(not HAS_FFPROBE, reason='ffprobe is not installed here.')


def render(path, *, seconds=2, size='320x240', sound=True, picture=True):
    """A real media file, made here with FFmpeg."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg is not installed here.')
    command = [ffmpeg, '-y']
    if picture:
        command += ['-f', 'lavfi', '-i',
                    f'testsrc=duration={seconds}:size={size}:rate=10']
    if sound:
        command += ['-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}']
    command += [str(path)]
    result = subprocess.run(command, capture_output=True, timeout=180, check=False)
    if result.returncode != 0:
        pytest.skip('FFmpeg could not make the file here.')
    return path


# ── the scripts ────────────────────────────────────────────────────────────

def test_the_photoshop_script_holds_the_edits():
    script = photoshop_script([
        {'action': 'resize', 'width': 800, 'height': 600},
        {'action': 'crop', 'width': 400, 'height': 300},
        {'action': 'rotate', 'degrees': 90},
        {'action': 'levels', 'black': 10, 'white': 240},
        {'action': 'convert', 'format': 'jpeg', 'path': 'C:/out.jpg'},
    ])
    assert script.startswith('#target photoshop')
    assert 'var w = 800; var h = 600;' in script
    assert 'resizeImage(UnitValue(w,"px"), UnitValue(h,"px"), 72)' in script
    assert 'crop(UnitValue(w,"px")' in script
    assert 'rotate(90)' in script
    assert 'adjustLevels(10, 240, 1)' in script
    assert 'new JPEGOptions()' in script
    assert 'saveAs(out, options' in script


def test_a_photoshop_edit_that_is_not_supported_is_refused():
    with pytest.raises(CreativeError) as error:
        photoshop_script([{'action': 'apply_a_neural_filter'}])
    assert 'resize, crop, rotate, levels, convert and save' in str(error.value)


def test_a_photoshop_format_that_is_not_supported_is_refused():
    with pytest.raises(CreativeError):
        photoshop_script([{'action': 'convert', 'format': 'raw', 'path': 'C:/out.raw'}])


def test_a_name_with_a_quote_does_not_break_the_script():
    script = photoshop_script([{'action': 'save', 'path': 'C:/the "file".png'}])
    assert '\\"file\\"' in script


def test_the_after_effects_script_holds_the_changes():
    script = after_effects_script([
        {'action': 'rename', 'from': 'Main Comp', 'to': 'Final Comp'},
        {'action': 'frame_rate', 'fps': 30},
        {'action': 'add_text', 'composition': 'Final Comp', 'text': 'Launch'},
    ])
    assert 'project.items.getItemByName("Main Comp")' in script
    assert 'item.name = "Final Comp"' in script
    assert 'item.frameRate = rate' in script
    assert 'comp.layers.addText("Launch")' in script


def test_an_after_effects_change_that_is_not_supported_is_refused():
    with pytest.raises(CreativeError) as error:
        after_effects_script([{'action': 'render_3d'}])
    assert 'rename, frame rate and add text' in str(error.value)


def test_the_resolve_script_renders_the_timeline():
    script = resolve_script('Timeline 1', 'C:/out.mp4', settings={'width': 1280,
                                                                   'height': 720})
    assert 'DaVinciResolveScript' in script
    assert "name = 'Timeline 1'" in script
    assert "target = 'C:\\\\out.mp4'" in script or "target = 'C:/out.mp4'" in script
    assert 'AddRenderJob' in script
    assert 'IsRenderingInProgress' in script


def test_a_timeline_that_is_not_named_is_refused():
    with pytest.raises(CreativeError):
        resolve_script('   ', 'C:/out.mp4')


# ── the applications ───────────────────────────────────────────────────────

def test_an_application_that_is_not_there_is_reported_as_missing():
    # None of the three applications is installed on this machine, and
    # saying so is the honest answer.
    if photoshop_available():
        pytest.skip('Photoshop is installed here.')
    with pytest.raises(CreativeError) as error:
        run_photoshop('/nowhere/Photoshop.exe', [{'action': 'save', 'path': '/tmp/x.png'}],
                      '/tmp/x.png')
    assert 'Photoshop.exe' in str(error.value)


def test_resolve_says_when_it_cannot_be_scripted():
    if resolve_available():
        pytest.skip('Resolve is installed here.')
    assert resolve_script_path() == ''
    assert resolve_available() is False


def test_the_applications_are_detected_without_raising():
    for check in (photoshop_available, after_effects_available, resolve_available):
        assert check() in (True, False)


# ── the media check ────────────────────────────────────────────────────────

@needs_probe
def test_a_real_render_is_verified(tmp_path):
    path = render(tmp_path / 'clip.mp4', seconds=2)
    result = verify_media(path, expect_duration=2)
    assert result.ok is True, result.message
    assert result.info.has_video is True
    assert result.info.has_audio is True
    assert result.info.width == 320
    assert result.info.height == 240
    assert 'real' in result.message


@needs_probe
def test_a_file_that_was_not_produced_is_caught(tmp_path):
    result = verify_media(tmp_path / 'nothing.mp4')
    assert result.ok is False
    assert 'not produced' in result.message


@needs_probe
def test_a_file_with_nothing_in_it_is_caught(tmp_path):
    path = tmp_path / 'empty.mp4'
    path.write_bytes(b'')
    result = verify_media(path)
    assert result.ok is False
    assert any('bytes' in problem for problem in result.problems)


@needs_probe
def test_a_file_that_is_not_media_is_caught(tmp_path):
    path = tmp_path / 'notes.mp4'
    path.write_bytes(b'this is a note, not a video' * 200)
    result = verify_media(path)
    assert result.ok is False
    assert any('not media' in problem for problem in result.problems)


@needs_probe
def test_a_file_that_is_too_short_is_caught(tmp_path):
    path = render(tmp_path / 'clip.mp4', seconds=2)
    result = verify_media(path, expect_duration=30)
    assert result.ok is False
    assert any('seconds were asked for' in problem for problem in result.problems)


@needs_probe
def test_a_file_without_a_picture_is_caught(tmp_path):
    path = render(tmp_path / 'sound.m4a', seconds=1, sound=True, picture=False)
    # A sound-only render is fine when no picture was asked for, and a
    # problem when one was.
    assert verify_media(path, expect_video=False, expect_audio=True).ok is True
    assert verify_media(path, expect_video=True).ok is False


@needs_probe
def test_what_is_inside_a_file_can_be_asked(tmp_path):
    path = render(tmp_path / 'clip.mp4', seconds=1)
    info = probe(path)
    assert info.exists is True
    assert info.bytes > 0
    assert info.has_video is True
    assert info.duration > 0


def test_the_probe_says_what_to_install_when_it_is_missing(monkeypatch):
    monkeypatch.setattr('video_studio.verification.shutil.which', lambda name: None)
    with pytest.raises(MediaVerificationError) as error:
        ffprobe_executable()
    assert 'FFmpeg' in str(error.value)
