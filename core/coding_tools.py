"""The tools of the coding agent.

WHAT THIS IS
    The catalogue JARVIS uses when the owner asks it to work inside a
    project. Every tool here is bound to one folder, the workspace, and
    every tool that changes something or runs something needs the
    owner's approval first.

    The tools are:

    * **read** — `read_file`, `list_files`, `search_code`,
      `git_status`, `git_diff`, `git_log`, `inspect_dependencies`,
      `artifact_info`;
    * **change** — `write_file`, `edit_file`, `apply_patch`,
      `create_branch`, `create_worktree`;
    * **run** — `run_tests`, `run_command`;
    * **report** — `prepare_pull_request`.

WHAT THIS IS NOT
    * It is not a shell. `run_command` matches the command against a
      fixed list before anything is started, and it runs without a
      command shell, so a model cannot smuggle a pipe or a redirection
      into it.
    * It does not push, merge or deploy. `prepare_pull_request` writes
      a title and a body and shows the diff; it never publishes
      anything.
    * It does not leave the workspace. Every path is checked against the
      project folder, and the protected files are out of reach.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys

from core.coding_workspace import CodingWorkspace, WorkspaceRefused
from core.mission_tools import Tool, ToolError, ToolRegistry

#: The suffixes the running interpreter may be given. The agent uses the
#: same Python that JARVIS runs under, so the project's tests run in the
#: same environment rather than in whichever `python` happens to be first
#: on the path.
INTERPRETER_SUFFIXES = ('-m pytest', '-m unittest', '-V', '--version')

#: The commands the agent may run. A command that is not here is refused
#: before anything is started.
ALLOWED_COMMANDS = (
    'python -V', 'python3 -V', 'python --version', 'python3 --version',
    'pytest', 'python -m pytest', 'python3 -m pytest',
    'node --test', 'node -v', 'npm test', 'npm run build', 'npm run lint',
    'pip list', 'pip show', 'node -p',
    'git status', 'git diff', 'git log', 'git show', 'git branch', 'git rev-parse',
    'cargo build', 'cargo test', 'mvn test', 'gradle test', 'make', 'make test',
)

#: How long a command may run. Five minutes is generous for a test run
#: or a build, and it stops one stuck command from holding a worker for
#: a quarter of an hour.
COMMAND_TIMEOUT = 300

#: The largest command output that is kept.
MAX_OUTPUT_CHARACTERS = 40_000


class CommandRefused(RuntimeError):
    """The command is not one the agent may run."""


@dataclass
class CommandResult:
    """What a command actually did."""

    command: str
    returncode: int
    output: str
    duration_ms: int = 0
    cancelled: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.cancelled

    def as_text(self) -> str:
        """The output as the owner and the model read it."""
        state = 'cancelled' if self.cancelled else (
            'passed' if self.returncode == 0 else f'failed with exit code {self.returncode}')
        return (f'{self.command} — {state}\n\n{self.output}')


def split_arguments(text: str, *, windows=None) -> list:
    """The arguments of a command.

    On Windows a backslash is a path separator and not an escape, so
    `shlex` cannot be used there: it would eat the separators of
    `C:\\Program Files\\Python\\python.exe` and leave a path that no
    longer exists. The quoting rules are the same on both systems: a
    double quote groups, and a space outside a group separates.
    """
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        try:
            return shlex.split(text)
        except ValueError:
            raise CommandRefused('That command could not be read.') from None
    parts = []
    current = ''
    quoted = False
    for character in text:
        if character == '"':
            quoted = not quoted
            continue
        if character.isspace() and not quoted:
            if current:
                parts.append(current)
                current = ''
            continue
        current += character
    if current:
        parts.append(current)
    return parts


def check_command(command: str) -> list:
    """The arguments of a command, when it is one the agent may run."""
    if not isinstance(command, str) or not command.strip():
        raise CommandRefused('Give a command to run.')
    text = command.strip()
    if len(text) > 400:
        raise CommandRefused('That command is too long.')
    for character in ('|', '>', '<', '`', '$', ';', '&', '\n', '\r'):
        if character in text:
            raise CommandRefused(
                'That command has a character that could run something else. '
                'Only a plain command is allowed.')
    arguments = split_arguments(text)
    if not arguments:
        raise CommandRefused('That command could not be read.')
    if not arguments:
        raise CommandRefused('Give a command to run.')
    for allowed in ALLOWED_COMMANDS:
        if text == allowed or text.startswith(allowed + ' '):
            return arguments
    interpreter = _same_interpreter(arguments[0])
    if interpreter:
        rest = ' '.join(arguments[1:])
        for suffix in INTERPRETER_SUFFIXES:
            if rest == suffix or rest.startswith(suffix + ' '):
                return arguments
    raise CommandRefused(
        f'JARVIS may not run {arguments[0]!r}. The commands it may run are: '
        + ', '.join(sorted(ALLOWED_COMMANDS)) + '.')


def _same_interpreter(path: str) -> bool:
    """Whether a path is the interpreter this program is running under."""
    try:
        candidate = os.path.normcase(os.path.abspath(path))
        running = os.path.normcase(os.path.abspath(sys.executable))
    except (OSError, ValueError):
        return False
    if candidate == running:
        return True
    # The Windows launcher is `python.exe` in a virtual environment, and
    # the base interpreter is next to it.
    name = os.path.basename(candidate).casefold()
    return name in ('python.exe', 'python3.exe', 'python') and \
        os.path.dirname(candidate) == os.path.dirname(running)


def run_command(command: str, cwd, *, timeout=COMMAND_TIMEOUT, cancel=None,
                environment=None) -> CommandResult:
    """Run one allowed command in the project, and keep what it printed."""
    import time

    arguments = check_command(command)
    folder = Path(cwd)
    started = time.monotonic()
    process = subprocess.Popen(
        arguments, cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        shell=False, env={**os.environ, **(environment or {})},
        encoding='utf-8', errors='replace')
    collected = []
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                break
            collected.append(line)
            if cancel is not None and cancel():
                process.kill()
                process.wait(timeout=10)
                return CommandResult(command=command, returncode=process.returncode or -1,
                                     output=''.join(collected)[:MAX_OUTPUT_CHARACTERS],
                                     duration_ms=int((time.monotonic() - started) * 1000),
                                     cancelled=True)
        process.wait(timeout=max(1, timeout - int(time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
        return CommandResult(command=command, returncode=-1,
                             output=''.join(collected)[:MAX_OUTPUT_CHARACTERS] + '\n'
                                    '[the command was stopped after the time limit]',
                             duration_ms=int((time.monotonic() - started) * 1000),
                             cancelled=True)
    finally:
        if process.stdout is not None:
            process.stdout.close()
    return CommandResult(command=command, returncode=process.returncode or 0,
                         output=''.join(collected)[:MAX_OUTPUT_CHARACTERS],
                         duration_ms=int((time.monotonic() - started) * 1000))


def git_output(folder, *arguments) -> str:
    """The output of one read-only git command, or an empty string."""
    try:
        result = subprocess.run(['git', *arguments], cwd=str(folder), capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=30,
                                check=False)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout if result.returncode == 0 else ''


# ── the tools ─────────────────────────────────────────────────────────────


def build_coding_registry(workspace: CodingWorkspace, *, runner=None, cancel=None) -> ToolRegistry:
    """The coding agent's tools, bound to one workspace."""
    registry = ToolRegistry(root=workspace.root)
    run = runner or (lambda command: run_command(command, workspace.root, cancel=cancel))

    def read_file(arguments):
        try:
            content = workspace.read_text(arguments['path'])
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError:
            raise ToolError('Give the path of the file to read.') from None
        return content

    def list_files(arguments):
        try:
            found = workspace.list_files(arguments.get('subpath', ''))
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        return '\n'.join(found) if found else 'The folder has no files in it.'

    def search_code(arguments):
        try:
            found = workspace.search(arguments['pattern'], arguments.get('subpath', ''))
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError:
            raise ToolError('Give the text or pattern to search for.') from None
        if not found:
            return 'Nothing in the project matches that.'
        return '\n'.join(f"{item['file']}:{item['line']}: {item['text']}" for item in found)

    def write_file(arguments):
        try:
            name = workspace.write_text(arguments['path'], arguments['content'])
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError as error:
            raise ToolError(f'The argument {error} is needed.') from None
        return f'{name} was written.'

    def edit_file(arguments):
        try:
            name = workspace.edit_file(arguments['path'], arguments['old'], arguments['new'])
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError as error:
            raise ToolError(f'The argument {error} is needed.') from None
        return f'{name} was changed.'

    def apply_patch(arguments):
        try:
            result = workspace.apply_patch(arguments['patch'])
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError:
            raise ToolError('Give the patch to apply.') from None
        return result.as_text()

    def git_status(arguments):
        output = git_output(workspace.root, 'status', '--short', '--branch')
        return output.strip() or 'The working tree is clean.'

    def git_diff(arguments):
        path = arguments.get('path')
        arguments_list = ['diff', '--stat'] if not path else ['diff', '--', path]
        output = git_output(workspace.root, *arguments_list)
        return output.strip() or 'There is no difference to show.'

    def git_log(arguments):
        limit = int(arguments.get('limit', 10))
        limit = max(1, min(limit, 100))
        output = git_output(workspace.root, 'log', f'-{limit}', '--pretty=%h %s')
        return output.strip() or 'This project has no commits yet.'

    def inspect_dependencies(arguments):
        parts = []
        for name in ('requirements.txt', 'pyproject.toml', 'setup.py', 'package.json',
                     'Pipfile', 'environment.yml'):
            path = workspace.root / name
            if not path.is_file():
                continue
            try:
                parts.append(f'--- {name} ---\n'
                             + path.read_text('utf-8', errors='replace')[:4000])
            except OSError:
                continue
        return '\n\n'.join(parts) if parts else 'This project declares no dependencies file.'

    def artifact_info(arguments):
        name = arguments['path']
        try:
            path = workspace.resolve(name)
        except WorkspaceRefused as error:
            raise ToolError(str(error)) from None
        except KeyError:
            raise ToolError('Give the path of the artefact.') from None
        if not path.is_file():
            raise ToolError('That file is not there.')
        data = path.read_bytes()
        info = [f'{path.name}: {len(data):,} bytes',
                f'SHA-256: {hashlib.sha256(data).hexdigest()}']
        try:
            from video_studio.preview import probe_media
            probe = probe_media(path)
        except Exception:
            probe = None
        if probe:
            info.append(probe)
        return '\n'.join(info)

    def run_tests(arguments):
        command = arguments.get('command') or 'python -m pytest'
        result = run(command)
        return result.as_text()

    def run_any(arguments):
        command = arguments['command']
        result = run(command)
        return result.as_text()

    def create_branch(arguments):
        name = arguments['name']
        if not name or '/' in name or name.startswith('-'):
            raise ToolError('Give a branch name without a slash.')
        current = git_output(workspace.root, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
        if current:
            try:
                subprocess.run(['git', 'checkout', '-b', name], cwd=str(workspace.root),
                               capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError) as error:
                raise ToolError(f'The branch could not be created: {error}') from None
        return f'The branch {name} was created.'

    def create_worktree(arguments):
        name = arguments.get('name') or 'jarvis-task'
        target = Path(arguments.get('path') or (workspace.root.parent / f'{workspace.root.name}-{name}'))
        try:
            result = subprocess.run(['git', 'worktree', 'add', '-b', name, str(target)],
                                    cwd=str(workspace.root), capture_output=True, text=True,
                                    timeout=60, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            raise ToolError(f'The worktree could not be created: {error}') from None
        if result.returncode != 0:
            raise ToolError(f'The worktree could not be created. {result.stderr.strip()[:300]}')
        return f'The worktree was created at {target}. The project folder was not touched.'

    def prepare_pull_request(arguments):
        status = git_output(workspace.root, 'status', '--short').strip()
        diff = git_output(workspace.root, 'diff', '--stat').strip()
        if not status:
            return 'There is nothing to prepare: the working tree is clean.'
        title = (arguments.get('title') or 'The changes made in this project').strip()
        body = (arguments.get('body') or '').strip()
        parts = [f'Title: {title}', '']
        if body:
            parts.extend([body, ''])
        parts.append('Files changed:')
        parts.append(status)
        if diff:
            parts.extend(['', 'Diff:', diff])
        parts.extend(['', 'This was prepared only. Nothing was pushed, and nothing was published.'])
        return '\n'.join(parts)

    registry.register(Tool(
        name='read_file',
        description='Read one file from the project.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'The file to read.'}},
            'required': ['path']},
        read_only=True, run=read_file, returns='The text of the file.'))

    registry.register(Tool(
        name='list_files',
        description='List the files in the project, or in one folder of it.',
        parameters={'type': 'object', 'properties': {
            'subpath': {'type': 'string', 'description': 'A folder inside the project.'}},
            'required': []},
        read_only=True, run=list_files, returns='The files that are there.'))

    registry.register(Tool(
        name='search_code',
        description='Find text or a pattern in the project.',
        parameters={'type': 'object', 'properties': {
            'pattern': {'type': 'string', 'description': 'The text or pattern to look for.'},
            'subpath': {'type': 'string', 'description': 'A folder inside the project.'}},
            'required': ['pattern']},
        read_only=True, run=search_code, returns='Where it was found.'))

    registry.register(Tool(
        name='git_status',
        description='What changed in the project, and which branch it is on.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True, run=git_status, returns='The git status.'))

    registry.register(Tool(
        name='git_diff',
        description='The difference between the files and the last commit.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'One file to show.'}},
            'required': []},
        read_only=True, run=git_diff, returns='The difference.'))

    registry.register(Tool(
        name='git_log',
        description='The recent commits of the project.',
        parameters={'type': 'object', 'properties': {
            'limit': {'type': 'integer', 'description': 'How many commits to show.'}},
            'required': []},
        read_only=True, run=git_log, returns='The commit list.'))

    registry.register(Tool(
        name='inspect_dependencies',
        description='What the project depends on.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True, run=inspect_dependencies, returns='The dependency files.'))

    registry.register(Tool(
        name='artifact_info',
        description='The size and the checksum of a built file, and what it really is.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'The artefact to inspect.'}},
            'required': ['path']},
        read_only=True, run=artifact_info, returns='What the artefact is.'))

    registry.register(Tool(
        name='write_file',
        description='Write a file in the project.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'The file to write.'},
            'content': {'type': 'string', 'description': 'The whole content of the file.'}},
            'required': ['path', 'content']},
        read_only=False, run=write_file, returns='What was written.'))

    registry.register(Tool(
        name='edit_file',
        description='Replace exact text in a file in the project.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'The file to change.'},
            'old': {'type': 'string', 'description': 'The text to replace.'},
            'new': {'type': 'string', 'description': 'The text to put in its place.'}},
            'required': ['path', 'old', 'new']},
        read_only=False, run=edit_file, returns='What was changed.'))

    registry.register(Tool(
        name='apply_patch',
        description='Apply a unified diff to the project.',
        parameters={'type': 'object', 'properties': {
            'patch': {'type': 'string', 'description': 'The diff to apply.'}},
            'required': ['patch']},
        read_only=False, run=apply_patch, returns='Which files were changed.'))

    registry.register(Tool(
        name='create_branch',
        description='Create a branch in the project and move onto it.',
        parameters={'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'The branch name.'}},
            'required': ['name']},
        read_only=False, run=create_branch, returns='What was created.'))

    registry.register(Tool(
        name='create_worktree',
        description='Create an isolated worktree of the project, leaving the folder alone.',
        parameters={'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'The name of the worktree.'},
            'path': {'type': 'string', 'description': 'Where the worktree is put.'}},
            'required': []},
        read_only=False, run=create_worktree, returns='Where the worktree is.'))

    registry.register(Tool(
        name='run_tests',
        description="Run the project's own tests and report what they printed.",
        parameters={'type': 'object', 'properties': {
            'command': {'type': 'string',
                        'description': 'The test command, for example "python -m pytest".'}},
            'required': []},
        read_only=False, run=run_tests, returns='The real output of the test run.'))

    registry.register(Tool(
        name='run_command',
        description='Run one allowed command in the project, such as a build.',
        parameters={'type': 'object', 'properties': {
            'command': {'type': 'string', 'description': 'The command to run.'}},
            'required': ['command']},
        read_only=False, run=run_any, returns='The real output of the command.'))

    registry.register(Tool(
        name='prepare_pull_request',
        description='Write the title and the body of a pull request and show the diff.',
        parameters={'type': 'object', 'properties': {
            'title': {'type': 'string', 'description': 'The title of the pull request.'},
            'body': {'type': 'string', 'description': 'The body of the pull request.'}},
            'required': []},
        read_only=True, run=prepare_pull_request,
        returns='The prepared pull request. Nothing is published.'))

    return registry


__all__ = ['ALLOWED_COMMANDS', 'COMMAND_TIMEOUT', 'CommandRefused', 'CommandResult',
           'build_coding_registry', 'check_command', 'git_output', 'run_command']
