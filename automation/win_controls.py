"""Bounded readback of the foreground Windows text control after approved input."""
import ctypes
from ctypes import wintypes

EDIT_CLASSES = {'edit', 'richedit20w', 'richedit50w', 'richeditd2dpt', 'richeditd2d'}
MAX_UNITS = 24000


class GUIThreadInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD)] + [
        (name, wintypes.HWND) for name in
        ('active', 'focus', 'capture', 'menu', 'move', 'caret')
    ] + [('rcCaret', wintypes.RECT)]


def foreground_window():
    """Get the handle of the visible foreground window."""
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    handle = user32.GetForegroundWindow()
    return handle if handle and user32.IsWindowVisible(handle) else None


def foreground_process():
    """Get the native process ID of the visible foreground window."""
    handle = foreground_window()
    if not handle:
        return None
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
    pid = ctypes.c_uint32()
    if user32.GetWindowThreadProcessId(handle, ctypes.byref(pid)) and pid.value:
        return pid.value
    return None


def focused_editor():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    foreground = user.GetForegroundWindow()
    if not foreground:
        return None
    thread = user.GetWindowThreadProcessId(foreground, None)
    info = GUIThreadInfo(cbSize=ctypes.sizeof(GUIThreadInfo))
    user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUIThreadInfo)]
    if not thread or not user.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.focus:
        return None
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    if user.GetAncestor(info.focus, 2) != foreground:  # GA_ROOT
        return None
    name = ctypes.create_unicode_buffer(96)
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    if not user.GetClassNameW(info.focus, name, len(name)) or name.value.casefold() not in EDIT_CLASSES:
        return None
    # Only the editor in the application window, never an Open/Save dialog.
    if not user.GetClassNameW(foreground, name, len(name)) or name.value == '#32770':
        return None
    return info.focus


def _message(hwnd, message, count=0, address=0):
    api = ctypes.WinDLL('user32', use_last_error=True).SendMessageTimeoutW
    api.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
                    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    api.restype = ctypes.c_ssize_t
    result = ctypes.c_size_t()
    if not api(hwnd, message, count, address, 2, 80, ctypes.byref(result)):
        return None
    return result.value


def contents(hwnd):
    length = _message(hwnd, 0x000E)  # WM_GETTEXTLENGTH
    if length is None or length > MAX_UNITS:
        return None
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = _message(hwnd, 0x000D, len(buffer), ctypes.addressof(buffer))
    if copied != length:
        return None
    return buffer.value


def expected_edit(hwnd, insertion):
    before = contents(hwnd)
    if before is None:
        return None
    selection = _message(hwnd, 0x00B0)  # EM_GETSEL, packed UTF-16 offsets
    if selection is None:
        return None
    start, end = selection & 0xffff, (selection >> 16) & 0xffff
    data = before.encode('utf-16-le')
    if not 0 <= start <= end <= len(data) // 2:
        return None
    try:
        result = data[:2*start].decode('utf-16-le') + insertion + data[2*end:].decode('utf-16-le')
    except UnicodeDecodeError:
        return None
    if result == before:
        return None
    return normal_text(result)


def normal_text(value):
    return value.replace('\r\n', '\n').replace('\r', '\n')
