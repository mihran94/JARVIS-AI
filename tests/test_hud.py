"""The holographic HUD: the readings that are always in sight.

WHAT IS COVERED
    * The HUD says which engine answered, and why.
    * A reading that is there is shown; a reading that is not there is
      shown as unavailable, never as a made-up number.
    * The step of the task is shown, and there is no invented
      percentage.
    * An approval that is waiting is visible, and it goes away when the
      approval is answered.
    * The state of the microphone and the mute are visible.
    * Emergency Stop is always there, and it says what it does.
    * The Tamil is drawn with the Tamil font of Windows.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from desktop.hud import TAMIL_STACK, HudDial, HudFrame, HudStrip


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

def test_the_engine_that_answered_is_shown(app):
    strip = HudStrip()
    strip.set_engine('Local', '')
    assert strip.engine_chip.text() == 'Local'
    strip.set_engine('Gemini', 'The on-device model could not complete this step.')
    assert strip.engine_chip.text() == 'Gemini'
    assert 'could not complete' in strip.engine_note.text()
    assert strip.engine_note.isVisible() is False  # not shown until the strip is


def test_a_reading_that_is_there_is_shown(app):
    dial = HudDial('CPU')
    dial.set_reading(0.42, '42%')
    assert dial.value == pytest.approx(0.42)
    assert dial.text == '42%'


def test_a_reading_that_is_not_there_is_not_made_up(app):
    dial = HudDial('CPU')
    dial.set_reading(None, '—')
    assert dial.value is None
    assert dial.text == '—'


def test_the_step_of_the_task_is_shown(app):
    strip = HudStrip()
    strip.set_progress(2, 6)
    assert strip.task_label.text() == 'Step 2 of 6'
    assert strip.progress.value() == 33


def test_no_task_means_no_step(app):
    strip = HudStrip()
    strip.set_progress(0, 0)
    assert strip.task_label.text() == 'No task running'
    assert strip.progress.value() == 0


def test_an_approval_that_is_waiting_is_visible(app):
    strip = HudStrip()
    strip.set_approval('Approval needed: mission_tool')
    assert 'Approval needed' in strip.approval.text()
    strip.clear_approval()
    assert strip.approval.text() == ''


def test_the_microphone_and_the_mute_are_visible(app):
    strip = HudStrip()
    strip.set_mic('The microphone is allowed for the voice feature.', False)
    assert 'allowed' in strip.mic.text()
    assert strip.mute.text() == 'Replies on'
    strip.set_mic('The microphone is allowed for the voice feature.', True)
    assert strip.mute.text() == 'Replies muted'


def test_the_emergency_stop_says_what_it_does(app):
    strip = HudStrip()
    assert strip.stop_button.text() == 'Emergency stop'
    assert strip.stop_button.accessibleName() == 'Emergency stop'


def test_the_emergency_stop_asks_the_window_to_stop(app):
    strip = HudStrip()
    asked = []
    strip.stop_requested.connect(lambda: asked.append(True))
    strip.stop_button.click()
    assert asked == [True]


def test_the_summary_names_everything_the_hud_shows(app):
    strip = HudStrip()
    strip.set_engine('Gemini', 'because of a step')
    strip.set_reading('cpu', 0.5, '50%')
    strip.set_reading('ram', None, '—')
    strip.set_progress(1, 4)
    strip.set_mic('The microphone has not been allowed.', True)
    summary = strip.summary()
    assert 'Gemini' in summary
    assert 'CPU 50%' in summary
    assert 'RAM —' in summary
    assert 'step 1 of 4' in summary
    assert 'muted' in summary


def test_the_tamil_font_of_windows_is_named():
    assert 'Nirmala UI' in TAMIL_STACK


def test_the_status_strip_uses_no_legacy_reactor(app):
    frame = HudFrame()
    assert frame.findChild(QWidget, 'hudCore') is None
