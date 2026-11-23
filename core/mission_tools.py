"""The tools JARVIS may use while it works towards a goal.

WHAT THIS IS
    A mission is one goal the owner gave. To reach it, JARVIS can call a
    small number of named tools. This module is the catalogue of those
    tools, and every one of them is bound to something that already
    exists in JARVIS: the real memory service, the real research reader,
    the real system readings and the real allowlisted launcher.

WHAT THIS IS NOT
    * It is not a general scripting surface. There is no "run this
      command" tool. A tool that is not in
      this catalogue does not exist for the model.
    * A tool does not decide anything. It runs one real thing and reports
      what really happened. Whether the owner allowed it is decided by
      `core.mission`, not here.
    * Nothing here invents a value. A reading that cannot be taken is
      reported as unavailable, exactly as the underlying service reports
      it.

THE TWO KINDS OF TOOL
    A tool is either read-only or it changes something. A read-only tool
    reports what is already there, so it can run without interrupting the
    owner. A tool that changes something needs the owner's approval, and
    the approval is asked for by the mission runner through the same
    gateway every other action in JARVIS uses.
"""
from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import operator
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import time

#: How many characters a file read may return.
MAX_FILE_CHARACTERS = 20_000

#: How many characters a fetched page may return.
MAX_PAGE_CHARACTERS = 8_000

#: The largest number of entries a directory listing may return.
MAX_DIRECTORY_ENTRIES = 200


class ToolError(RuntimeError):
    """A tool could not do what it was asked to do.

    The message is written for the owner, because the same message is
    shown in the HUD and handed back to the model as an observation. It
    says what went wrong and never what was done instead.
    """


@dataclass(frozen=True)
class Tool:
    """One named capability, with the shape of the arguments it takes.

    `parameters` is a JSON Schema for the arguments, so the same
    description can be shown to the model and to the owner. `read_only`
    is the safety decision: a read-only tool only reports, so it runs
    without an approval, and anything else needs the owner's approval
    before it runs.
    """

    name: str
    description: str
    parameters: dict
    read_only: bool
    run: object
    returns: str = ''
    accepts_checkpoint: bool = False

    def summary(self, arguments: dict) -> str:
        """One line that says what this call is about.

        The approval the owner sees names the exact call, so an approval
        cannot be reused for a different one by accident.
        """
        parts = []
        for key in sorted(arguments):
            value = arguments[key]
            if isinstance(value, str):
                text = value if len(value) <= 80 else value[:77] + '...'
            else:
                text = str(value)
            parts.append(f'{key}={text}')
        detail = ' '.join(parts)
        return f'{self.name}({detail})' if detail else f'{self.name}()'


