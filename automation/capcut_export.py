"""Export the open CapCut Desktop project to an approved local MP4."""
import ctypes
from ctypes import wintypes
from pathlib import Path, PureWindowsPath
import sys
import time

import psutil

from automation import win_controls
from automation.input import InputTarget, click_at, press_key, type_text
from video_studio.verification import ffprobe_executable, verify_media


# CapCut Desktop 9.9 paints its own controls. Coordinates are relative to
# the settings form at 96 DPI. Its completion screen has a different layout.
_FORM_SIZE = (720, 663)
_NAME_FIELD = (520, 100)
_FOLDER_BUTTON = (689, 138)
_EXPORT_BUTTON = (590, 640)
_VIDEO_CHECK = (362, 192)
_SYNC_CHECK = (365, 507)
_SYNC_PIXEL = (362, 507)
_GA_ROOT = 2
_GA_ROOTOWNER = 3
_GW_ENABLEDPOPUP = 6


def new_mp4(path):
    output = Path(path).expanduser()
    if not output.is_absolute() or output.suffix.casefold() != '.mp4':
        raise ValueError('Choose an absolute MP4 path.')
    if (PureWindowsPath(output.name).is_reserved()
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in output.name)
            or output.stem.endswith((' ', '.'))):
        raise ValueError('Choose a valid Windows filename for the CapCut MP4.')
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('Choose an existing export folder.')
    output = parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new MP4 filename. Existing files will not be overwritten.')
    return output


