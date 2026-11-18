"""A system-wide key that brings JARVIS up.

The shortcut the owner sets here works in every application, not only
while the JARVIS window has the focus. The key does one thing: it brings
JARVIS to the front, so the owner can talk to it. It does not open the
microphone, because the microphone only ever follows the explicit
consent the owner gave inside the application.

How it is done on each system:

* **Windows.** The key is registered with the operating system through
  ``RegisterHotKey``, and the ``WM_HOTKEY`` message that follows is
  caught by a Qt native event filter. The registration fails with a
  clear reason when another program already owns the key, and that
  reason is shown to the owner rather than swallowed.
* **Everywhere else.** The operating system cannot be asked to hand out
  a key from here without extra native libraries, so the setting is still
  read, still shown and still saved, and the application says plainly
  that the key does nothing on this system. It never pretends the key
  works.

The rules that decide whether a shortcut may be used -- which
combinations Windows keeps for itself, which ones other applications
usually take, and how a written shortcut is turned into a key -- are
plain Python with no system in them, so they are tested on any machine.
"""
from __future__ import annotations

import re
import sys

# The modifier flags RegisterHotKey understands.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
#: Ask Windows not to repeat the message while the key is held down.
MOD_NOREPEAT = 0x4000

#: The window message Windows sends when a registered key is pressed.
WM_HOTKEY = 0x0312
#: The identifier this application owns. Any number under 0xBFFF is fine.
HOTKEY_ID = 0xB01

MODIFIER_NAMES = {
    'ctrl': MOD_CONTROL,
    'control': MOD_CONTROL,
    'alt': MOD_ALT,
    'shift': MOD_SHIFT,
    'win': MOD_WIN,
    'meta': MOD_WIN,
    'super': MOD_WIN,
    'cmd': MOD_WIN,
    'command': MOD_WIN,
}

#: The keys that do not carry a letter or a digit.
NAMED_KEYS = {
    'space': 0x20,
    'enter': 0x0D,
    'return': 0x0D,
    'tab': 0x09,
    'esc': 0x1B,
    'escape': 0x1B,
    'insert': 0x2D,
    'delete': 0x2E,
    'del': 0x2E,
    'home': 0x24,
    'end': 0x23,
    'pageup': 0x21,
    'pagedown': 0x22,
    'backspace': 0x08,
    'up': 0x26,
    'down': 0x28,
    'left': 0x25,
    'right': 0x27,
    'pause': 0x13,
    'printscreen': 0x2C,
    'apps': 0x5E,
}

#: Keys Windows keeps for itself. Taking one of them would break Windows.
WINDOWS_RESERVED = (
    ('Ctrl+Alt+Del', MOD_CONTROL | MOD_ALT, 0x2E),
    ('Alt+Tab', MOD_ALT, 0x09),
    ('Ctrl+Esc', MOD_CONTROL, 0x1B),
    ('Alt+Esc', MOD_ALT, 0x1B),
    ('Ctrl+Shift+Esc', MOD_CONTROL | MOD_SHIFT, 0x1B),
    ('Alt+F4', MOD_ALT, 0x73),
    ('Alt+Space', MOD_ALT, 0x20),
    ('Win+L', MOD_WIN, 0x4C),
    ('Win+D', MOD_WIN, 0x44),
    ('Win+E', MOD_WIN, 0x45),
    ('Win+R', MOD_WIN, 0x52),
    ('F12', 0, 0x7B),
)

#: Keys other applications usually take. These are allowed, but the owner
#: is told, because the key may reach the other application instead.
COMMONLY_TAKEN = (
    ('Ctrl+T', MOD_CONTROL, 0x54),
    ('Ctrl+N', MOD_CONTROL, 0x4E),
    ('Ctrl+W', MOD_CONTROL, 0x57),
    ('Ctrl+Shift+T', MOD_CONTROL | MOD_SHIFT, 0x54),
    ('Ctrl+Shift+J', MOD_CONTROL | MOD_SHIFT, 0x4A),
    ('Ctrl+Shift+I', MOD_CONTROL | MOD_SHIFT, 0x49),
    ('Ctrl+Shift+C', MOD_CONTROL | MOD_SHIFT, 0x43),
    ('F5', 0, 0x74),
    ('F11', 0, 0x7A),
)

#: The shortcut the application starts with.
DEFAULT_SHORTCUT = 'Ctrl+Alt+Space'


class ShortcutError(ValueError):
    """The written shortcut cannot be used."""


class Shortcut:
    """A key with its modifiers, ready to be handed to the operating system."""

    def __init__(self, modifiers: int, virtual_key: int, text: str = ''):
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self.text = text or self.describe()

    def describe(self) -> str:
        """The shortcut written the way a person would say it."""
        names = []
        for name, flag in (('Ctrl', MOD_CONTROL), ('Alt', MOD_ALT),
                           ('Shift', MOD_SHIFT), ('Win', MOD_WIN)):
            if self.modifiers & flag:
                names.append(name)
        key = ''
        for name, code in NAMED_KEYS.items():
            if code == self.virtual_key:
                key = name.capitalize()
                break
        if not key:
            if 0x70 <= self.virtual_key <= 0x87:
                key = f'F{self.virtual_key - 0x6F}'
            else:
                key = chr(self.virtual_key)
        return '+'.join(names + [key])

    def __eq__(self, other):
        return (isinstance(other, Shortcut)
                and other.modifiers == self.modifiers
                and other.virtual_key == self.virtual_key)

    def __hash__(self):
        return hash((self.modifiers, self.virtual_key))

    def __repr__(self):
        return f'Shortcut({self.describe()!r})'


