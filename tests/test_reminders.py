from datetime import datetime

from core.reminders import Reminders
from core.store import Store


def test_reminders_survive_restart_and_do_not_fire_twice(tmp_path):
    path = tmp_path / 'history.sqlite3'
    reminders = Reminders(Store(path))
    night = datetime(2026, 11, 28, 21)
    assert '29 Nov at 06:30' in reminders.command('Hey Jarvis, அலாரம் நாளை 06:30', night)
    reminders = Reminders(Store(path))
    assert reminders.due(night) == []
    morning = datetime(2026, 11, 29, 6, 30)
    assert reminders.due(morning) == ['Wake up']
    assert reminders.due(morning) == []


def test_daily_briefing_lists_upcoming_reminders_and_recurs(tmp_path):
    reminders = Reminders(Store(tmp_path / 'history.sqlite3'))
    morning = datetime(2026, 11, 28, 7)
    reminders.command('daily update at 08:00', morning)
    reminders.command('remind me at 18:00 call the clinic', morning)
    assert 'call the clinic' in reminders.due(morning.replace(hour=8))[0]
    assert reminders.items()[-1]['due'] == '2026-11-29T08:00:00'
    assert reminders.command('explain how to set an alarm') is None
    assert '24-hour' in reminders.command('alarm 25:00', morning)
    ident = reminders.items()[0]['id']
    assert reminders.command('cancel reminder ' + ident) == 'Reminder cancelled.'


def test_edit_keeps_id_and_calendar_draft_uses_new_time(tmp_path):
    from urllib.parse import parse_qs, urlsplit

    reminders = Reminders(Store(tmp_path / 'history.sqlite3'))
    now = datetime(2026, 11, 28, 9)
    reminders.command('ஷெட்யூல் 2026-12-01 18:00 Gym', now)
    ident = reminders.items()[0]['id']
    reminders.command(f'நேரம் மாற்று {ident} 2026-12-01 19:45', now)
    assert len(reminders.items()) == 1
    params = parse_qs(urlsplit(reminders.google_calendar_url(ident)).query)
    assert params['text'] == ['Gym']
    assert params['dates'] == ['20261201T194500/20261201T201500']
