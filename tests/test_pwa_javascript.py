"""The JavaScript of the iPhone page, run from the Python suite.

The GitHub Actions recipe runs pytest, so the node suite is started from
here. One command then covers both halves of the project, and the phone code
cannot rot unnoticed on the runner.

The tests themselves live in `iphone-pwa/tests/`.
"""
import os
import re
import shutil
import subprocess

import pytest

PWA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'iphone-pwa')

#: How long the phone suite may take.
TIMEOUT_SECONDS = 600

#: The number of JavaScript tests that have to run. A lower number means that
#: a file was not found, and that must not pass unnoticed.
EXPECTED_TESTS = 64


def node_binary():
    """The node program, or None when the machine has none."""
    return shutil.which('node')


@pytest.mark.skipif(node_binary() is None, reason='node is not installed on this machine')
def test_the_phone_javascript_suite_passes():
    completed = subprocess.run([node_binary(), '--test'], cwd=PWA, capture_output=True,
                               text=True, timeout=TIMEOUT_SECONDS)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-6000:]
    # Newer node prints "pass 64" with a different prefix than the older
    # "# pass 64", so both forms are accepted.
    passed = re.search(r'(?:^#|^\u2139)\s*pass (\d+)$', output, re.M)
    assert passed is not None, output[-2000:]
    assert int(passed.group(1)) >= EXPECTED_TESTS, output[-2000:]


@pytest.mark.skipif(node_binary() is None, reason='node is not installed on this machine')
def test_the_phone_page_has_no_syntax_error():
    """Every file the browser loads has to parse."""
    files = ['app.js', 'sw.js', 'js/bridge.js', 'js/chat.js', 'js/offline.js',
             'js/pairing.js', 'js/qr.js', 'js/speech.js']
    for name in files:
        path = os.path.join(PWA, name)
        assert os.path.exists(path), 'The phone page is missing ' + name
        completed = subprocess.run([node_binary(), '--check', path], capture_output=True,
                                   text=True, timeout=120)
        assert completed.returncode == 0, name + ': ' + completed.stderr


def test_the_icons_are_written_again_from_their_sidecars(tmp_path):
    """The pictures travel as text, and the script writes them again."""
    import importlib.util
    import shutil as shutil_module

    script = os.path.join(PWA, 'icons', 'restore-icons.py')
    assert os.path.exists(script)
    spec = importlib.util.spec_from_file_location('restore_icons', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in module.ICONS:
        shutil_module.copy(os.path.join(PWA, 'icons', name + '.b64'),
                           os.path.join(tmp_path, name + '.b64'))
    written = module.restore(str(tmp_path))
    assert len(written) == len(module.ICONS)
    for name, expected in module.ICONS.items():
        assert module.png_size(os.path.join(tmp_path, name)) == expected


@pytest.mark.skipif(node_binary() is None, reason='node is not installed on this machine')
def test_the_phone_page_points_at_files_that_exist():
    """Every file the page and the worker refer to has to be there."""
    with open(os.path.join(PWA, 'index.html'), encoding='utf-8') as handle:
        page = handle.read()
    for name in ['./manifest.webmanifest', './style.css', './app.js']:
        assert name in page, 'The page does not refer to ' + name
        assert os.path.exists(os.path.join(PWA, name.lstrip('./'))), name + ' is missing'
    # The picture itself is written by the restore script from its sidecar.
    assert './icons/icon-180.png' in page
    assert os.path.exists(os.path.join(PWA, 'icons', 'icon-180.png.b64'))
    with open(os.path.join(PWA, 'sw.js'), encoding='utf-8') as handle:
        worker = handle.read()
    for name in ['./app.js', './style.css', './manifest.webmanifest', './js/bridge.js']:
        assert name in worker, 'The service worker does not cache ' + name
        assert os.path.exists(os.path.join(PWA, name.lstrip('./'))), name + ' is missing'