def _virtual_key(name: str):
    """The key code for a written key, or ``None`` when it is not one."""
    lowered = name.lower()
    if lowered in NAMED_KEYS:
        return NAMED_KEYS[lowered]
    if len(name) == 1:
        upper = name.upper()
        if 'A' <= upper <= 'Z':
            return ord(upper)
        if '0' <= name <= '9':
            return ord(name)
    match = re.fullmatch(r'f(\d{1,2})', lowered)
    if match:
        number = int(match.group(1))
        if 1 <= number <= 24:
            return 0x6F + number
    return None


def _is_function_key(name: str) -> bool:
    match = re.fullmatch(r'f(\d{1,2})', name.strip().lower())
    if not match:
        return False
    return 1 <= int(match.group(1)) <= 24


def parse_shortcut(text: str) -> Shortcut:
    """Turn a written shortcut into a key, or explain why it cannot be used."""
    raw = (text or '').strip()
    if not raw:
        raise ShortcutError('Type the key, for example Ctrl+Alt+Space.')
    parts = [part.strip() for part in raw.split('+') if part.strip()]
    if not parts:
        raise ShortcutError('Type the key, for example Ctrl+Alt+Space.')
    modifiers = 0
    key_name = None
    for part in parts:
        lowered = part.lower()
        if lowered in MODIFIER_NAMES:
            modifiers |= MODIFIER_NAMES[lowered]
        elif key_name is None:
            key_name = part
        else:
            raise ShortcutError(f'Only one key can be used, and {part} would be a second one.')
    if key_name is None:
        raise ShortcutError('The key itself is missing from the shortcut.')
    virtual_key = _virtual_key(key_name)
    if virtual_key is None:
        raise ShortcutError(f'{key_name} is not a key this can use.')
    if not modifiers and not _is_function_key(key_name):
        # A bare letter would be taken while the owner types. The function
        # keys are not typed, so they are left alone.
        raise ShortcutError(
            'Add a modifier such as Ctrl or Alt, so the key is not taken while typing.')
    shortcut = Shortcut(modifiers, virtual_key, raw)
    for name, mods, key in WINDOWS_RESERVED:
        if shortcut.modifiers == mods and shortcut.virtual_key == key:
            raise ShortcutError(f'{name} belongs to Windows and cannot be taken.')
    return shortcut


def commonly_taken(shortcut: Shortcut) -> str:
    """The name of an application that usually owns this key, if one does."""
    for name, mods, key in COMMONLY_TAKEN:
        if shortcut.modifiers == mods and shortcut.virtual_key == key:
            return name
    return ''


def shortcut_status(text: str) -> str:
    """A line the owner can read about a written shortcut."""
    try:
        shortcut = parse_shortcut(text)
    except ShortcutError as error:
        return str(error)
    taken = commonly_taken(shortcut)
    if taken:
        return f'{taken} is used by other applications. It may not reach JARVIS.'
    return f'{shortcut.describe()} is ready.'


class GlobalHotkey:
    """Registers one key with the operating system and reports what happened.

    The object is honest about the system it runs on. On a system where
    the key cannot be registered, ``register`` says so and the caller
    shows that to the owner.
    """

    def __init__(self, callback):
        self.callback = callback
        self._shortcut = None
        self._native_filter = None
        self._registered = False

    @staticmethod
    def supported() -> bool:
        """True when this system can be asked for a key."""
        return sys.platform == 'win32'

    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def shortcut(self):
        return self._shortcut

    def register(self, text: str) -> str:
        """Take the key. The returned line says what happened."""
        self.unregister()
        try:
            shortcut = parse_shortcut(text)
        except ShortcutError as error:
            return str(error)
        if not self.supported():
            self._shortcut = shortcut
            return ('This system cannot give a key to the operating system, so the '
                    'shortcut is saved but does nothing here.')
        message = self._register_windows(shortcut)
        if message:
            return message
        self._shortcut = shortcut
        self._registered = True
        return f'{shortcut.describe()} now brings JARVIS up from anywhere.'

    def unregister(self):
        """Give the key back."""
        if self._registered:
            try:
                self._release_windows()
            except Exception:
                pass
        self._registered = False
        self._shortcut = None

    # -- the Windows part ------------------------------------------------

    def _register_windows(self, shortcut: Shortcut) -> str:
        import ctypes
        from ctypes import wintypes

        from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                         wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL

        if self._native_filter is None:
            class _WindowsFilter(QAbstractNativeEventFilter):
                def __init__(self, owner):
                    super().__init__()
                    self.owner = owner

                def nativeEventFilter(self, event_type, message):
                    if event_type == b'windows_generic_MSG':
                        msg = wintypes.MSG.from_address(int(message))
                        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                            self.owner.callback()
                            return True, 0
                    return False, 0

            self._native_filter = _WindowsFilter(self)
            QCoreApplication.instance().installNativeEventFilter(self._native_filter)

        if not user32.RegisterHotKey(None, HOTKEY_ID, shortcut.modifiers | MOD_NOREPEAT,
                                     shortcut.virtual_key):
            code = ctypes.get_last_error()
            if code == 1409:
                return 'Another program already holds this key. Choose another one.'
            if code == 0:
                return 'Windows refused the key without giving a reason.'
            return f'Windows refused the key (error {code}).'
        return ''

    def _release_windows(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey(None, HOTKEY_ID)
        if self._native_filter is not None:
            from PySide6.QtCore import QCoreApplication

            application = QCoreApplication.instance()
            if application is not None:
                application.removeNativeEventFilter(self._native_filter)
            self._native_filter = None