@dataclass
class ToolRegistry:
    """The tools one mission may use.

    The registry is the boundary between what the model may ask for and
    what JARVIS can actually do. A tool that is not registered cannot be
    called, and a registered tool can only be called with the arguments
    its schema describes.
    """

    tools: dict = field(default_factory=dict)
    root: Path | None = None

    def register(self, tool: Tool) -> Tool:
        if tool.name in self.tools:
            raise ValueError(f'The tool {tool.name} is already registered.')
        self.tools[tool.name] = tool
        return tool

    def get(self, name: str):
        """The tool with this name, or None when there is no such tool."""
        if not isinstance(name, str):
            return None
        return self.tools.get(name)

    def names(self) -> list:
        """Every tool name, in registration order."""
        return list(self.tools)

    def read_only_names(self) -> list:
        """The names of the tools that only report."""
        return [name for name, tool in self.tools.items() if tool.read_only]

    def describe(self) -> str:
        """The catalogue, written for the model's instructions."""
        lines = []
        for tool in self.tools.values():
            kind = 'read-only' if tool.read_only else 'changes something and needs approval'
            lines.append(f'- {tool.name} ({kind}): {tool.description}')
            lines.append(f'  arguments: {tool.parameters}')
            if tool.returns:
                lines.append(f'  returns: {tool.returns}')
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # argument checking

    def check_arguments(self, tool: Tool, arguments: dict) -> dict:
        """Check the arguments against the tool's schema.

        Only the types the schema names are accepted, and an argument
        that the schema does not describe is refused rather than
        ignored: a tool that is called with something it did not ask for
        is a mistake worth surfacing.
        """
        if not isinstance(arguments, dict):
            raise ToolError('The arguments must be a JSON object.')
        schema = tool.parameters or {}
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        for key in required:
            if key not in arguments:
                raise ToolError(f'{tool.name} needs the argument {key}.')
        for key, value in arguments.items():
            if key not in properties:
                raise ToolError(f'{tool.name} does not take the argument {key}.')
            expected = properties[key].get('type')
            if expected == 'string' and not isinstance(value, str):
                raise ToolError(f'The argument {key} must be text.')
            if expected == 'integer' and (not isinstance(value, int) or isinstance(value, bool)):
                raise ToolError(f'The argument {key} must be a whole number.')
            if expected == 'array' and not isinstance(value, list):
                raise ToolError(f'The argument {key} must be a list.')
            if expected == 'boolean' and not isinstance(value, bool):
                raise ToolError(f'The argument {key} must be true or false.')
            if expected == 'object' and not isinstance(value, dict):
                raise ToolError(f'The argument {key} must be an object.')
            if expected == 'string' and 'enum' in properties[key]:
                if value not in properties[key]['enum']:
                    allowed = ', '.join(str(item) for item in properties[key]['enum'])
                    raise ToolError(f'The argument {key} must be one of: {allowed}.')
        return arguments

    # ------------------------------------------------------------------
    # the safe path helpers

    def resolve_inside_root(self, path: str) -> Path:
        """Resolve a path and refuse anything outside the mission root.

        The mission root is the one place the mission may look. A path
        that leaves it is refused, and a link is refused as well, because
        a link is a way out of the root that does not look like one.
        """
        if self.root is None:
            raise ToolError('This mission has no folder to read from.')
        root = Path(self.root).expanduser().resolve()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.is_symlink():
            raise ToolError('A link is not read here. Choose the real file or folder.')
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise ToolError('That path is outside the mission folder.')
        return resolved


# ----------------------------------------------------------------------
# the tools themselves


def _current_time(_arguments: dict) -> str:
    """The time on this computer, as it is."""
    now = datetime.now().astimezone()
    return f'{now.isoformat(timespec="seconds")} ({now.tzname()})'


def _system_status(_arguments: dict) -> str:
    """The real CPU, RAM, disk, GPU and temperature readings."""
    # The import is here so that this module stays usable without a
    # desktop, and so the readings are only taken when they are asked for.
    from desktop.system_metrics import format_snapshot, snapshot

    return format_snapshot(snapshot())


def _make_memory_tools(service):
    """The tools that read and write the owner's own memory."""

    def search(arguments: dict) -> str:
        query = (arguments.get('query') or '').strip()
        if not query:
            raise ToolError('Give a query to search for.')
        limit = arguments.get('limit', 5)
        limit = max(1, min(int(limit), 20))
        found = service.search(query, limit=limit)
        if not found:
            return f'No memory matches {query!r}.'
        lines = []
        for item in found:
            lines.append(f'- {item.title} ({item.created}) [{", ".join(item.tags) or "no tags"}]')
            lines.append(f'  {item.body[:400]}')
        return '\n'.join(lines)

    def remember(arguments: dict) -> str:
        title = (arguments.get('title') or '').strip()
        body = (arguments.get('body') or '').strip()
        if not title:
            raise ToolError('A memory needs a title.')
        if not body:
            raise ToolError('A memory needs some text.')
        tags = arguments.get('tags') or []
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ToolError('The tags must be a list of words.')
        saved = service.remember(title, body, tags)
        return f'Saved the memory {saved.title!r}.'

    return search, remember


