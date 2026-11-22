"""The mission console: what the owner sees while JARVIS works.

WHAT IS COVERED
    * Every step of a mission reaches the rail, in the order it
      happened.
    * The status pill says what the mission is doing, and it says
      "Working" while it runs.
    * The step counter counts the calls that ran. There is no percentage
      and no estimate.
    * The result card appears only when there is a result to show.
    * The evidence line names the tools that really ran, and says so
      when none did.
    * The console paints. A mission that is running has a timeline with
      something on it, not an empty box.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from core.mission import Mission, MissionEvent
from desktop.mission_panel import MissionPanel
from desktop.prime_ui import PrimePalette


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    widget = MissionPanel(PrimePalette(dark=True))
    widget.resize(760, 620)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def event(kind, label, detail=''):
    return MissionEvent(kind=kind, label=label, detail=detail)


def test_the_console_starts_idle(panel):
    assert panel.status.text() == 'READY'
    assert panel.timeline.entries() == []
    assert panel.evidence.text() == ''
    assert panel.answer_card.isVisible() is False


def test_a_running_mission_says_so(panel):
    panel.set_running(True)
    assert panel.status.text() == 'WORKING'
    assert panel.run_button.isEnabled() is False
    assert panel.cancel_button.isEnabled() is True


def test_the_pill_says_when_the_owner_is_being_asked(panel):
    panel.set_running(True)
    panel.set_status('approval')
    assert panel.status.text() == 'APPROVAL NEEDED'
    assert panel.current_status() == 'approval'
    panel.set_status('running')
    assert panel.status.text() == 'WORKING'


def test_every_step_reaches_the_rail_in_order(panel):
    panel.append_event(event('goal', 'Mission started', 'Check the weather.'))
    panel.append_event(event('thought', 'JARVIS decided', 'I need the time first.'))
    panel.append_event(event('tool', 'Calling current_time', 'current_time()'))
    panel.append_event(event('result', 'current_time finished', '2026-11-22 09:00'))
    panel.append_event(event('answer', 'Mission complete', 'It is nine.'))
    kinds = [entry['kind'] for entry in panel.timeline.entries()]
    assert kinds == ['goal', 'thought', 'tool', 'result', 'answer']
    assert panel.timeline.entries()[3]['detail'] == '2026-11-22 09:00'


def test_the_counter_counts_the_calls_that_ran(panel):
    panel.set_counter(0, 6)
    assert panel.counter.text() == 'Step 0 of 6'
    panel.set_counter(2, 6)
    assert panel.counter.text() == 'Step 2 of 6'
    assert '%' not in panel.counter.text()


def test_the_result_card_shows_the_answer(panel):
    mission = Mission(id='m1', goal='Check the time.', status='completed',
                       answer='It is nine in the morning.', steps=2,
                       tools_used=[{'tool': 'current_time', 'summary': 'current_time()',
                                    'result': '09:00'}])
    panel.show_result(mission)
    assert panel.status.text() == 'COMPLETE'
    assert panel.answer.text() == 'It is nine in the morning.'
    assert panel.answer_card.isVisible() is True
    assert 'current_time' in panel.evidence.text()


def test_a_mission_without_a_tool_says_the_evidence_is_empty(panel):
    mission = Mission(id='m2', goal='Say hello.', status='completed', answer='Hello.', steps=1)
    panel.show_result(mission)
    assert 'no tool ran' in panel.evidence.text()


def test_a_failed_mission_says_it_did_not_finish(panel):
    mission = Mission(id='m3', goal='Do something impossible.', status='failed', steps=3)
    panel.show_result(mission)
    assert panel.status.text() == 'FAILED'
    assert 'did not finish' in panel.answer.text()


def test_the_console_paints_what_it_shows(panel):
    panel.append_event(event('goal', 'Mission started', 'Read the notes.'))
    panel.append_event(event('tool', 'Calling memory_search', 'memory_search(query=launch)'))
    panel.append_event(event('result', 'memory_search finished',
                             '- Launch (today)\n  The launch is on Friday.'))
    app = QApplication.instance()
    app.processEvents()
    pixmap = QPixmap(panel.size())
    pixmap.fill()
    panel.render(pixmap)
    image = pixmap.toImage()
    # The rail was drawn: the panel is not an empty rectangle.
    colours = {image.pixel(x, y) for x in range(0, image.width(), 7)
               for y in range(0, image.height(), 7)}
    assert len(colours) > 3
