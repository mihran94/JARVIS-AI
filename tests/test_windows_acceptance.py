"""The Windows acceptance checks, run as part of the test suite.

WHAT IS COVERED
    * Every acceptance check that can run without the real Windows
      desktop passes.
    * The checks that need the real Windows desktop are reported as not
      run, never as a pass.
    * The report says which checks ran and which did not.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from core import acceptance
from desktop.app import Window


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope='module')
def window(app, tmp_path_factory):
    base = tmp_path_factory.mktemp('jarvis-acceptance')
    win = Window(base)
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


@pytest.fixture(scope='module')
def checks(window):
    return acceptance.run_all(window)


def test_every_check_that_can_run_here_passes(checks):
    failures = [check for check in checks if check.ran and not check.passed]
    assert not failures, '\n'.join(f'{check.name}: {check.detail}' for check in failures)


def test_the_checks_that_need_windows_are_not_reported_as_passed(checks):
    for check in checks:
        if check.windows_only and not check.ran:
            assert check.status == acceptance.NOT_RUN
            assert check.detail


def test_the_owner_list_is_covered(checks):
    names = {check.requirement for check in checks}
    for wanted in ('One JARVIS window after restart',
                   'Offline Tamil and Tanglish voice',
                   'Saved projects survive a restart',
                   'Approve for me persists',
                   'Calculator shows 391 for 17 × 23 without prompting',
                   'Notepad Save still asks',
                   'A browser draft is reviewable inside Automation',
                   'One routine task stays local',
                   'One task automatically uses Gemini',
                   'Local tasks still work offline',
                   'Related settings are consolidated into one view',
                   'Automation holds the whole surface',
                   'One holographic JARVIS window'):
        assert wanted in names, wanted


def test_the_report_says_what_ran_and_what_did_not(checks):
    text = acceptance.report(checks)
    assert 'Checks run here' in text
    assert 'Passed' in text
    assert 'Failed' in text
    for check in checks:
        assert check.name in text


def test_only_one_window_is_open(window, app):
    assistant = [widget for widget in app.topLevelWidgets()
                 if widget.metaObject().className() == 'Window'
                 and (widget.isVisible() or widget is window)]
    assert len(assistant) == 1
