"""Export the open CapCut Desktop project to an approved local MP4."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path, PureWindowsPath
import sys
import time

import psutil

from automation import win_controls
from automation.input import InputTarget, click_at, press_key, type_text
from automation.windows import editor_executable, launch_editor
from video_studio.verification import ffprobe_executable, probe, verify_media


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
_PICKER_ADDRESS_ID = 41477
_PROMOTION_SIZE = (356, 508)


def capcut_launcher(configured):
    if not configured:
        local = os.environ.get('LOCALAPPDATA')
        configured = Path(local) / 'CapCut' / 'Apps' / 'CapCut.exe' if local else None
    return editor_executable('CapCut', configured)


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
        'GetDlgItem': ([wintypes.HWND, ctypes.c_int], wintypes.HWND),
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

    def _bind(self, hwnd):
        self.editor = hwnd
        self.pid = win_controls.window_process(hwnd)
        self.target = InputTarget(self.pid, 'CapCut')

    def _title(self, hwnd):
        return self._window_text(self.user.GetWindowTextW, hwnd)

    def _class(self, hwnd):
        return self._window_text(self.user.GetClassNameW, hwnd)

    @staticmethod
    def _window_text(get_text, hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        get_text(hwnd, buffer, len(buffer))
        return buffer.value

    def _windows(self):
        editors = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _):
            size = self._geometry(hwnd) if self.user.IsWindowVisible(hwnd) else None
            if (size and size[2] >= 1000 and self._title(hwnd) == 'CapCut'
                    and self.user.GetAncestor(hwnd, _GA_ROOTOWNER) == hwnd):
                try:
                    process = psutil.Process(win_controls.window_process(hwnd) or -1)
                    if process.name().casefold() == 'capcut.exe':
                        editors.append(hwnd)
                except (psutil.Error, OSError, ValueError):
                    pass
            return True

        self.user.EnumWindows(collect, 0)
        return editors

    def bind_existing(self):
        editors = self._windows()
        if len(editors) != 1:
            raise RuntimeError('Open one CapCut Desktop project window and try again.')
        self._bind(editors[0])

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

    def _guard(self, ready, action):
        self.check()
        if not ready():
            raise RuntimeError(f'CapCut focus changed while trying to {action}. Check the project and retry.')
        return self.pid

    def _key(self, key, ready):
        press_key(key, self.target, foreground=lambda: self._guard(ready, f'press {key}'))

    def _type(self, text, ready):
        type_text(text, self.target, foreground=lambda: self._guard(ready, 'enter the filename'))

    def _click(self, form, coordinate, *, sync=None):
        def locate():
            if self._form_ready(form):
                return self._form_point(form, coordinate, sync=sync)
            return None

        self._click_point(locate, 'click Export controls')

    def _click_point(self, locate, action):
        self.check()
        point = locate()
        if point is None or not self.user.SetCursorPos(*point):
            raise RuntimeError('CapCut lost focus or its Export controls could not be verified.')

        def cursor_on_target():
            cursor = wintypes.POINT()
            return (self.user.GetCursorPos(ctypes.byref(cursor))
                    and (cursor.x, cursor.y) == point and locate() == point)

        click_at(*point, self.target, foreground=lambda: self._guard(cursor_on_target, action))

    def _geometry(self, hwnd):
        if not hwnd:
            return None
        rect = wintypes.RECT()
        dpi = self.user.GetDpiForWindow(hwnd)
        if not dpi or not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        width = round((rect.right - rect.left) * 96 / dpi)
        height = round((rect.bottom - rect.top) * 96 / dpi)
        return rect, dpi, width, height

    def _window_point(self, hwnd, coordinate, markers, *, minimum):
        """Locate a control only when its neighboring layout markers agree."""
        geometry = self._geometry(hwnd)
        if not geometry:
            return None
        rect, dpi, width, height = geometry
        if width < minimum[0] or height < minimum[1]:
            return None

        def point(x, y):
            return rect.left + round(x * dpi / 96), rect.top + round(y * dpi / 96)

        dc = self.user.GetDC(None)
        if not dc:
            return None
        try:
            if not all(test(self.get_pixel(dc, *point(x, y))) for x, y, test in markers):
                return None
        finally:
            self.user.ReleaseDC(None, dc)
        target = point(*coordinate)
        hit = self.user.WindowFromPoint(wintypes.POINT(*target))
        return target if self.user.GetAncestor(hit, _GA_ROOT) == hwnd else None

    def _home_button(self):
        if self._foreground() != self.editor:
            return None

        def cyan(pixel):
            red, green, blue = _rgb(pixel)
            return red < 130 and green > 125 and blue > 145

        return self._window_point(self.editor, (650, 110),
                                  ((300, 62, cyan), (540, 104, cyan), (660, 164, cyan)),
                                  minimum=(1000, 650))

    def _promotion_close(self):
        hwnd = win_controls.foreground_window()
        if (not hwnd or win_controls.window_process(hwnd) != self.pid
                or self._title(hwnd) != 'CapCut' or not self._class(hwnd).endswith('QWindowIcon')):
            return None
        geometry = self._geometry(hwnd)
        if not geometry or geometry[2:] != _PROMOTION_SIZE:
            return None

        def purple(pixel):
            red, green, blue = _rgb(pixel)
            return 135 <= red <= 230 and 105 <= green <= 178 and blue >= 220

        def light_blue(pixel):
            red, green, blue = _rgb(pixel)
            return 130 <= red <= 198 and green >= 210 and blue >= 230

        return self._window_point(hwnd, (338, 17),
                                  ((24, 55, purple), (37, 436, light_blue), (310, 436, purple)),
                                  minimum=_PROMOTION_SIZE)

    def _empty_import(self):
        return self._editor_ready() and self._window_point(
            self.editor, (256, 165), ((253, 161, _teal),), minimum=(1150, 690))

    def _add_video(self):
        if not self._editor_ready():
            return None

        def media_panel(pixel):
            return 25 <= max(_rgb(pixel)) <= 46

        # Open leaves the first card unselected on some builds. The right
        # shoulder and the surrounding Media pane are clear of the thumbnail.
        return self._window_point(self.editor, (243, 209),
                                  ((153, 101, _teal), (255, 185, _unchecked),
                                   (269, 185, media_panel)), minimum=(1150, 690))

    def _import_picker(self):
        hwnd = self._foreground()
        if hwnd and self._class(hwnd) == '#32770' and self._title(hwnd) == 'Select a media resource':
            return hwnd
        return None

    def _import_video(self, source):
        self._key('ctrl+i', self._empty_import)
        picker = self._wait(self._import_picker, 'CapCut did not open its media picker.')
        fields = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _):
            if self._class(hwnd) == 'Edit' and self.user.GetDlgCtrlID(hwnd) == 1148:
                fields.append(hwnd)
            return True

        self.user.EnumChildWindows(picker, collect, 0)
        self.check()
        if (self._import_picker() != picker or len(fields) != 1
                or not win_controls.replace_contents(fields[0], str(source))):
            raise RuntimeError('The import file field could not be verified.')
        self._press_picker_button(picker, 'Open', self._import_picker)
        self._wait(self._add_video, 'CapCut did not show the imported video card.', timeout=15)
        self._click_point(self._add_video, 'add the imported video to the timeline')

    def create_project(self, executable, source):
        self.check()
        launch_editor('CapCut', executable)
        windows = self._wait(self._windows, 'CapCut did not open on this desktop.', timeout=40)
        if len(windows) != 1:
            raise RuntimeError('Leave only CapCut Home open before creating a new project.')
        home, = windows
        self._bind(home)
        self.user.SetForegroundWindow(home)
        self._wait(self._home_button, 'Return to CapCut Home to create a new local project.',
                   timeout=20)
        self._click_point(self._home_button, 'create a new CapCut project')

        def project_window():
            windows = self._windows()
            return windows[0] if len(windows) == 1 and windows[0] != home else None

        self._bind(self._wait(project_window, 'CapCut did not open a new project.', timeout=30))
        self._wait(self._empty_import, 'CapCut’s empty Media panel could not be verified.',
                   timeout=20)
        self._import_video(source)

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
                if (focus and self._class(focus) == 'Edit'
                        and self.user.GetDlgCtrlID(focus) == _PICKER_ADDRESS_ID):
                    return focus
            return None

        self._key('alt+d', picker_ready)
        address = self._wait(address_field, 'The export folder address could not be located.')

        def address_ready():
            return address_field() == address

        self._guard(address_ready, 'enter the folder path')
        if not win_controls.replace_contents(address, str(folder)):
            raise RuntimeError('The export folder could not be entered in CapCut.')
        self._key('enter', address_ready)
        self._wait(lambda: picker_ready() and not address_field(),
                   'CapCut did not finish navigating to the export folder.')
        self._key('alt+d', picker_ready)
        address = self._wait(address_field, 'The selected export folder could not be read.')
        chosen = win_controls.contents(address)
        if not chosen or not Path(chosen).is_absolute() or Path(chosen).resolve() != folder:
            raise RuntimeError('CapCut did not navigate to the approved export folder.')

        self._key('escape', address_ready)
        self._press_picker_button(picker, 'Select Folder', self._folder_picker)
        if self._wait(self._current_form, 'CapCut did not return to Export settings.') != form:
            raise RuntimeError('CapCut switched to a different Export dialog.')
        self._verify_export_folder(form, folder)

    def _verify_export_folder(self, form, folder):
        self._click(form, _FOLDER_BUTTON)
        picker = self._wait(self._folder_picker, 'CapCut did not reopen the selected export folder.')

        def ready():
            return self._folder_picker() == picker

        self._key('alt+d', ready)

        def directory():
            if ready():
                focus = win_controls.focused_control(picker)
                if focus and self.user.GetDlgCtrlID(focus) == _PICKER_ADDRESS_ID:
                    return win_controls.contents(focus)
            return None

        selected = self._wait(directory, 'CapCut did not report its saved export folder.')
        # Escape dismisses address editing, then the picker, without changing
        # the directory. Verify what CapCut actually committed before export.
        self._key('escape', ready)
        if ready():
            self._key('escape', ready)
        self._wait(self._current_form, 'CapCut did not close the export folder picker.')
        if not Path(selected).is_absolute() or Path(selected).resolve() != folder:
            raise RuntimeError('CapCut kept a different export folder. No export was started.')

    def _press_picker_button(self, picker, label, current_picker):
        button = self.user.GetDlgItem(picker, 1)
        self.check()
        caption = win_controls.contents(button) if button else None
        if (current_picker() != picker or not button or not self.user.IsWindowVisible(button)
                or not self.user.IsWindowEnabled(button) or self._class(button) != 'Button'
                or caption not in (label, '&' + label)
                or not win_controls.click_dialog_button(button)):
            raise RuntimeError(f'JARVIS could not activate CapCut’s {label} button.')

    def _open_export(self):
        deadline = time.monotonic() + 25
        requested_at = 0
        requests = 0
        while time.monotonic() < deadline:
            self.check()
            form = self._current_form()
            if form:
                return form
            if self._promotion_close():
                self._click_point(self._promotion_close, 'close the CapCut promotion')
                requested_at = 0
            elif self._editor_ready() and requests < 3 and time.monotonic() - requested_at >= 2:
                if self._editor_export_button():
                    self._click_point(self._editor_export_button, 'open the CapCut Export dialog')
                else:
                    self._key('ctrl+e', self._editor_ready)
                requested_at = time.monotonic()
                requests += 1
            time.sleep(0.15)
        raise RuntimeError('CapCut did not open a supported Export form. Check the timeline and close any blocking dialogs.')

    def _editor_export_button(self):
        if not self._editor_ready():
            return None
        geometry = self._geometry(self.editor)
        if not geometry:
            return None
        width = geometry[2]
        return self._window_point(self.editor, (width - 126, 18),
                                  ((width - 124, 22, _teal), (width - 128, 10, _teal)),
                                  minimum=(1150, 690))

    def export(self, output):
        self.check()
        if self.user.IsIconic(self.editor):
            self.user.ShowWindow(self.editor, 9)  # SW_RESTORE
        self.user.SetForegroundWindow(self._popup() or self.editor)
        form = self._open_export()

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


def save_open_capcut_export(path, check_cancelled, *, source=None, executable=None):
    """Export an open project or build a fresh one from a single approved clip."""
    if sys.platform != 'win32':
        raise RuntimeError('CapCut Desktop export is available on Windows only.')
    output = new_mp4(path)
    ffprobe_executable()
    duration = None
    if source is not None:
        source = Path(source).resolve(strict=True)
        info = probe(source)
        if not info.has_video or info.duration <= 0:
            raise ValueError('Choose a playable local source video.')
        duration = info.duration
    user = _window_api()
    # The screen DC and cursor use physical pixels. Use the same coordinate
    # space for window geometry and hit testing regardless of process DPI mode.
    previous = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:
        raise RuntimeError('JARVIS could not read the display scaling for CapCut.')
    try:
        ui = _CapCutExportUI(user, check_cancelled)
        if source is None:
            ui.bind_existing()
        else:
            ui.create_project(executable, source)
        ui.export(output)
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
            if size and size == last_size:
                verified = verify_media(output, expect_duration=duration)
                if verified.ok:
                    check_cancelled()
                    return output
                if verified.info.has_video:
                    raise RuntimeError(verified.message)
            last_size = size
        time.sleep(0.5)
    raise RuntimeError(f'CapCut was asked to export, but no playable MP4 was verified at {output}. '
                       'Check CapCut before retrying.')
