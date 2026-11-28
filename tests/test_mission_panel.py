"""The mission console: the Command Deck the owner sees while JARVIS works.

WHAT IS COVERED
    * Every step of a mission reaches the rail, in the order it
      happened.
    * The status pill says what the mission is doing, and it says
      "Working" while it runs and "Approval needed" while it waits.
    * The step counter counts the calls that ran. There is no percentage
      and no estimate.
    * The approval banner appears while the owner is being asked, and it
      goes away when the step is over.
    * The evidence column names the tools that really ran, and says so
      when none did.
    * The answer column carries the answer, and says that the mission
      did not finish when it did not.
    * The readings on the left are real, and a reading that cannot be
      taken is shown as unavailable rather than as a number.
    * The console paints. A mission that is running has a timeline with
      something on it, not an empty box.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from core.mission import BUDGET_SECONDS, MAX_STEPS, Mission, MissionEvent
from desktop.mission_panel import GaugeRing, MissionPanel, TelemetryColumn
from desktop.prime_ui import PrimePalette


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    widget = MissionPanel(PrimePalette(dark=True))
    widget.resize(1180, 760)
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
    assert panel.evidence_column.count.text() == 'no tool ran'
    assert panel.evidence_column.answer.text() == 'No mission has run yet.'


def test_the_default_run_limit_label_matches_the_runtime_budget(panel):
    assert panel.run_limit.currentData() == (MAX_STEPS, BUDGET_SECONDS)
    assert panel.run_limit.currentText() == f'{MAX_STEPS} steps · {BUDGET_SECONDS // 60} min'
    assert [(panel.run_limit.itemText(index), panel.run_limit.itemData(index)) for index in (1, 2)] == [
        ('12 steps · 6 min', (12, 360)),
        ('24 steps · 12 min', (24, 720)),
    ]


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


def test_the_goal_is_shown_in_the_centre(panel):
    panel.set_goal('Find the launch date')
    assert panel.title.text() == 'Find the launch date'


def test_the_counter_counts_the_calls_that_ran(panel):
    panel.set_counter(0, 6)
    assert panel.counter.text() == 'Step 0 of 6'
    panel.set_counter(2, 6)
    assert panel.counter.text() == 'Step 2 of 6'
    assert '%' not in panel.counter.text()


def test_the_approval_banner_appears_and_goes_away(panel):
    panel.append_event(event('approval', 'Approval needed',
                             'memory_remember(title=Launch)'))
    assert panel.approval.isVisible() is True
    assert 'memory_remember' in panel.approval_detail.text()
    panel.append_event(event('result', 'memory_remember finished', 'Saved.'))
    assert panel.approval.isVisible() is False


def test_the_answer_and_the_evidence_are_shown(panel):
    mission = Mission(id='m1', goal='Check the time.', status='completed',
                       answer='It is nine in the morning.', steps=2,
                       tools_used=[{'tool': 'current_time', 'summary': 'current_time()',
                                    'result': '09:00'}])
    panel.show_result(mission)
    assert panel.status.text() == 'COMPLETE'
    assert panel.evidence_column.answer.text() == 'It is nine in the morning.'
    assert 'tool result' in panel.evidence_column.count.text()


def test_a_mission_without_a_tool_says_the_evidence_is_empty(panel):
    mission = Mission(id='m2', goal='Say hello.', status='completed', answer='Hello.', steps=1)
    panel.show_result(mission)
    assert panel.evidence_column.count.text() == 'no tool ran'


def test_a_failed_mission_says_it_did_not_finish(panel):
    mission = Mission(id='m3', goal='Do something impossible.', status='failed', steps=3)
    panel.show_result(mission)
    assert panel.status.text() == 'FAILED'
    assert 'did not finish' in panel.evidence_column.answer.text()


# ── the readings on the left ───────────────────────────────────────────────

def test_a_gauge_without_a_reading_says_so(app):
    palette = PrimePalette(dark=True)
    gauge = GaugeRing(palette, 'CPU')
    gauge.set_reading(None, '—')
    assert gauge.text == '—'
    assert gauge.value is None


def test_the_readings_are_real_readings(panel):
    panel.telemetry.refresh()
    # The CPU reading is only there once the sampler has a baseline, so
    # the test accepts the first sample being unavailable.
    gauge = panel.telemetry.cpu
    assert gauge.text == '—' or gauge.text.endswith('%')
    assert panel.telemetry.extra.text().startswith('GPU ')


def test_the_memory_count_is_a_real_count(panel, tmp_path):
    from memory.memory_service import MemoryService

    service = MemoryService(tmp_path / 'history.sqlite3')
    service.remember('One', 'A note.')
    service.remember('Two', 'Another note.')
    column = TelemetryColumn(PrimePalette(dark=True), memory=service)
    column.refresh()
    assert column.memory_count.text() == '2 notes'


def test_the_memory_count_says_unavailable_when_it_cannot_be_read(panel):
    class Broken:
        def count(self):
            raise RuntimeError('The database is locked.')

    column = TelemetryColumn(PrimePalette(dark=True), memory=Broken())
    column.refresh()
    assert column.memory_count.text() == 'notes —'


# ── the painting ───────────────────────────────────────────────────────────

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