def _research_fetch(arguments: dict) -> str:
    """Read one public page over HTTPS."""
    from research.research import ResearchError, fetch

    url = (arguments.get('url') or '').strip()
    if not url:
        raise ToolError('Give the address of the page to read.')
    try:
        page = fetch(url)
    except ResearchError as error:
        raise ToolError(str(error)) from None
    text = page.text[:MAX_PAGE_CHARACTERS]
    if page.truncated:
        text += '\n\n[the page was cut short]'
    head = f'# {page.title}\nSource: {page.url}\n\n' if page.title else f'Source: {page.url}\n\n'
    return head + text


def _launch_app(arguments: dict) -> str:
    """Launch an allowlisted app and verify its foreground process."""
    from automation.windows import launch_app, launch_is_foreground

    name = arguments['app']
    try:
        request = launch_app(name)
        # Windows may return from process creation before its window is ready.
        deadline = time.monotonic() + 1.0
        while True:
            if launch_is_foreground(request):
                return f'{name} opened. Windows confirmed its foreground process (PID {request.pid}).'
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    except (ValueError, OSError, RuntimeError) as error:
        raise ToolError(str(error)) from None
    raise ToolError(f'{request} Its window could not be verified. Check Windows before retrying.')


def _type_notepad(arguments: dict) -> str:
    from automation.desktop_tasks import VerifiedEdit, type_into_target

    try:
        result = type_into_target('Notepad', arguments['text'])
    except (ValueError, OSError, RuntimeError) as error:
        raise ToolError(str(error)) from None
    if not isinstance(result, VerifiedEdit):
        raise ToolError(f'{result} Inspect Notepad before retrying.')
    return str(result)


def _export_text(registry: ToolRegistry, arguments: dict) -> str:
    name = arguments['filename']
    text = arguments['text']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.txt', name, re.IGNORECASE):
        raise ToolError('Use a simple .txt filename with letters, digits, underscores or dashes.')
    if Path(name).is_reserved():
        raise ToolError('Choose a filename that is not reserved by Windows.')
    if not 1 <= len(text) <= MAX_FILE_CHARACTERS:
        raise ToolError(f'Export between 1 and {MAX_FILE_CHARACTERS} characters.')
    target = registry.resolve_inside_root(name)
    try:
        payload = text.encode('utf-8')
        with target.open('x+b') as output:
            output.write(payload)
            output.flush()
            output.seek(0)
            if output.read(len(payload) + 1) != payload:
                raise OSError('File readback did not match.')
    except FileExistsError:
        raise ToolError('That filename already exists. Choose a new filename.') from None
    except (OSError, UnicodeError) as error:
        raise ToolError(f'Export failed: {error}') from None
    return f'Created and verified UTF-8 text file {target}.'


def _browser_draft(arguments: dict, check) -> str:
    """Populate one draft field in an isolated, approved browser session."""
    from automation.browser import BrowserAction, BrowserSession, origin

    url, label, text = (arguments[key] for key in ('url', 'label', 'text'))
    if not 1 <= len(label) <= 200 or not 1 <= len(text) <= 4000:
        raise ToolError('Use a field label up to 200 characters and draft text up to 4,000.')

    async def fill(profile):
        session = BrowserSession(profile)
        try:
            _, _, document = await session.perform(BrowserAction('open', url), None, check)
            status, evidence, _ = await session.perform(
                BrowserAction('fill', label, text), document, check)
            if status != 'verified':
                raise ToolError('The draft field could not be verified.')
            return f'{evidence} The browser session closed after the draft check.'
        finally:
            await session.close()

    from playwright.async_api import Error as PlaywrightError

    try:
        origin(url)
        with TemporaryDirectory(prefix='jarvis-browser-draft-') as profile:
            return asyncio.run(fill(profile))
    except (ValueError, OSError, PlaywrightError) as error:
        raise ToolError(f'Browser draft could not be verified ({type(error).__name__}).') from None


