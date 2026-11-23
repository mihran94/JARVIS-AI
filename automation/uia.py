"""UI Automation: reading the controls of a window, and finding them by name.

WHAT THIS IS
    Windows tells an application what its controls are, through UI
    Automation. This module reads that tree for one window and turns it
    into plain Python objects, so the rest of JARVIS can look for a
    button, a menu or a field by the name the owner can see.

    The tree is read from the process the owner named, or from the
    foreground window. It is a **read**: nothing here clicks, types or
    changes anything.

WHAT THIS IS NOT
    * It is not a scraping layer. It reads the accessibility tree that
      the application publishes, not the pixels.
    * It does not invent a control. A control that the tree does not
      have is not found, and the report says so.
    * It does not act. The actions live in `automation.input`, and they
      check the focus again before every one of them.
    * It does not run on anything but Windows. On another system every
      entry point says so plainly.

THE RUNTIME
    The Windows tree comes from the .NET `UIAutomationClient` assembly
    through pythonnet, which `setup.cmd` already installs. The .NET
    part is isolated behind `load_client()`, so the parts of this
    module that decide *what to look for* can be exercised without
    Windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sys

#: How deep the tree is read by default.
DEFAULT_DEPTH = 5

#: How many controls one read may return.
MAX_ELEMENTS = 400

#: The control types the assistant can name. A name that is not here is
#: refused rather than passed to Windows as a guess.
CONTROL_TYPES = (
    'Button', 'Edit', 'Document', 'Text', 'ComboBox', 'List', 'ListItem',
    'Menu', 'MenuItem', 'MenuBar', 'CheckBox', 'RadioButton', 'Tab',
    'TabItem', 'Tree', 'TreeItem', 'Window', 'Dialog', 'Pane', 'Group',
    'Slider', 'Spinner', 'ProgressBar', 'ToolBar', 'StatusBar', 'Header',
    'DataItem', 'Image', 'Hyperlink', 'SplitButton', 'Custom',
)

#: The names of the controls that mean a dialog is in the way.
DIALOG_TYPES = ('Dialog', 'Window')


class UiaUnavailable(RuntimeError):
    """The UI Automation tree could not be read."""


@dataclass
class UiaElement:
    """One control the application published."""

    name: str = ''
    control_type: str = ''
    automation_id: str = ''
    class_name: str = ''
    process_id: int = 0
    value: str = ''
    enabled: bool = True
    offscreen: bool = False
    children: list = field(default_factory=list)

    def matches(self, *, name: str = '', control_type: str = '',
                automation_id: str = '') -> bool:
        """Whether this control is the one that was asked for."""
        if name and name.casefold() not in self.name.casefold():
            return False
        if control_type and control_type.casefold() != self.control_type.casefold():
            return False
        if automation_id and automation_id != self.automation_id:
            return False
        return True

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'control_type': self.control_type,
            'automation_id': self.automation_id,
            'class_name': self.class_name,
            'process_id': self.process_id,
            'value': self.value,
            'enabled': self.enabled,
            'offscreen': self.offscreen,
            'children': [child.as_dict() for child in self.children],
        }

    def describe(self) -> str:
        """The control as the owner reads it."""
        parts = [self.control_type or 'Control']
        if self.name:
            parts.append(f'"{self.name}"')
        if self.automation_id:
            parts.append(f'id={self.automation_id}')
        if not self.enabled:
            parts.append('disabled')
        if self.offscreen:
            parts.append('off screen')
        if self.value:
            parts.append(f'value={self.value[:120]}')
        return ' '.join(parts)


def flatten(elements) -> list:
    """Every control in a tree, in the order it was read."""
    out = []
    for element in elements:
        out.append(element)
        out.extend(flatten(element.children))
    return out


def find(elements, *, name: str = '', control_type: str = '',
         automation_id: str = '', visible_only: bool = False) -> list:
    """The controls that match what was asked for."""
    if control_type and control_type not in CONTROL_TYPES:
        raise ValueError(f'Unknown control type: {control_type}')
    matches = []
    for element in flatten(elements):
        if visible_only and element.offscreen:
            continue
        if element.matches(name=name, control_type=control_type,
                           automation_id=automation_id):
            matches.append(element)
    return matches


def describe(elements) -> str:
    """A tree as the owner reads it."""
    lines = []

    def walk(items, depth):
        for element in items:
            lines.append('  ' * depth + element.describe())
            walk(element.children, depth + 1)

    walk(elements, 0)
    return '\n'.join(lines)


def unexpected_dialogs(elements, expected_titles=()) -> list:
    """The dialogs that are in the way.

    A dialog that the owner did not expect means another program asked
    something, and the action must stop rather than click through it.
    """
    wanted = {title.casefold() for title in expected_titles}
    found = []
    for element in flatten(elements):
        if element.control_type not in DIALOG_TYPES:
            continue
        if element.name and element.name.casefold() in wanted:
            continue
        found.append(element)
    return found


# ── the Windows runtime ───────────────────────────────────────────────────


def load_client():
    """The .NET UI Automation client, on Windows only.

    Everything that touches .NET is behind this one function, so the
    rest of the module can be exercised on a machine that has no
    Windows in it.
    """
    if sys.platform != 'win32':
        raise UiaUnavailable('UI Automation is available on Windows only.')
    try:
        import clr
    except ImportError:
        raise UiaUnavailable('pythonnet is needed for UI Automation. '
                              'Run setup.cmd on this computer.') from None
    for assembly in ('UIAutomationClient', 'UIAutomationTypes'):
        try:
            clr.AddReference(assembly)
        except Exception:
            raise UiaUnavailable('Windows UI Automation is not available here.') from None
    try:
        from System.Windows.Automation import AutomationElement
    except Exception:
        raise UiaUnavailable('Windows UI Automation could not be loaded.') from None
    return AutomationElement


def _property(element, name, default=''):
    """One property of a .NET automation element."""
    try:
        current = element.GetCurrentPropertyValue(name)
    except Exception:
        return default
    if current is None:
        return default
    return str(current)


def _read(element, depth, remaining) -> UiaElement:
    """Turn one .NET element into a `UiaElement`."""
    node = UiaElement(
        name=_property(element, 'Name'),
        control_type=_property(element, 'ControlType').split(' ')[-1].strip('[]'),
        automation_id=_property(element, 'AutomationId'),
        class_name=_property(element, 'ClassName'),
        process_id=_property(element, 'ProcessId') or 0,
        value=_property(element, 'ValuePattern', '') if False else '',
    )
    try:
        node.enabled = bool(element.CurrentIsEnabled)
    except Exception:
        node.enabled = True
    try:
        node.offscreen = bool(element.CurrentIsOffscreen)
    except Exception:
        node.offscreen = False
    if depth <= 0 or remaining[0] <= 0:
        return node
    try:
        walker = element.FindAll
    except Exception:
        return node
    try:
        children = walker(lambda child: True)
    except Exception:
        return node
    try:
        count = children.Length
    except Exception:
        return node
    for index in range(min(int(count), MAX_ELEMENTS)):
        remaining[0] -= 1
        if remaining[0] <= 0:
            break
        try:
            child = children.Item(index)
        except Exception:
            break
        node.children.append(_read(child, depth - 1, remaining))
    return node


def read_tree(*, process_id: int = 0, title: str = '', depth: int = DEFAULT_DEPTH) -> list:
    """The control tree of a window.

    Without a process or a title, the foreground window is read. The
    tree is what Windows publishes; a control the application does not
    publish is not in it.
    """
    if depth < 1 or depth > 12:
        raise ValueError('The tree depth must be between 1 and 12.')
    automation = load_client()
    from System import Array  # noqa: F401  (the type is needed by the .NET call)
    from System.Windows.Automation import TreeScope

    root = None
    if process_id:
        try:
            condition = automation.ProcessIdCondition(process_id)
            windows = automation.RootElement.FindAll(TreeScope.Children, condition)
            if windows.Length:
                root = windows.Item(0)
        except Exception:
            root = None
    if root is None and title:
        try:
            condition = automation.NameProperty(title)
            windows = automation.RootElement.FindAll(TreeScope.Children, condition)
            if windows.Length:
                root = windows.Item(0)
        except Exception:
            root = None
    if root is None:
        try:
            root = automation.FocusedElement
        except Exception:
            root = None
    if root is None:
        try:
            root = automation.RootElement
        except Exception:
            root = None
    if root is None:
        raise UiaUnavailable('No window was found to read.')
    remaining = [MAX_ELEMENTS]
    return [_read(root, depth, remaining)]


def foreground_process() -> int:
    """The process id of the window in front, or 0."""
    from automation.win_controls import foreground_process as process_id

    return process_id() or 0


__all__ = ['CONTROL_TYPES', 'DEFAULT_DEPTH', 'DIALOG_TYPES', 'MAX_ELEMENTS',
           'UiaElement', 'UiaUnavailable', 'describe', 'find', 'flatten',
           'foreground_process', 'load_client', 'read_tree', 'unexpected_dialogs']
