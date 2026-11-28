"""Local reminders, daily alarms and an upcoming-reminder briefing."""
from datetime import datetime, timedelta
import re
from uuid import uuid4
from urllib.parse import urlencode

from core.conversation import addressed_request


COMMAND = re.compile(
    r'(?:(?P<reminder>remind me (?:at )?|நினைவூட்டு )|'
    r'(?P<alarm>(?:set )?(?:an )?alarm(?: (?:at|for))? |அலாரம் )|'
    r'(?P<daily>daily update (?:at )?|தினசரி அப்டேட் )|'
    r'(?P<schedule>schedule |ஷெட்யூல் ))'
    r'(?:(?P<day>tomorrow|நாளை|\d{4}-\d{2}-\d{2}) )?(?P<time>\d{1,2}:\d{2})'
    r'(?: (?P<text>.+))?', re.IGNORECASE)


MOVE = re.compile(
    r'(?:move reminder|நேரம் மாற்று) ([a-f0-9]{8}) (?:to )?'
    r'(?:(tomorrow|நாளை|\d{4}-\d{2}-\d{2}) )?(\d{1,2}:\d{2})', re.I)


def scheduled_time(now, day, time):
    hour, minute = map(int, time.split(':'))
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day and day.casefold() not in ('tomorrow', 'நாளை'):
        due = datetime.combine(datetime.fromisoformat(day).date(), due.time())
        if due <= now:
            raise ValueError('The date and time must be in the future.')
        return due
    if day or due <= now:
        due += timedelta(days=1)
    return due


class Reminders:
    KEY = 'reminders:items'

    def __init__(self, store):
        self.store = store

    def items(self):
        return self.store.get(self.KEY, [])

    def command(self, text, now=None):
        text = addressed_request(text).strip()
        now = now or datetime.now()
        if text.casefold() in ('list reminders', 'நினைவூட்டல்கள் காட்டு'):
            return self.summary(self.items())
        cancel = re.fullmatch(r'(?:cancel reminder|நினைவூட்டல் ரத்து) ([a-f0-9]{8})', text, re.I)
        if cancel:
            items = self.items()
            remaining = [item for item in items if item['id'] != cancel[1].lower()]
            if len(remaining) == len(items):
                return 'Reminder not found.'
            self.store.set(self.KEY, remaining)
            return 'Reminder cancelled.'
        move = MOVE.fullmatch(text)
        if move:
            return self.move(move[1].lower(), move[2], move[3], now)
        match = COMMAND.fullmatch(text)
        if not match:
            return None
        try:
            due = scheduled_time(now, match['day'], match['time'])
        except ValueError:
            return 'Use a future date with a 24-hour time, such as 2026-12-01 18:00.'
        kind = 'briefing' if match['daily'] else 'alarm' if match['alarm'] else 'reminder'
        label = match['text'] or ('Daily update' if kind == 'briefing' else 'Wake up')
        if kind == 'reminder' and not match['text']:
            return 'Add what to remember. Example: remind me at 18:00 call the clinic.'
        items = self.items()
        if kind == 'briefing':
            items = [item for item in items if item['kind'] != 'briefing']
        item = {'id': uuid4().hex[:8], 'due': due.isoformat(), 'text': label, 'kind': kind}
        self.store.set(self.KEY, items + [item])
        return f'{label} · {due:%a %d %b at %H:%M} · {item["id"]}'

    def move(self, ident, day, time, now):
        items = self.items()
        for item in items:
            if item['id'] == ident:
                try:
                    due = scheduled_time(now, day, time)
                except ValueError:
                    return 'Use a future date and a 24-hour time.'
                item['due'] = due.isoformat()
                self.store.set(self.KEY, items)
                return f'Moved {item["text"]} to {due:%a %d %b at %H:%M} · {ident}'
        return 'Reminder not found.'

    def google_calendar_url(self, ident):
        for item in self.items():
            if item['id'] != ident or item['kind'] == 'briefing':
                continue
            start = datetime.fromisoformat(item['due'])
            end = start + timedelta(minutes=30)
            return 'https://calendar.google.com/calendar/render?' + urlencode({
                'action': 'TEMPLATE', 'text': item['text'],
                'dates': f'{start:%Y%m%dT%H%M%S}/{end:%Y%m%dT%H%M%S}',
            })
        return None

    @staticmethod
    def summary(items):
        if not items:
            return 'No upcoming reminders.'
        return '\n'.join(
            f'{datetime.fromisoformat(item["due"]):%a %d %b %H:%M} · '
            f'{item["text"]} · {item["id"]}'
            for item in sorted(items, key=lambda item: item['due'])[:12])

    def due(self, now=None):
        now = now or datetime.now()
        items = self.items()
        ready = [item for item in items if datetime.fromisoformat(item['due']) <= now]
        if not ready:
            return []
        remaining = [item for item in items if item not in ready]
        for item in ready:
            if item['kind'] == 'briefing':
                scheduled = datetime.fromisoformat(item['due'])
                tomorrow = datetime.combine(now.date() + timedelta(days=1), scheduled.time())
                remaining.append({**item, 'due': tomorrow.isoformat()})
        self.store.set(self.KEY, remaining)
        return [self.summary([item for item in remaining if item['kind'] != 'briefing'])
                if item['kind'] == 'briefing' else item['text'] for item in ready]