def _make_file_tools(registry: ToolRegistry):
    """The tools that look at the mission folder."""

    def list_directory(arguments: dict) -> str:
        path = arguments.get('path') or '.'
        target = registry.resolve_inside_root(path)
        if not target.is_dir():
            raise ToolError('That is not a folder.')
        entries = sorted(target.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        if not entries:
            return 'The folder is empty.'
        lines = []
        for entry in entries[:MAX_DIRECTORY_ENTRIES]:
            kind = 'file' if entry.is_file() else 'folder'
            size = f', {entry.stat().st_size} bytes' if entry.is_file() else ''
            lines.append(f'- {entry.name} ({kind}{size})')
        if len(entries) > MAX_DIRECTORY_ENTRIES:
            lines.append(f'- ... and {len(entries) - MAX_DIRECTORY_ENTRIES} more')
        return '\n'.join(lines)

    def read_text_file(arguments: dict) -> str:
        path = (arguments.get('path') or '').strip()
        if not path:
            raise ToolError('Give the path of the file to read.')
        target = registry.resolve_inside_root(path)
        if not target.is_file():
            raise ToolError('That file is not there.')
        limit = arguments.get('max_characters', MAX_FILE_CHARACTERS)
        limit = max(1, min(int(limit), MAX_FILE_CHARACTERS))
        try:
            text = target.read_text(encoding='utf-8', errors='replace')
        except OSError as error:
            raise ToolError(f'The file could not be read: {error}') from None
        if len(text) > limit:
            return text[:limit] + f'\n\n[the file was cut short at {limit} characters]'
        return text

    return list_directory, read_text_file


#: The arithmetic a mission may do, and nothing else.
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

#: The largest number an expression may reach.
MAX_EXPRESSION_VALUE = 10 ** 12


def _evaluate_expression(arguments: dict) -> str:
    """Do an arithmetic calculation, and nothing else."""
    expression = (arguments.get('expression') or '').strip()
    if not expression:
        raise ToolError('Give the calculation to do.')
    if len(expression) > 200:
        raise ToolError('That calculation is too long.')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        raise ToolError('That calculation could not be read.') from None

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ToolError('Only numbers can be calculated.')
            return node.value
        if isinstance(node, ast.BinOp):
            handler = _BINARY_OPERATORS.get(type(node.op))
            if handler is None:
                raise ToolError('That operator is not allowed.')
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 64 or abs(left) > 10 ** 6):
                raise ToolError('That power is too large to calculate.')
            try:
                value = handler(left, right)
            except (ZeroDivisionError, OverflowError):
                raise ToolError('That calculation has no answer.') from None
            if abs(value) > MAX_EXPRESSION_VALUE:
                raise ToolError('That result is too large.')
            return value
        if isinstance(node, ast.UnaryOp):
            handler = _UNARY_OPERATORS.get(type(node.op))
            if handler is None:
                raise ToolError('That operator is not allowed.')
            return handler(evaluate(node.operand))
        raise ToolError('Only numbers and arithmetic can be calculated.')

    result = evaluate(tree)
    return f'{expression} = {result}'


