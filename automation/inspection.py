"""Read-only visible top-level window inventory, isolated in a bounded child process.

Window titles can contain private information. Call from a user-approved desktop
operation only. Never scrape child controls or interact with any window here.
"""
import ctypes
import json
from pathlib import Path
import subprocess
import sys

MAX_WINDOWS = 30


def _windows_child():
    if sys.platform != 'win32':
        raise RuntimeError('Window inspection is Windows-only.')
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    windows = []

    @callback_type
    def collect(hwnd, _):
        if len(windows) >= MAX_WINDOWS:
            return False
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length < 1:
            return True
        buffer = ctypes.create_unicode_buffer(min(length, 200) + 1)
        if not user32.GetWindowTextW(hwnd, buffer, len(buffer)):
            return True
        title = buffer.value.strip()
        if title:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append({'title': title[:200], 'pid': int(pid.value)})
        return True

    user32.EnumWindows(collect, 0)
    return windows


def inspect_windows(timeout=3):
    """Return capped title/PID records, or a sanitized error on timeout/failure."""
    if sys.platform != 'win32':
        raise RuntimeError('Window inspection requires Windows.')
    if not 0 < timeout <= 10:
        raise ValueError('Inspection timeout must be between 0 and 10 seconds.')
    try:
        result = subprocess.run(
            [sys.executable, '-I', str(Path(__file__).resolve()), '--child'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=timeout, shell=False, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Window inspection timed out and was stopped.') from None
    except OSError:
        raise RuntimeError('Could not start the isolated window inspector.') from None
    if result.returncode != 0 or len(result.stdout) > 20_000:
        raise RuntimeError('Window inspection failed.')
    try:
        entries = json.loads(result.stdout)
        if not isinstance(entries, list) or len(entries) > MAX_WINDOWS:
            raise ValueError('Invalid window count')
        if any(not isinstance(x, dict) or not isinstance(x.get('title'), str)
               or len(x['title']) > 200 or type(x.get('pid')) is not int for x in entries):
            raise ValueError('Invalid record')
        return entries
    except (ValueError, TypeError):
        raise RuntimeError('Invalid window inspection response.') from None


if __name__ == '__main__':
    if sys.argv[1:] != ['--child']:
        raise SystemExit(2)
    print(json.dumps(_windows_child(), ensure_ascii=False))
