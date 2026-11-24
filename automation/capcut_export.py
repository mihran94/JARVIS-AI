"""Save a reviewed, open CapCut Desktop export dialog on Windows."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time

import psutil

from automation import win_controls
from automation.input import InputTarget, click_at
from video_studio.verification import ffprobe_executable, verify_media


# CapCut Desktop 9.9 draws its controls itself. These points describe the
# settings form at 100% scale, using coordinates relative to the dialog.
# The result/share screen has the same title and a teal button elsewhere.
_FORM_SIZE = (720, 663)
_EXPORT_POINT = (572, 635)
_VIDEO_CHECK = (365, 192)
_SYNC_CHECK = (365, 507)


def new_mp4(path):
    output = Path(path).expanduser()
    if not output.is_absolute() or output.suffix.casefold() != '.mp4':
        raise ValueError('Choose the exact local MP4 path shown in CapCut.')
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('Choose an existing export folder.')
    output = parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new MP4 filename. Existing files will not be overwritten.')
    return output


def _window_api():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.WindowFromPoint.argtypes = [wintypes.POINT]
    user.WindowFromPoint.restype = wintypes.HWND
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    return user


def _rgb(pixel):
    return pixel & 255, (pixel >> 8) & 255, (pixel >> 16) & 255


def _teal(pixel):
    red, green, blue = _rgb(pixel)
    return red < 65 and green > 125 and blue > 125


def _unchecked(pixel):
    channels = _rgb(pixel)
    darkest, brightest = min(channels), max(channels)
    return 45 <= darkest and brightest <= 110 and brightest - darkest <= 18


def _local_export_point(user, hwnd):
    title = ctypes.create_unicode_buffer(256)
    user.GetWindowTextW(hwnd, title, len(title))
    rect = wintypes.RECT()
    if not title.value.startswith('Export-') or not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if (rect.right - rect.left, rect.bottom - rect.top) != _FORM_SIZE:
        return None
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.GetPixel.restype = wintypes.DWORD
    dc = user.GetDC(None)
    if not dc:
        return None
    try:
        video_x, video_y = _VIDEO_CHECK
        sync_x, sync_y = _SYNC_CHECK
        button_x, button_y = _EXPORT_POINT
        video = gdi.GetPixel(dc, rect.left + video_x - 3, rect.top + video_y)
        sync = gdi.GetPixel(dc, rect.left + sync_x, rect.top + sync_y)
        button = gdi.GetPixel(dc, rect.left + button_x, rect.top + button_y)
    finally:
        user.ReleaseDC(None, dc)
    if not (_teal(video) and _unchecked(sync) and _teal(button)):
        return None
    point = (rect.left + button_x, rect.top + button_y)
    if user.GetAncestor(user.WindowFromPoint(wintypes.POINT(*point)), 2) != hwnd:
        return None
    return point


def save_open_capcut_export(path, check_cancelled):
    """Confirm one local Export click, then verify the resulting new MP4."""
    if sys.platform != 'win32':
        raise RuntimeError('CapCut Desktop export is available on Windows only.')
    output = new_mp4(path)
    ffprobe_executable()
    user = _window_api()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        check_cancelled()
        hwnd = win_controls.foreground_window()
        pid = win_controls.foreground_process()
        if hwnd and pid:
            try:
                is_capcut = psutil.Process(pid).name().casefold() == 'capcut.exe'
            except (psutil.Error, OSError):
                is_capcut = False
            point = _local_export_point(user, hwnd) if is_capcut else None
            if point is not None:
                break
        time.sleep(0.1)
    else:
        raise RuntimeError('CapCut export settings could not be verified. Bring the open '
                           'Export dialog forward with Video checked and sync unchecked. '
                           'This layout supports CapCut Desktop 9.9 at 100% scale.')

    def current_target():
        check_cancelled()
        new_mp4(output)
        if (win_controls.foreground_window() == hwnd
                and win_controls.foreground_process() == pid
                and _local_export_point(user, hwnd) == point):
            return pid
        return None

    if current_target() != pid or not user.SetCursorPos(*point):
        raise RuntimeError('CapCut moved or lost focus before Export.')

    def target_under_cursor():
        cursor = wintypes.POINT()
        if user.GetCursorPos(ctypes.byref(cursor)) and (cursor.x, cursor.y) == point:
            return current_target()
        return None

    click_at(*point, InputTarget(pid, 'CapCut Export'), foreground=target_under_cursor)

    deadline = time.monotonic() + 600
    last_size = 0
    while time.monotonic() < deadline:
        check_cancelled()
        if output.is_symlink():
            raise RuntimeError('CapCut export verification requires a regular local file.')
        if output.is_file():
            size = output.stat().st_size
            if size and size == last_size and verify_media(output).ok:
                check_cancelled()
                return output
            last_size = size
        time.sleep(0.5)
    raise RuntimeError(f'CapCut was asked to export, but no playable MP4 was verified at {output}. '
                       'Check CapCut before retrying.')
