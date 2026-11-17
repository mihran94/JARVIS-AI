"""Ask a coding provider for a change, and write that change into a worktree.

WHO MAY DO THIS
    Only MiniMax and Codex. `providers.routing.require_coding_provider`
    refuses anything else before a request is made, so the rule is not a
    convention that a new call site could forget.

HOW THE CHANGE IS MADE
    The provider is asked for the files it wants to change, as JSON. JARVIS
    writes them itself, inside the isolated worktree, and refuses any path
    that would leave it. The provider never gets a path it can write to, and
    JARVIS never runs a command the provider invented.

    That keeps the two coding providers interchangeable, and it keeps the
    blast radius of a wrong answer inside one worktree that the owner has
    not approved yet.

FAILURES
    A provider failure comes back as the classified diagnosis the provider
    layer already produces. The caller saves the task and offers to resume it;
    switching to the other coding provider is an action the owner approves.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from core.protection import SKIP_DIRS, Protection
from core.updates import UpdateError, validate_update_path
from providers.chat import ProviderError, stream_chat

INSTRUCTION = """You are preparing a change to a Python project.

Answer with one JSON object and nothing else. No explanation before or after it.

{"files": {"<path relative to the project root>": "<the complete new content of that file>"}}

Rules:
- Only files that already exist in the project, or new files under the project root.
- Give the complete new content of every file you change.
- Use forward slashes in paths. Do not use "..".
- Keep the change small and focused on the request.
"""


class CodingAgentError(RuntimeError):
    """The coding provider could not prepare the change."""


def build_messages(goal: str, context: str = '') -> list[dict]:
    """The conversation sent to the coding provider."""
    prompt = INSTRUCTION
    if context:
        prompt += f'\nThe files you may read:\n{context}\n'
    prompt += f'\nThe request:\n{goal}\n'
    return [{'role': 'user', 'content': prompt}]


def parse_proposal(text: str) -> dict:
    """Read the file proposal out of the provider's answer.

    The answer is JSON. A provider that wraps it in a code fence is read as
    well, because that is a common and harmless habit.
    """
    body = (text or '').strip()
    if body.startswith('```'):
        body = re.sub(r'^```[a-zA-Z]*\s*', '', body)
        body = re.sub(r'```\s*$', '', body).strip()
    start = body.find('{')
    end = body.rfind('}')
    if start < 0 or end <= start:
        raise CodingAgentError('The coding provider did not return a change.')
    try:
        payload = json.loads(body[start:end + 1])
    except ValueError:
        raise CodingAgentError('The coding provider returned something that is not a change.') from None
    if not isinstance(payload, dict):
        raise CodingAgentError('The coding provider returned something that is not a change.')
    files = payload.get('files')
    if not isinstance(files, dict) or not files:
        raise CodingAgentError('The coding provider did not propose any file to change.')
    clean = {}
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str):
            raise CodingAgentError('The coding provider returned a file it could not read.')
        clean[name.strip().replace('\\', '/')] = content
    return clean


def ask_minimax(model: str, key: str, goal: str, worktree, *, check, emit=None,
                context: str = '', transport=None) -> dict:
    """Ask MiniMax for the change."""
    try:
        answer = stream_chat('MiniMax', model, key, build_messages(goal, context),
                             check, emit or (lambda part: None), transport=transport)
    except ProviderError:
        raise
    return parse_proposal(answer)


def ask_codex(goal: str, worktree, *, check, executable=None) -> dict:
    """Ask Codex for the change.

    The Codex CLI runs read-only, as it does everywhere else in JARVIS: it
    reads the project and answers, and JARVIS writes what it answers.
    """
    from developer_studio.codex_cli import codex_executable, run_codex

    path = executable or codex_executable()
    answer = run_codex(path, Path(worktree), build_messages(goal)[-1]['content'], check)
    return parse_proposal(answer)


def ask(provider: str, goal: str, worktree, *, check, model: str = '', key: str = '',
        emit=None, transport=None, executable=None) -> dict:
    """Ask the chosen coding provider for the change."""
    from providers.routing import require_coding_provider

    require_coding_provider(provider)
    if provider == 'Codex':
        return ask_codex(goal, worktree, check=check, executable=executable)
    if not key:
        raise CodingAgentError(f'Save the {provider} key before preparing a change.')
    return ask_minimax(model, key, goal, worktree, check=check, emit=emit, transport=transport,
                       context=project_context(worktree))


def apply_files(worktree, files: dict) -> list[str]:
    """Write the proposed files inside the worktree.

    A path that would leave the worktree is refused, and so is a path that
    points at something that is not a regular file.

    A file that holds secrets, or that the project's `.gitignore` keeps out,
    is refused as well. The provider proposes; JARVIS decides.
    """
    root = Path(worktree).resolve()
    protection = Protection(root)
    written = []
    for name, content in files.items():
        try:
            validate_update_path(name)
        except UpdateError as error:
            raise CodingAgentError(f'The coding provider proposed an unsafe path: {name}') from error
        relative = Path(name)
        if (any(part.lower().startswith('.env') or part.lower() in
                {'.git', '.venv', '.updates', 'development'} for part in relative.parts)):
            raise CodingAgentError(f'The coding provider proposed a reserved path: {name}')
        if relative.is_absolute() or '..' in relative.parts:
            raise CodingAgentError(f'The coding provider asked for a file outside the project: {name}')
        relative_name = str(relative).replace('\\', '/')
        if protection.blocked(relative_name):
            raise CodingAgentError(
                f'The coding provider asked to change a protected file: {name} — '
                + protection.reason(relative_name))
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise CodingAgentError(f'The coding provider asked for a file outside the project: {name}')
        if target.exists() and not target.is_file():
            raise CodingAgentError(f'The coding provider asked to replace something that is not a file: {name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        written.append(str(relative).replace('\\', '/'))
    return sorted(written)


def project_context(worktree, limit: int = 120_000) -> str:
    """The readable text files of the project, so the provider knows the code.

    Only text files are read, and only up to a limit, so a large project
    cannot fill the request.

    Files that hold secrets, and files the project's own `.gitignore` keeps
    out, are left out completely. A key must never travel to a provider.
    """
    root = Path(worktree)
    protection = Protection(root)
    parts = []
    used = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        relative = str(path.relative_to(root)).replace('\\', '/')
        if protection.blocked(relative):
            continue
        if path.suffix.lower() not in {'.py', '.md', '.txt', '.json', '.toml', '.cfg', '.ini'}:
            continue
        try:
            content = path.read_text('utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        block = f'--- {relative}\n{content}\n'
        if used + len(block) > limit:
            break
        used += len(block)
        parts.append(block)
    return ''.join(parts)
