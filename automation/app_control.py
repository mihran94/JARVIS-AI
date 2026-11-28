"""Approval-gated interaction with controls published by Windows apps."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import time

import psutil

from automation import uia, win_controls
from automation import input as desktop_input
from automation.input import InputRefused, InputTarget, activate_window


BLOCKED_PROCESSES = {
    'applicationframehost.exe', 'chatgpt.exe', 'cmd.exe', 'codex.exe', 'conhost.exe', 'credentialuibroker.exe',
    'explorer.exe', 'lockapp.exe', 'msiexec.exe', 'powershell.exe', 'pwsh.exe',
    'regedit.exe', 'securityhealthsystray.exe', 'sechealthui.exe', 'systemsettings.exe',
    'taskmgr.exe', 'vmconnect.exe', 'wsl.exe', 'windowsterminal.exe',
}
INVOKE_TYPES = {'Button', 'MenuItem', 'SplitButton'}
EDIT_TYPES = {'Edit'}
SELECT_TYPES = {'DataItem', 'ListItem', 'TabItem', 'TreeItem'}
SCROLL_TYPES = {'DataGrid', 'Document', 'List', 'Pane', 'Table', 'Tree'}
SENSITIVE_LABELS = (
    'password', 'passcode', 'secret', 'one-time code', 'security code', 'api key',
    'terminal', 'command prompt', 'powershell',
)
MAX_TEXT = 240
NAVIGATION_KEYS = ('left', 'right', 'up', 'down', 'home', 'end', 'tab')


def _application(pid):
    if pid <= 0 or pid == os.getpid():
        raise InputRefused('Choose another open desktop application.')
    try:
        name = psutil.Process(pid).name()
    except (psutil.Error, OSError) as error:
        raise InputRefused('The selected application is no longer open.') from error
    if name.casefold() in BLOCKED_PROCESSES:
        raise InputRefused('JARVIS app control is unavailable for that Windows process.')
    return name


def list_apps():
    from automation.inspection import inspect_windows

    rows = []
    for window in inspect_windows():
        pid = window['pid']
        try:
            process = _application(pid)
        except InputRefused:
            continue
        rows.append(f'{process} (pid={pid}): {window["title"]!r}')
    return '\n'.join(rows) or 'No supported desktop application window is open.'


@contextmanager
def _foreground_app(pid, title):
    """Bind to one exact foreground HWND; refuse popups and focus changes."""
    automation = uia.load_client()
    handle = win_controls.foreground_window()
    if not handle or win_controls.window_process(handle) != pid:
        raise InputRefused('Bring the selected app window to the front and retry.')
    process = _application(pid)
    from System import IntPtr
    from System.Windows.Automation import TreeScope, Condition

    root = automation.FromHandle(IntPtr(handle))
    if root is None or root.Current.Name != title or not root.Current.IsEnabled:
        raise InputRefused('The active window does not match the selected app window.')

    def check():
        if (win_controls.foreground_window() != handle
                or win_controls.window_process(handle) != pid
                or _application(pid) != process or root.Current.Name != title
                or not root.Current.IsEnabled):
            raise InputRefused('The app window changed. No input was sent.')

    controls = root.FindAll(TreeScope.Descendants, Condition.TrueCondition)
    if controls.Count > 800:
        raise InputRefused('The window has too many controls. Open the specific panel and retry.')
    check()
    yield controls, check


def _usable(control, pid):
    props = control.Current
    name = str(props.Name or '')
    automation_id = str(props.AutomationId or '')
    if (props.ProcessId != pid or not props.IsEnabled or props.IsOffscreen
            or props.IsPassword or any(word in (name + ' ' + automation_id).casefold()
                                      for word in SENSITIVE_LABELS)):
        return None
    kind = str(props.ControlType.ProgrammaticName).removeprefix('ControlType.')
    return name, automation_id, kind


def focus_selected(pid, title):
    _application(pid)
    if win_controls.foreground_process() == os.getpid():
        activate_window(pid, title=title)


def see_controls(pid, title):
    """Return action labels and IDs without reading editable values."""
    with _foreground_app(pid, title) as (controls, check):
        results = []
        for control in controls:
            entry = _usable(control, pid)
            if entry and entry[2] in INVOKE_TYPES | EDIT_TYPES | SCROLL_TYPES | SELECT_TYPES and (entry[0] or entry[1]):
                name, automation_id, kind = entry
                results.append(f'{kind} {name[:100]!r} (id={automation_id[:100]!r})')
        check()
    return '\n'.join(results[:50]) or 'No supported controls were published by this window.'


def _control_pattern(control, *, editing):
    from System.Windows.Automation import InvokePattern, ValuePattern

    return control.GetCurrentPattern(ValuePattern.Pattern if editing else InvokePattern.Pattern)


@contextmanager
def _selected_control(pid, title, name, automation_id, kinds, checkpoint, *,
                      restore_focus=True, runtime_id=None):
    if (not name and not automation_id) or len(name) > 100 or len(automation_id) > 100:
        raise InputRefused('Choose a control by the exact name or ID shown by inspection.')
    # A JARVIS approval dialog can briefly take focus. Restore the approved
    # app only in that case, and leave a different foreground app alone.
    if restore_focus and win_controls.foreground_process() == os.getpid():
        _application(pid)
        checkpoint()
        activate_window(pid, title=title)
    with _foreground_app(pid, title) as (controls, check):
        matches = []
        for control in controls:
            entry = _usable(control, pid)
            if not entry:
                continue
            actual_name, actual_id, kind = entry
            if kind in kinds and (not name or name == actual_name) and (
                    not automation_id or automation_id == actual_id) and (
                    runtime_id is None or tuple(control.GetRuntimeId()) == runtime_id):
                matches.append((control, entry))
        if len(matches) != 1:
            raise InputRefused('The named control is missing or ambiguous. Inspect the window again.')
        control, entry = matches[0]

        def guard():
            check()
            if _usable(control, pid) != entry or (
                    runtime_id is not None and tuple(control.GetRuntimeId()) != runtime_id):
                raise InputRefused('The control changed. No input was sent.')
            checkpoint()
            return pid

        yield control, entry[0] or entry[1], guard


def verify_control(pid, title, name, automation_id='', *, expected, checkpoint=lambda: None):
    """Read one observable condition from the selected foreground window."""
    kinds = INVOKE_TYPES | EDIT_TYPES
    with _selected_control(pid, title, name, automation_id, kinds, checkpoint,
                           restore_focus=False) as (control, label, guard):
        guard()
        if expected == 'focused' and not control.Current.HasKeyboardFocus:
            raise InputRefused('The expected control does not have keyboard focus.')
        guard()
        return f'Windows observed {label!r} {expected}.'


def scroll_control(pid, title, name, automation_id='', *, direction, checkpoint=lambda: None):
    """Scroll one increment and verify movement in the requested direction."""
    from System.Windows.Automation import ScrollAmount, ScrollPattern

    if direction not in ('up', 'down'):
        raise InputRefused('Choose up or down.')
    with _selected_control(pid, title, name, automation_id, SCROLL_TYPES, checkpoint) as (
            control, label, guard):
        pattern = control.GetCurrentPattern(ScrollPattern.Pattern)
        guard()
        snapshot = pattern.Current
        if not snapshot.VerticallyScrollable:
            raise InputRefused('This control does not expose a vertical scroll range.')
        before = float(snapshot.VerticalScrollPercent)
        if not 0 <= before <= 100:
            raise InputRefused('Windows did not report a valid scroll position.')
        down = direction == 'down'
        if (down and before == 100) or (not down and before == 0):
            raise InputRefused(f'{label!r} is already at the requested edge.')
        amount = ScrollAmount.SmallIncrement if down else ScrollAmount.SmallDecrement
        guard()
        pattern.Scroll(ScrollAmount.NoAmount, amount)
        deadline = time.monotonic() + 0.7
        while True:
            guard()
            after = float(pattern.Current.VerticalScrollPercent)
            if 0 <= after <= 100 and (after > before if down else after < before):
                return f'Windows verified that {label!r} scrolled {direction}, from {before:g}% to {after:g}%.'
            if time.monotonic() >= deadline:
                raise InputRefused('Windows did not verify the scroll movement. Check the app before retrying.')
            time.sleep(0.05)


def _check_text(text):
    if not 1 <= len(text) <= MAX_TEXT or any(ord(char) < 32 for char in text):
        raise InputRefused(f'Enter between 1 and {MAX_TEXT} printable characters.')


def use_control(pid, title, name, automation_id='', *, text=None, checkpoint=lambda: None):
    if text is not None:
        _check_text(text)
    kinds = INVOKE_TYPES if text is None else EDIT_TYPES
    with _selected_control(pid, title, name, automation_id, kinds, checkpoint) as (control, label, guard):
        pattern = _control_pattern(control, editing=text is not None)
        guard()
        if text is None:
            pattern.Invoke()
            return f'Windows invoked {label!r}. Inspect the window again to verify the result.'
        if pattern.Current.IsReadOnly:
            raise InputRefused('The selected field is read-only.')
        pattern.SetValue(text)
        if pattern.Current.Value != text:
            raise InputRefused('Windows accepted the edit request but did not verify the new value.')
        return f'Windows verified the text in {label!r}.'


def select_control(pid, title, name, automation_id='', *, checkpoint=lambda: None, runtime_id=None):
    from System.Windows.Automation import SelectionItemPattern

    with _selected_control(pid, title, name, automation_id, SELECT_TYPES, checkpoint,
                           runtime_id=runtime_id) as (
            control, label, guard):
        pattern = control.GetCurrentPattern(SelectionItemPattern.Pattern)
        guard()
        pattern.Select()
        guard()
        if not pattern.Current.IsSelected:
            raise InputRefused('Windows did not verify the requested selection.')
        return f'Windows verified that {label!r} is selected.'


def pointed_control(pid, title, *, selecting=False):
    """Capture a published control under the cursor inside the approved window."""
    kinds = SELECT_TYPES if selecting else INVOKE_TYPES | EDIT_TYPES
    with _foreground_app(pid, title) as (controls, check):
        from System.Windows import Point

        cursor = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor)):
            raise InputRefused('Windows could not read the mouse position.')
        hit = uia.load_client().FromPoint(Point(cursor.x, cursor.y))
        runtime = tuple(hit.GetRuntimeId() or ()) if hit is not None else ()
        if runtime:
            for control in controls:
                if tuple(control.GetRuntimeId()) != runtime:
                    continue
                entry = _usable(control, pid)
                if entry and entry[2] in kinds and (entry[0] or entry[1]):
                    check()
                    return entry[0], entry[1], runtime
                break
    raise InputRefused('Point at a named control inside the selected app and try again.')


def _point_hits(control, x, y):
    from System.Windows import Point

    hit = uia.load_client().FromPoint(Point(x, y))
    return hit is not None and tuple(hit.GetRuntimeId()) == tuple(control.GetRuntimeId())


def mouse_click(pid, title, name, automation_id='', *, checkpoint=lambda: None, runtime_id=None):
    """Physically click the published point of exactly one visible control."""
    with _selected_control(pid, title, name, automation_id, INVOKE_TYPES | EDIT_TYPES,
                           checkpoint, runtime_id=runtime_id) as (control, label, guard):
        point = control.GetClickablePoint()
        x, y = round(point.X), round(point.Y)
        if not (0 <= x <= 10000 and 0 <= y <= 10000):
            raise InputRefused('The control is outside the supported desktop area.')

        def checked_point():
            guard()
            if not _point_hits(control, x, y):
                raise InputRefused('The control is covered or has moved. No click was sent.')
            return pid

        checked_point()
        user = ctypes.windll.user32
        if not user.SetCursorPos(x, y):
            raise InputRefused('Windows could not move the mouse to the selected control.')

        def at_control():
            checked_point()
            cursor = wintypes.POINT()
            if not user.GetCursorPos(ctypes.byref(cursor)) or (cursor.x, cursor.y) != (x, y):
                raise InputRefused('The mouse moved away from the control. No click was sent.')
            return pid

        desktop_input.click_at(x, y, InputTarget(pid, title), foreground=at_control)
        return f'Mouse clicked {label!r}. Inspect the app to verify its response.'


def keyboard_input(pid, title, name, automation_id='', *, text=None, key=None, checkpoint=lambda: None):
    """Send literal text or a navigation key to the specified focused field."""
    if text is None and key not in NAVIGATION_KEYS:
        raise InputRefused('Choose an approved navigation key.')
    if text is not None:
        _check_text(text)
    with _selected_control(pid, title, name, automation_id, EDIT_TYPES, checkpoint) as (
            control, label, guard):
        target = InputTarget(pid, title)

        def focused():
            guard()
            if not control.Current.HasKeyboardFocus:
                raise InputRefused('Focus the selected field before sending keyboard input.')
            return pid

        focused()
        if text is None:
            desktop_input.press_key(key, target, foreground=focused)
            return f'{key} was pressed in {label!r}.'
        pattern = _control_pattern(control, editing=True)
        if pattern.Current.IsReadOnly:
            raise InputRefused('The selected field is read-only.')
        before = pattern.Current.Value
        desktop_input.type_text(text, target, foreground=focused)
        deadline = time.monotonic() + 1.0
        while True:
            focused()
            after = pattern.Current.Value
            if after != before and text in after:
                return f'Windows verified the keyboard text in {label!r}.'
            if time.monotonic() >= deadline:
                raise InputRefused('Windows accepted keyboard input without verifying the inserted text.')
            time.sleep(0.05)
