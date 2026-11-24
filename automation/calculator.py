"""Read the Windows Calculator display and invoke approved arithmetic controls."""
from __future__ import annotations

import operator
import re
import sys
import time

import psutil

from automation import win_controls
from automation.uia import UiaUnavailable, find, flatten, load_client, read_tree

#: The name of the element that holds the Calculator's display.
DISPLAY_ID = 'calculatorResults'

#: The names the Calculator has used for that element.
DISPLAY_IDS = (DISPLAY_ID, 'CalculatorResults', 'resultsDisplay', 'calculatorResult')
CALCULATOR_PROCESSES = {'calculator.exe', 'calculatorapp.exe'}
OPERATIONS = {
    '+': ('plusButton', operator.add),
    '-': ('minusButton', operator.sub),
    '*': ('multiplyButton', operator.mul),
}
_EXPRESSION = re.compile(r'([0-9]{1,6})\s*([+*×−-])\s*([0-9]{1,6})')
_DISPLAY_INTEGER = re.compile(
    r'(?<![\d.,])[-−]?(?:[0-9]{1,3}(?:[, \u00a0\u202f][0-9]{3})+|[0-9]+)\Z')

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


def parse_expression(expression):
    """Return the two operands and an allowed Calculator operator."""
    match = _EXPRESSION.fullmatch(expression.strip())
    if not match:
        raise ValueError('Use two integers with up to six digits and one +, - or * operator.')
    left, operation, right = match.groups()
    return str(int(left)), {'×': '*', '−': '-'}.get(operation, operation), str(int(right))


def _process_name(pid):
    try:
        return psutil.Process(pid).name().casefold()
    except (psutil.Error, OSError):
        return ''


def _find_control(root, automation, control_id):
    from System.Windows.Automation import PropertyCondition, TreeScope

    condition = PropertyCondition(automation.AutomationIdProperty, control_id)
    matches = root.FindAll(TreeScope.Descendants, condition)
    return matches[0] if matches.Count == 1 else None


def foreground_calculator():
    """Identify the foreground Calculator, including its Windows 10 frame."""
    if sys.platform != 'win32':
        raise RuntimeError('Windows Calculator is available on Windows only.')
    handle = win_controls.foreground_window()
    pid = win_controls.foreground_process()
    if not handle or not pid or _process_name(pid) not in (
            CALCULATOR_PROCESSES | {'applicationframehost.exe'}):
        return None
    automation = load_client()
    from System import Exception as AutomationError, IntPtr

    try:
        root = automation.FromHandle(IntPtr(handle))
        display = _find_control(root, automation, 'CalculatorResults')
        if (display is None or display.Current.IsOffscreen
                or _process_name(display.Current.ProcessId) not in CALCULATOR_PROCESSES
                or win_controls.foreground_window() != handle):
            return None
    except AutomationError:
        return None
    return handle, root, display


def _display_integer(name):
    match = _DISPLAY_INTEGER.search(name.strip())
    if match is None:
        return None
    value = match.group().translate(str.maketrans('−', '-', ', \u00a0\u202f'))
    return int(value)


def calculate_in_window(expression, calculator, *, check):
    """Invoke the approved keys and return the observed Calculator result."""
    left, operation, right = parse_expression(expression)
    handle, root, display = calculator
    automation = load_client()
    from System import Exception as AutomationError
    from System.Windows.Automation import InvokePattern

    operator_id, evaluate = OPERATIONS[operation]
    control_ids = ['clearButton', *(f'num{digit}Button' for digit in left),
                   operator_id, *(f'num{digit}Button' for digit in right), 'equalButton']
    patterns = {}
    try:
        for name in dict.fromkeys(control_ids):
            control = _find_control(root, automation, name)
            if (control is None or not control.Current.IsEnabled or control.Current.IsOffscreen
                    or control.Current.ProcessId != display.Current.ProcessId):
                raise RuntimeError('Open Standard mode in Windows Calculator and try again.')
            patterns[name] = control.GetCurrentPattern(InvokePattern.Pattern)
    except AutomationError:
        raise RuntimeError('Calculator controls could not be verified.') from None
    for name in control_ids:
        check()
        if win_controls.foreground_window() != handle:
            raise RuntimeError('Calculator lost focus. Check its display before retrying.')
        try:
            patterns[name].Invoke()
        except AutomationError:
            raise RuntimeError('A Calculator key could not be applied. Check its display.') from None
    expected = evaluate(int(left), int(right))
    deadline = time.monotonic() + 0.75
    while time.monotonic() < deadline:
        check()
        if win_controls.foreground_window() != handle:
            break
        try:
            value = _display_integer(display.Current.Name)
        except AutomationError:
            break
        if value == expected:
            return str(value)
        time.sleep(0.025)
    raise RuntimeError('The result could not be verified on the Calculator display.')


__all__ = ['DISPLAY_ID', 'DISPLAY_IDS', 'calculate_in_window', 'display_is_readable',
           'find_display', 'foreground_calculator', 'is_a_display_value', 'normalise_value',
           'parse_expression', 'read_display']
