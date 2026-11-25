"""Approval-gated interaction with controls published by Windows apps."""
from contextlib import contextmanager
import os

import psutil

from automation import uia, win_controls
from automation.input import InputRefused, activate_window


BLOCKED_PROCESSES = {
    'applicationframehost.exe', 'chatgpt.exe', 'cmd.exe', 'codex.exe', 'conhost.exe', 'credentialuibroker.exe',
    'explorer.exe', 'lockapp.exe', 'msiexec.exe', 'powershell.exe', 'pwsh.exe',
    'regedit.exe', 'securityhealthsystray.exe', 'sechealthui.exe', 'systemsettings.exe',
    'taskmgr.exe', 'vmconnect.exe', 'wsl.exe', 'windowsterminal.exe',
}
INVOKE_TYPES = {'Button', 'MenuItem', 'SplitButton'}
EDIT_TYPES = {'Edit'}
SENSITIVE_LABELS = (
    'password', 'passcode', 'secret', 'one-time code', 'security code', 'api key',
    'terminal', 'command prompt', 'powershell',
)
MAX_TEXT = 240


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


def see_controls(pid, title):
    """Return action labels and IDs without reading editable values."""
    with _foreground_app(pid, title) as (controls, check):
        results = []
        for control in controls:
            entry = _usable(control, pid)
            if entry and entry[2] in INVOKE_TYPES | EDIT_TYPES and (entry[0] or entry[1]):
                name, automation_id, kind = entry
                results.append(f'{kind} {name[:100]!r} (id={automation_id[:100]!r})')
        check()
    return '\n'.join(results[:50]) or 'No supported controls were published by this window.'


def _control_pattern(control, *, editing):
    from System.Windows.Automation import InvokePattern, ValuePattern

    return control.GetCurrentPattern(ValuePattern.Pattern if editing else InvokePattern.Pattern)


def use_control(pid, title, name, automation_id='', *, text=None, checkpoint=lambda: None):
    if (not name and not automation_id) or len(name) > 100 or len(automation_id) > 100:
        raise InputRefused('Choose a control by the exact name or ID shown by inspection.')
    if text is not None and (not 1 <= len(text) <= MAX_TEXT or any(ord(char) < 32 for char in text)):
        raise InputRefused(f'Enter between 1 and {MAX_TEXT} printable characters.')
    # A JARVIS approval dialog can briefly take focus. Restore the approved
    # app only in that case, and leave a different foreground app alone.
    if win_controls.foreground_process() == os.getpid():
        _application(pid)
        checkpoint()
        activate_window(pid)
    with _foreground_app(pid, title) as (controls, check):
        kinds = INVOKE_TYPES if text is None else EDIT_TYPES
        matches = []
        for control in controls:
            entry = _usable(control, pid)
            if not entry:
                continue
            actual_name, actual_id, kind = entry
            if kind in kinds and (not name or name == actual_name) and (
                    not automation_id or automation_id == actual_id):
                matches.append((control, entry))
        if len(matches) != 1:
            raise InputRefused('The named control is missing or ambiguous. Inspect the window again.')
        control, entry = matches[0]
        label = entry[0] or entry[1]
        pattern = _control_pattern(control, editing=text is not None)
        check()
        if _usable(control, pid) != entry:
            raise InputRefused('The control changed. No input was sent.')
        checkpoint()
        if text is None:
            pattern.Invoke()
            return f'Windows invoked {label!r}. Inspect the window again to verify the result.'
        if pattern.Current.IsReadOnly:
            raise InputRefused('The selected field is read-only.')
        pattern.SetValue(text)
        if pattern.Current.Value != text:
            raise InputRefused('Windows accepted the edit request but did not verify the new value.')
        return f'Windows verified the text in {label!r}.'