def build_registry(*, root=None, memory=None) -> ToolRegistry:
    """The standard catalogue of mission tools.

    `memory` is the owner's memory service. Without it, the two memory
    tools are not registered at all, rather than registered and broken.
    """
    registry = ToolRegistry(root=Path(root) if root else None)

    registry.register(Tool(
        name='current_time',
        description='The time and the date on this computer.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True,
        run=_current_time,
        returns='The local date and time.',
    ))

    registry.register(Tool(
        name='system_status',
        description='The real CPU, RAM, disk, GPU and temperature readings of this PC.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True,
        run=_system_status,
        returns='The current system readings.',
    ))

    registry.register(Tool(
        name='evaluate_expression',
        description='Calculate a number, for example (120 * 3) / 4.',
        parameters={'type': 'object', 'properties': {
            'expression': {'type': 'string', 'description': 'The calculation to do.'}},
            'required': ['expression']},
        read_only=True,
        run=_evaluate_expression,
        returns='The calculation and its result.',
    ))

    registry.register(Tool(
        name='research_fetch',
        description='Read one public web page and return its text.',
        parameters={'type': 'object', 'properties': {
            'url': {'type': 'string', 'description': 'The https address of the page.'}},
            'required': ['url']},
        read_only=True,
        run=_research_fetch,
        returns='The page title and its text.',
    ))

    registry.register(Tool(
        name='launch_app',
        description='Open an approved application on this PC.',
        parameters={'type': 'object', 'properties': {
            'app': {'type': 'string', 'enum': ['Notepad', 'Calculator'],
                    'description': 'The application to open.'}},
            'required': ['app']},
        read_only=False,
        run=_launch_app,
        returns='A verified Windows foreground process, or a verification error.',
    ))

    registry.register(Tool(
        name='browser_draft',
        description='Open an approved HTTPS page in a temporary session and verify one filled draft field.',
        parameters={'type': 'object', 'properties': {
            'url': {'type': 'string'}, 'label': {'type': 'string'},
            'text': {'type': 'string'}}, 'required': ['url', 'label', 'text']},
        read_only=False,
        run=_browser_draft,
        returns='Field readback confirmation. The session closes after verification.',
        accepts_checkpoint=True,
    ))

    registry.register(Tool(
        name='type_notepad',
        description='Insert literal text into the focused Notepad editor and verify the edit.',
        parameters={'type': 'object', 'properties': {'text': {'type': 'string'}},
                    'required': ['text']},
        read_only=False,
        run=_type_notepad,
        returns='Editor readback confirmation. Saving is a separate operation.',
    ))
    if registry.root is not None:
        registry.register(Tool(
            name='export_text',
            description='Create a new UTF-8 text file inside the mission folder from supplied text.',
            parameters={'type': 'object', 'properties': {
                'filename': {'type': 'string'}, 'text': {'type': 'string'}},
                'required': ['filename', 'text']},
            read_only=False,
            run=lambda arguments: _export_text(registry, arguments),
            returns='The path and byte readback confirmation.',
        ))

    list_directory, read_text_file = _make_file_tools(registry)
    registry.register(Tool(
        name='list_directory',
        description='List the files and folders in the mission folder.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'A folder inside the mission folder.'}},
            'required': []},
        read_only=True,
        run=list_directory,
        returns='The entries in the folder.',
    ))
    registry.register(Tool(
        name='read_text_file',
        description='Read one text file from the mission folder.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'The file to read.'},
            'max_characters': {'type': 'integer', 'description': 'How much to read.'}},
            'required': ['path']},
        read_only=True,
        run=read_text_file,
        returns='The text of the file.',
    ))

    if memory is not None:
        search, remember = _make_memory_tools(memory)
        registry.register(Tool(
            name='memory_search',
            description='Search the owner\'s saved notes for something.',
            parameters={'type': 'object', 'properties': {
                'query': {'type': 'string', 'description': 'What to look for.'},
                'limit': {'type': 'integer', 'description': 'How many notes to return.'}},
                'required': ['query']},
            read_only=True,
            run=search,
            returns='The notes that match, best first.',
        ))
        registry.register(Tool(
            name='memory_remember',
            description='Save a note in the owner\'s memory.',
            parameters={'type': 'object', 'properties': {
                'title': {'type': 'string', 'description': 'The title of the note.'},
                'body': {'type': 'string', 'description': 'What the note says.'},
                'tags': {'type': 'array', 'description': 'Words that describe the note.'}},
                'required': ['title', 'body']},
            read_only=False,
            run=remember,
            returns='The note that was saved.',
        ))

    return registry


__all__ = ['MAX_EXPRESSION_VALUE', 'MAX_FILE_CHARACTERS', 'MAX_PAGE_CHARACTERS',
           'Tool', 'ToolError', 'ToolRegistry', 'build_registry']
