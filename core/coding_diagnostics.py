"""Reading a failure out of what a test run actually printed.

WHAT THIS IS
    When a test fails, the output is a wall of text. This turns that text
    into the facts a repair needs: which file, which line, what kind of
    failure, and the message the tool gave.

    It reads the real output of the real runners:

    * pytest, in its short and verbose forms;
    * unittest;
    * a plain Python traceback from anything at all;
    * Node's test runner;
    * a compiler's `file:line: error: message` lines.

WHAT THIS IS NOT
    * It does not guess. A line that is not a failure line is not turned
      into one, and a run that failed with no readable failure says so
      rather than inventing a location.
    * It does not fix anything. It says what broke; `core.coding_repair`
      decides what to do about it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

#: The kinds of failure that are reported.
KINDS = ('assertion', 'exception', 'syntax', 'import', 'timeout', 'compile', 'unknown')


@dataclass
class Failure:
    """One thing that went wrong, and where."""

    kind: str = 'unknown'
    file: str = ''
    line: int = 0
    message: str = ''
    test: str = ''
    snippet: str = ''

    def as_dict(self) -> dict:
        return {'kind': self.kind, 'file': self.file, 'line': self.line,
                'message': self.message, 'test': self.test, 'snippet': self.snippet}

    def describe(self) -> str:
        """The failure as the owner and the model read it."""
        where = self.file or 'the project'
        if self.line:
            where = f'{where}, line {self.line}'
        parts = [f'{self.kind.upper()} in {where}']
        if self.test:
            parts.append(f'test {self.test}')
        if self.message:
            parts.append(self.message)
        text = '\n'.join(parts)
        if self.snippet:
            text += f'\n  {self.snippet}'
        return text


_PYTEST_LINE = None


def _pytest_line(line: str) -> tuple:
    """A pytest result line: `FAILED path::test - message`."""
    for marker in ('FAILED', 'ERROR'):
        if line.startswith(marker + ' '):
            rest = line[len(marker) + 1:].strip()
            location, _, message = rest.partition(' - ')
            file_part, _, test = location.partition('::')
            return marker.lower(), file_part, test, message.strip()
    return None


_TRACEBACK_FILE = None


def _traceback_file(line: str) -> tuple:
    """A Python traceback frame: `  File "path.py", line 12, in name`."""
    stripped = line.strip()
    if not stripped.startswith('File "'):
        return None
    try:
        rest = stripped[6:].split('"', 1)[0]
        location = stripped.split('line ', 1)
        if len(location) < 2:
            return None
        number = location[1].split(',')[0].strip()
        return rest, int(number)
    except (IndexError, ValueError):
        return None


def _kind_from_message(message: str) -> str:
    """The kind of failure a message describes."""
    text = (message or '').lower()
    if 'assertionerror' in text or text.startswith('assert'):
        return 'assertion'
    if 'modulenotfounderror' in text or 'importerror' in text:
        return 'import'
    if 'syntaxerror' in text or 'indentationerror' in text:
        return 'syntax'
    if 'timeout' in text or 'timed out' in text:
        return 'timeout'
    if 'error' in text:
        return 'exception'
    return 'unknown'


_SUMMARY_LOCATION = None


def _summary_locations(lines) -> dict:
    """The `file:line: Error` lines pytest prints under each failure."""
    found = {}
    for line in lines:
        match = re.match(r'^(?P<file>[^\s:]+):(?P<line>\d+): (?P<kind>[\w.]+)', line.strip())
        if match:
            found.setdefault(match.group('file'), []).append(
                (int(match.group('line')), match.group('kind')))
    return found


def parse_failures(output: str, *, source: str = '') -> list:
    """Read the failures out of what a command printed.

    The output of a real run is read; nothing here invents a location,
    and a run that failed without a readable failure gives no failure at
    all, so the caller can say "the output did not say why".
    """
    if not output:
        return []
    failures = []
    lines = output.splitlines()
    locations = _summary_locations(lines)
    for index, line in enumerate(lines):
        parsed = _pytest_line(line.strip())
        if parsed:
            kind, file, test, message = parsed
            detail = message or _pytest_detail(lines, index)
            failures.append(Failure(kind=_kind_from_message(detail),
                                    file=file, line=0,
                                    message=detail, test=test))
            continue
        if line.startswith(('FAIL: ', 'ERROR: ')):
            kind = 'exception' if line.startswith('ERROR: ') else 'assertion'
            name = line.split(': ', 1)[1].strip()
            detail, location = _traceback_after(lines, index)
            failures.append(Failure(kind=kind, file=location[0], line=location[1],
                                    message=detail, test=name))
            continue
        if 'Traceback (most recent call last)' in line:
            detail, location = _traceback_after(lines, index)
            if location[0] or detail:
                failures.append(Failure(kind=_kind_from_message(detail),
                                        file=location[0], line=location[1], message=detail))
            continue
        if 'not ok ' in line:
            name = line.split('not ok', 1)[1].strip(' -0123456789 ')
            detail, location = _node_after(lines, index)
            failures.append(Failure(kind='assertion', file=location[0], line=location[1],
                                    message=detail, test=name))
            continue
        if _looks_like_compiler_error(line):
            file, number, message = _compiler_error(line)
            failures.append(Failure(kind='compile', file=file, line=number, message=message))
            continue
    for failure in failures:
        if not failure.line:
            failure.line = _line_for(failure, locations)
    if not failures and _says_nothing_ran(output):
        failures.append(Failure(kind='unknown', message='The run did not report a failure.'))
    return failures


def _line_for(failure, locations) -> int:
    """The line a failure happened on, when the output says it."""
    if not failure.file:
        return 0
    name = failure.file.split('::')[-1]
    candidates = locations.get(name) or locations.get(failure.file) or []
    for number, kind in candidates:
        if kind.casefold() in (failure.message or '').casefold():
            return number
    return candidates[0][0] if candidates else 0


def _pytest_detail(lines, index) -> str:
    """The `E   ...` lines under a pytest result."""
    parts = []
    for line in lines[index + 1:index + 6]:
        stripped = line.strip()
        if stripped.startswith('E '):
            parts.append(stripped[2:].strip())
        elif stripped and not stripped.startswith(('E ', '-', '_')):
            break
    return ' '.join(parts)


def _line_of(lines, index, file) -> int:
    """The line number of a pytest failure, when the output gives one."""
    for line in lines[index + 1:index + 8]:
        match = _traceback_file(line)
        if match and (not file or match[0].endswith(file.split('::')[-1])):
            return match[1]
    return 0


def _is_exception_line(text: str) -> bool:
    """Whether a line names an exception, such as `ValueError: it broke`."""
    return bool(re.match(r'^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt|Warning)\b', text)) \
        or bool(re.match(r'^[A-Za-z_][\w.]*: ', text))


def _traceback_after(lines, index) -> tuple:
    """The message and the location of a traceback that follows.

    The frame that is kept is the deepest one, because that is where the
    exception was actually raised. The frames above it are the callers,
    which is useful to read and not useful to edit.
    """
    message = ''
    file = ''
    number = 0
    for line in lines[index + 1:index + 60]:
        frame = _traceback_file(line)
        if frame:
            file, number = frame
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if set(stripped) <= set('-=_*'):
            continue
        if stripped.startswith('Traceback (most recent call last)'):
            continue
        if stripped.startswith(('During handling', 'The above exception')):
            continue
        if _is_exception_line(stripped):
            message = stripped
            break
    return message, (file, number)


def _node_after(lines, index) -> tuple:
    """The message and the location of a Node test failure."""
    message = ''
    file = ''
    number = 0
    block = []
    for line in lines[index + 1:index + 40]:
        stripped = line.strip()
        if stripped.startswith('error:'):
            value = stripped[6:].strip()
            if value in ('|-', '|', '>-'):
                # The message is the indented block under it.
                block = []
                for follow in lines[index + 2:index + 30]:
                    if not follow.strip():
                        continue
                    if follow[:1].isspace():
                        block.append(follow.strip())
                        continue
                    break
                message = ' '.join(block)
            else:
                message = value
            continue
        if stripped.startswith('at ') and ':' in stripped:
            place = stripped[3:]
            # `at name (file:line:column)` or `at file:line:column`
            if place.endswith(')'):
                place = place[place.rfind('(') + 1:place.rfind(')')]
            parts = place.rsplit(':', 2)
            if len(parts) == 3:
                file = parts[0].strip()
                digits = ''.join(char for char in parts[1] if char.isdigit())
                number = int(digits) if digits else 0
            else:
                file = place.strip()
            continue
        if message and not stripped:
            break
    return message, (file, number)


def _looks_like_compiler_error(line: str) -> bool:
    stripped = line.strip()
    if ': error:' not in stripped:
        return False
    return bool(re.match(r'^[^:]+\.[A-Za-z0-9]+:\d+:', stripped))


def _compiler_error(line: str):
    """A compiler error: `file.py:12: error: message`."""
    stripped = line.strip()
    location, _, message = stripped.partition(': error:')
    file, _, number = location.rpartition(':')
    try:
        return file.strip(), int(number.strip()), message.strip()
    except ValueError:
        return file.strip(), 0, message.strip()


def _says_nothing_ran(output: str) -> bool:
    """Whether the output says the run found nothing at all."""
    text = output.lower()
    return ('no tests ran' in text or 'no tests found' in text
            or 'collected 0 items' in text)


def summarize(failures) -> str:
    """The failures as one block of text for the model to read."""
    if not failures:
        return 'No readable failure was found in the output.'
    return '\n\n'.join(failure.describe() for failure in failures)


__all__ = ['Failure', 'KINDS', 'parse_failures', 'summarize']
