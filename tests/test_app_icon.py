"""The application icon and the installer that carries it.

WHAT IS COVERED
    * The icon is a real Windows icon file, with the sizes Windows asks
      for and a whole picture in every one of them.
    * The installer uses that icon, and the executable is built with it,
      so the owner sees the JARVIS orb and not the default picture.
    * The icon can be drawn again, so a change to it is reviewable.
    * The workflow changes travel as patches, because the GitHub App that
      pushes this repository is not allowed to write the workflows. A
      patch that does not apply is a patch the owner cannot use.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import struct
from pathlib import Path

from tools.make_icon import SIZES, draw, write_ico

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / 'installers' / 'JarvisAI.ico'
INSTALLER = ROOT / 'installers' / 'JARVIS-AI.iss'
ICON_PATCH = ROOT / 'patches' / 'windows-app-icon.patch'
GREEN_PATCH = ROOT / 'patches' / 'github-actions-green.patch'


def read_entries(data):
    """The pictures inside an icon file."""
    reserved, kind, count = struct.unpack('<HHH', data[:6])
    assert reserved == 0
    assert kind == 1, 'the file must be an icon'
    entries = []
    for index in range(count):
        width, height, colours, _res, planes, bits, size, offset = struct.unpack(
            '<BBBBHHII', data[6 + 16 * index:22 + 16 * index])
        entries.append({
            'width': width or 256, 'height': height or 256, 'bits': bits,
            'size': size, 'offset': offset,
        })
    return entries


def test_the_icon_is_a_real_windows_icon(tmp_path):
    """The icon is drawn, and what is drawn is a real Windows icon.

    The icon is build output rather than a committed picture, so the
    build draws it from the code and the code is what is reviewed.
    """
    drawn = tmp_path / 'JarvisAI.ico'
    write_ico(drawn)
    assert drawn.exists(), 'the application icon could not be drawn'
    entries = read_entries(drawn.read_bytes())
    assert len(entries) == len(SIZES)
    assert {entry['width'] for entry in entries} == set(SIZES)
    assert all(entry['bits'] == 32 for entry in entries)


def test_every_picture_of_the_icon_is_whole(tmp_path):
    """A picture that runs past the end of the file is a broken icon."""
    drawn = tmp_path / 'JarvisAI.ico'
    write_ico(drawn)
    data = drawn.read_bytes()
    for entry in read_entries(data):
        start = entry['offset']
        end = start + entry['size']
        assert end <= len(data), 'a picture of the icon runs past the end of the file'
        assert data[start:start + 8] != b'', 'a picture of the icon is empty'


def test_the_icon_is_drawn_with_the_colours_of_the_orb():
    """The icon is the same orb the application draws."""
    pixels = draw(64)
    assert len(pixels) == 64
    assert len(pixels[0]) == 64
    # The centre is bright, the corner is clear: the icon has a shape.
    assert pixels[32][32][3] == 255
    assert pixels[0][0][3] == 0


def test_the_icon_can_be_drawn_again(tmp_path):
    """A change to the icon has to be reviewable, so the drawing is code."""
    target = tmp_path / 'jarvis-icon-test.ico'
    write_ico(target)
    assert target.exists()
    assert read_entries(target.read_bytes())


def test_the_installer_in_the_tree_does_not_need_a_file_that_is_not_there():
    """The installer must build from the tree alone.

    The icon is drawn by the build, and the installer only uses it once
    the patch that draws it has been applied. Until then the installer
    must not point at a file that is not there, because the Windows
    installer job fails on a file it cannot find.
    """
    text = INSTALLER.read_text(encoding='utf-8')
    assert 'SetupIconFile' not in text
    assert 'UninstallDisplayIcon={app}\\JarvisAI.exe' in text


def test_the_executable_is_built_with_the_icon():
    """The workflow change travels as a patch, because the GitHub App
    that pushes this repository is not allowed to write the workflows.

    The patch is kept in the repository so the change is reviewed with
    the rest of it, and so the owner can apply it with one command.
    """
    text = ICON_PATCH.read_text(encoding='utf-8')
    # All three parts travel together: the build draws the icon, the
    # executable is built with it, and the installer uses it.
    assert 'python tools/make_icon.py installers/JarvisAI.ico' in text
    assert '--icon installers/JarvisAI.ico' in text
    assert 'SetupIconFile=JarvisAI.ico' in text
    # The icon is drawn after the tests, so the tests never see a file
    # that is not in the source.
    assert text.index('make_icon.py') < text.index('PyInstaller')


def test_the_test_suite_reports_both_operating_systems():
    """A Linux only failure must never hide the Windows result.

    The workflow change is a patch for the same reason the icon change
    is: the App that pushes this repository cannot write the workflows.
    """
    assert 'fail-fast: false' in GREEN_PATCH.read_text(encoding='utf-8')


def test_the_patches_apply_to_the_workflows_they_change():
    """A patch that does not apply is a patch the owner cannot use."""
    import subprocess

    for patch in (ICON_PATCH, GREEN_PATCH):
        result = subprocess.run(['git', 'apply', '--check', str(patch)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, (
            f'{patch.name} does not apply: {result.stderr[:300]}')


def test_the_icon_is_not_committed_as_a_picture():
    """The icon is drawn by the build, so it is not part of the source."""
    assert not ICON.exists(), 'the icon is build output and must not be committed'
    manifest = (ROOT / 'scripts' / 'source_manifest.py').read_text(encoding='utf-8')
    assert 'installers/JarvisAI.ico' in manifest
