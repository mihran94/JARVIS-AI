"""Reading what the Windows Calculator is actually showing.

WHAT THIS IS
    The Calculator in Windows publishes its display through UI
    Automation, so the value on the screen can be read rather than
    guessed at. That is what makes the Calculator → Notepad workflow
    possible: the number that is carried into the other application is
    the number the Calculator is really showing.

    The value is read from the accessibility tree, and the tree is read
    from the process that owns the window. Nothing is typed into the
    Calculator here: this module only looks.

WHAT THIS IS NOT
    * It does not press the keys. The calculator keys are pressed
      through `automation.input`, where the focus is checked first.
    * It does not guess a result. A Calculator that is not showing
      anything readable is reported as such.
"""
from __future__ import annotations

import re

from automation.uia import UiaUnavailable, find, flatten, read_tree

#: The name of the element that holds the Calculator's display.
DISPLAY_ID = 'calculatorResults'

#: The names the Calculator has used for that element.
DISPLAY_IDS = (DISPLAY_ID, 'resultsDisplay', 'calculatorResult')

#: A value the display can show.
_NUMBER = re.compile(r'^-?[\d,]*\.?\d+(?:[eE][-+]?\d+)?$')


def is_a_display_value(text: str) -> bool:
    """Whether a string is a number a calculator would show."""
    if not isinstance(text, str):
        return False
    value = text.strip().replace(' ', ' ')
    if not value:
        return False
    if value in ('0', '-0'):
        return True
    return bool(_NUMBER.match(value))


def normalise_value(text: str) -> str:
    """The number the display shows, without the separators."""
    value = (text or '').strip().replace(' ', '')
    return value.replace(',', '')


def find_display(elements) -> str:
    """The value in the tree, or an empty string.

    The element with the known id is preferred. When the tree does not
    carry that id, a text element whose name is a number is used, which
    is what the Calculator publishes in some versions.
    """
    for wanted in DISPLAY_IDS:
        matches = find(elements, automation_id=wanted)
        if matches:
            name = (matches[0].name or '').strip()
            if name:
                return name
    for element in flatten(elements):
        if element.control_type not in ('Text', 'Edit', 'Document'):
            continue
        name = (element.name or '').strip()
        if is_a_display_value(name):
            return name
    return ''


def read_display(process_id: int = 0, *, timeout: float = 0.0) -> str:
    """The value the Calculator is showing.

    An empty string means the display could not be read: the window was
    not there, or it was showing something that is not a number.
    """
    try:
        tree = read_tree(process_id=int(process_id or 0))
    except UiaUnavailable:
        return ''
    value = find_display(tree)
    if not value:
        return ''
    return normalise_value(value)


def display_is_readable(process_id: int = 0) -> bool:
    """Whether the Calculator's display can be read at all."""
    return bool(read_display(process_id))


__all__ = ['DISPLAY_ID', 'DISPLAY_IDS', 'display_is_readable', 'find_display',
           'is_a_display_value', 'normalise_value', 'read_display']