def _window_api():
    user = ctypes.WinDLL('user32', use_last_error=True)
    signatures = {
        'SetThreadDpiAwarenessContext': ([ctypes.c_void_p], ctypes.c_void_p),
        'GetDpiForWindow': ([wintypes.HWND], wintypes.UINT),
        'GetWindow': ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
        'GetWindowTextW': ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        'GetClassNameW': ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        'GetWindowRect': ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        'GetDC': ([wintypes.HWND], wintypes.HDC),
        'ReleaseDC': ([wintypes.HWND, wintypes.HDC], ctypes.c_int),
        'WindowFromPoint': ([wintypes.POINT], wintypes.HWND),
        'GetAncestor': ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
        'SetCursorPos': ([ctypes.c_int, ctypes.c_int], wintypes.BOOL),
        'GetCursorPos': ([ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        'IsWindowVisible': ([wintypes.HWND], wintypes.BOOL),
        'IsWindowEnabled': ([wintypes.HWND], wintypes.BOOL),
        'IsIconic': ([wintypes.HWND], wintypes.BOOL),
        'ShowWindow': ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        'SetForegroundWindow': ([wintypes.HWND], wintypes.BOOL),
        'GetDlgCtrlID': ([wintypes.HWND], ctypes.c_int),
    }
    for name, (args, result) in signatures.items():
        function = getattr(user, name)
        function.argtypes = args
        function.restype = result
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


class _CapCutExportUI:
    def __init__(self, user, check_cancelled):
        self.user = user
        self.check = check_cancelled
        gdi = ctypes.WinDLL('gdi32', use_last_error=True)
        self.get_pixel = gdi.GetPixel
        self.get_pixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.get_pixel.restype = wintypes.DWORD
        self.editor = self._find_editor()
        self.pid = win_controls.window_process(self.editor)
        self.target = InputTarget(self.pid, 'CapCut Export')

    def _title(self, hwnd):
        return self._window_text(self.user.GetWindowTextW, hwnd)

    def _class(self, hwnd):
        return self._window_text(self.user.GetClassNameW, hwnd)

    @staticmethod
    def _window_text(get_text, hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        get_text(hwnd, buffer, len(buffer))
        return buffer.value

    def _find_editor(self):
        editors = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _):
            if (self.user.IsWindowVisible(hwnd) and self._title(hwnd) == 'CapCut'
                    and self.user.GetAncestor(hwnd, _GA_ROOTOWNER) == hwnd):
                try:
                    process = psutil.Process(win_controls.window_process(hwnd) or -1)
                    if process.name().casefold() == 'capcut.exe':
                        editors.append(hwnd)
                except (psutil.Error, OSError, ValueError):
                    pass
            return True

        self.user.EnumWindows(collect, 0)
        if len(editors) != 1:
            raise RuntimeError('Open one CapCut Desktop project window and try again.')
        return editors[0]

    def _wait(self, read, message, *, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            result = read()
            if result:
                return result
            time.sleep(0.08)
        raise RuntimeError(message)

    def _foreground(self):
        hwnd = win_controls.foreground_window()
        if (hwnd and win_controls.window_process(hwnd) == self.pid
                and self.user.GetAncestor(hwnd, _GA_ROOTOWNER) == self.editor):
            return hwnd
        return None

    def _popup(self):
        popup = self.user.GetWindow(self.editor, _GW_ENABLEDPOPUP)
        if (popup and popup != self.editor and self.user.IsWindowVisible(popup)
                and (self._title(popup).startswith('Export-') or self._class(popup) == '#32770')):
            return popup
        return None

    def _form_point(self, hwnd, coordinate, *, sync=None):
        if not hwnd or not self._title(hwnd).startswith('Export-'):
            return None
        dpi = self.user.GetDpiForWindow(hwnd)
        rect = wintypes.RECT()
        if not dpi or not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None

        def scaled(value):
            return round(value * dpi / 96)

        width, height = _FORM_SIZE
        if (rect.right - rect.left, rect.bottom - rect.top) != (scaled(width), scaled(height)):
            return None

        def point(x, y):
            return rect.left + scaled(x), rect.top + scaled(y)

        dc = self.user.GetDC(None)
        if not dc:
            return None
        try:
            if (not _teal(self.get_pixel(dc, *point(*_VIDEO_CHECK)))
                    or not _teal(self.get_pixel(dc, *point(*_EXPORT_BUTTON)))
                    or (sync is not None and not sync(
                        self.get_pixel(dc, *point(*_SYNC_PIXEL))))):
                return None
        finally:
            self.user.ReleaseDC(None, dc)

        target = point(*coordinate)
        hit = self.user.WindowFromPoint(wintypes.POINT(*target))
        return target if self.user.GetAncestor(hit, _GA_ROOT) == hwnd else None

    def _editor_ready(self):
        foreground = self._foreground()
        # The editor's own floating tutorials can have focus. Ctrl+E is
        # application-wide, but a modal dialog must never receive it.
        return (foreground and self._title(foreground) == 'CapCut'
                and self.user.IsWindowEnabled(self.editor) and self._popup() is None)

    def _form_ready(self, form):
        return self._foreground() in (self.editor, form) and self._popup() in (None, form)

    def _current_form(self):
        form = self._popup() or self._foreground()
        if form and self._form_ready(form) and self._form_point(form, _EXPORT_BUTTON):
            return form
        return None

    def _guard(self, ready):
        self.check()
        if not ready():
            raise RuntimeError('CapCut focus or the expected control changed. Check the project and retry.')
        return self.pid

    def _key(self, key, ready):
        press_key(key, self.target, foreground=lambda: self._guard(ready))

    def _type(self, text, ready):
        type_text(text, self.target, foreground=lambda: self._guard(ready))

    def _click(self, form, coordinate, *, sync=None):
        def locate():
            if self._form_ready(form):
                return self._form_point(form, coordinate, sync=sync)
            return None

        self.check()
        point = locate()
        if point is None or not self.user.SetCursorPos(*point):
            raise RuntimeError('CapCut lost focus or its Export controls could not be verified.')

        def cursor_on_target():
            cursor = wintypes.POINT()
            return (self.user.GetCursorPos(ctypes.byref(cursor))
                    and (cursor.x, cursor.y) == point and locate() == point)

        click_at(*point, self.target, foreground=lambda: self._guard(cursor_on_target))

    def _folder_picker(self):
        hwnd = self._foreground()
        if (hwnd and self._class(hwnd) == '#32770'
                and self._title(hwnd) == 'Select exporting path'):
            return hwnd
        return None

    def _choose_folder(self, form, folder):
        self._click(form, _FOLDER_BUTTON)
        picker = self._wait(self._folder_picker, 'CapCut did not open its export folder picker.')

        def picker_ready():
            return self._folder_picker() == picker

        def address_field():
            if picker_ready():
                focus = win_controls.focused_control(picker)
                if focus and self._class(focus).casefold() == 'edit':
                    return focus
            return None

        self._key('alt+d', picker_ready)
        address = self._wait(address_field, 'The export folder address could not be located.')

        def address_ready():
            return address_field() == address

        self._key('ctrl+a', address_ready)
        self._type(str(folder), address_ready)
        if win_controls.contents(address) != str(folder):
            raise RuntimeError('The export folder could not be entered in CapCut.')
        self._key('enter', address_ready)
        self._key('alt+d', picker_ready)
        address = self._wait(address_field, 'The selected export folder could not be read.')
        chosen = win_controls.contents(address)
        if not chosen or not Path(chosen).is_absolute() or Path(chosen).resolve() != folder:
            raise RuntimeError('CapCut did not navigate to the approved export folder.')

        def select_focused():
            if not picker_ready():
                return False
            focus = win_controls.focused_control(picker)
            return bool(focus and self._class(focus) == 'Button'
                        and self.user.GetDlgCtrlID(focus) == 1)

        self._key('alt+n', picker_ready)
        self._key('tab', picker_ready)
        self._wait(select_focused, 'The Select Folder button could not be verified.')
        self._key('space', select_focused)
        if self._wait(self._current_form, 'CapCut did not return to Export settings.') != form:
            raise RuntimeError('CapCut switched to a different Export dialog.')

    def export(self, output):
        self.check()
        if self.user.IsIconic(self.editor):
            self.user.ShowWindow(self.editor, 9)  # SW_RESTORE
        self.user.SetForegroundWindow(self._popup() or self.editor)
        self._wait(self._foreground, 'Bring the open CapCut project to the front and try again.',
                   timeout=25)
        form = self._current_form()
        if form is None:
            if not self._editor_ready():
                raise RuntimeError('Return to the open CapCut timeline and close any blocking dialogs.')
            self._key('ctrl+e', self._editor_ready)
            form = self._wait(
                self._current_form,
                'CapCut did not open a supported Export form. Open a timeline with video in CapCut 9.9.',
            )

        self._choose_folder(form, output.parent)
        self._click(form, _NAME_FIELD)

        def form_ready():
            return self._current_form() == form

        self._key('ctrl+a', form_ready)
        self._type(output.stem, form_ready)
        if self._form_point(form, _SYNC_CHECK, sync=_teal):
            self._click(form, _SYNC_CHECK, sync=_teal)
        if not self._form_point(form, _EXPORT_BUTTON, sync=_unchecked):
            raise RuntimeError('JARVIS could not verify that CapCut’s space sync is off.')
        new_mp4(output)
        self._click(form, _EXPORT_BUTTON, sync=_unchecked)


def save_open_capcut_export(path, check_cancelled):
    """Open CapCut Export, apply the approved destination, and verify its MP4."""
    if sys.platform != 'win32':
        raise RuntimeError('CapCut Desktop export is available on Windows only.')
    output = new_mp4(path)
    ffprobe_executable()
    user = _window_api()
    # The screen DC and cursor use physical pixels. Use the same coordinate
    # space for window geometry and hit testing regardless of process DPI mode.
    previous = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:
        raise RuntimeError('JARVIS could not read the display scaling for CapCut.')
    try:
        _CapCutExportUI(user, check_cancelled).export(output)
    finally:
        user.SetThreadDpiAwarenessContext(previous)

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
