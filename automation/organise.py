"""Tidying a folder the owner chose.

WHAT THIS IS FOR
    A folder that has been downloaded into collects everything in one
    place. This puts the files into folders by kind, and nothing else.

WHAT IT WILL NOT DO
    * It never looks outside the one folder the owner chose. The plan is
      made from that folder's own top level, and a file in a subfolder is
      left where it is.
    * It never overwrites a file. When a file of the same name is in the
      way, the file stays where it is and the report says so.
    * It never moves a file that looks like a secret, and it never moves
      a hidden file or a link. Those stay where they are.
    * It never moves anything before the owner has seen the plan. The
      plan says what would move and where; the owner approves that plan,
      and only that plan is carried out.
    * It is bounded: at most so many files, and it refuses a folder that
      is not a real folder.

WHAT MOVES WHERE
    Documents, images, archives, code and media each go into a folder of
    that name inside the chosen folder. Anything else stays in place,
    because a file that does not fit a kind is better left alone than
    guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

#: The kinds of file that are moved, and the suffix that belongs to each.
CATEGORIES = (
    ('documents', frozenset({
        '.pdf', '.docx', '.doc', '.txt', '.md', '.markdown', '.rst', '.rtf',
        '.odt', '.csv', '.xlsx', '.xls', '.pptx', '.ppt',
    })),
    ('images', frozenset({
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.tif', '.tiff',
    })),
    ('archives', frozenset({
        '.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz', '.tgz',
    })),
    ('code', frozenset({
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.kt', '.c', '.cpp', '.h',
        '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.sh', '.ps1', '.bat',
        '.cmd', '.html', '.css', '.json', '.yml', '.yaml', '.toml', '.xml',
        '.sql', '.gradle', '.kt',
    })),
    ('media', frozenset({
        '.mp3', '.wav', '.m4a', '.flac', '.mp4', '.mov', '.mkv', '.avi', '.webm',
    })),
)

#: The most files one plan may move.
MAX_FILES = 500

#: The name of a file that looks like it holds a secret.
_SECRET_RE = re.compile(
    r'(^|/)(\.env(\..*)?|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|.*\.(pem|key|p12|pfx|keystore|jks)|'
    r'.*(secret|credential|password|passwd|token|api[_-]?keys?).*'
    r'\.(json|ya?ml|toml|ini|cfg|conf|txt|env|properties|xml))$',
    re.IGNORECASE)


class OrganiseError(ValueError):
    """A folder cannot be tidied."""


@dataclass
class OrganisePlan:
    """What would move, and where."""

    folder: str
    moves: list = field(default_factory=list)
    left_alone: list = field(default_factory=list)
    truncated: bool = False

    @property
    def move_count(self) -> int:
        return len(self.moves)

    def as_dict(self) -> dict:
        return {
            'folder': self.folder,
            'moves': [{'from': frm, 'to': to} for frm, to in self.moves],
            'left_alone': list(self.left_alone),
            'truncated': self.truncated,
        }


def category_of(path: Path) -> str:
    """The folder a file belongs in, or '' when it does not fit any kind."""
    suffix = path.suffix.casefold()
    if not suffix:
        return ''
    for name, suffixes in CATEGORIES:
        if suffix in suffixes:
            return name
    return ''


def plan_organise(folder, *, limit: int = MAX_FILES) -> OrganisePlan:
    """Say what would move, and where. Nothing is moved."""
    root = Path(folder).expanduser()
    plan = OrganisePlan(folder=str(root))
    if not root.is_dir():
        raise OrganiseError('That folder is not there.')
    if root.is_symlink():
        raise OrganiseError('Choose a real folder, not a link.')
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError as error:
        raise OrganiseError(f'That folder could not be read: {error}') from None
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            # Folders and links are left exactly where they are.
            plan.left_alone.append(entry.name)
            continue
        if entry.name.startswith('.') or _SECRET_RE.search(entry.name):
            plan.left_alone.append(entry.name)
            continue
        name = category_of(entry)
        if not name:
            plan.left_alone.append(entry.name)
            continue
        if len(plan.moves) >= limit:
            plan.truncated = True
            plan.left_alone.append(entry.name)
            continue
        target = root / name / entry.name
        if target.exists():
            # A file of the same name is already there. Nothing is
            # overwritten, and the report says so.
            plan.left_alone.append(entry.name)
            continue
        plan.moves.append((entry.name, str(target)))
    return plan


def organise(plan: OrganisePlan) -> dict:
    """Carry out the plan the owner approved.

    Only the moves that are in the plan happen. A file that cannot be
    moved is left where it is and named in the report, so the owner
    knows exactly what happened.
    """
    root = Path(plan.folder)
    moved = []
    failed = []
    for name, target in plan.moves:
        source = root / name
        destination = Path(target)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                failed.append({'file': name, 'why': 'a file of that name was already there'})
                continue
            source.replace(destination)
            moved.append({'file': name, 'to': str(destination)})
        except OSError as error:
            failed.append({'file': name, 'why': str(error)})
    return {
        'folder': str(root),
        'moved': moved,
        'failed': failed,
        'left_alone': list(plan.left_alone),
        'truncated': plan.truncated,
    }


def plan_text(plan: OrganisePlan) -> str:
    """The plan as the owner reads it."""
    lines = [f'{plan.move_count} file(s) would move in {plan.folder}.']
    if not plan.moves:
        lines.append('Nothing needs moving there.')
    else:
        by_folder = {}
        for name, target in plan.moves:
            by_folder.setdefault(Path(target).parent.name, []).append(name)
        for folder, names in sorted(by_folder.items()):
            lines.append(f'{folder}: ' + ', '.join(sorted(names)))
    if plan.left_alone:
        lines.append(f'{len(plan.left_alone)} file(s) stay where they are: '
                     + ', '.join(sorted(plan.left_alone)[:12])
                     + ('…' if len(plan.left_alone) > 12 else '') + '.')
    if plan.truncated:
        lines.append('There were more files than one plan may move, so some were left alone.')
    return '\n'.join(lines)


def result_text(result: dict) -> str:
    """What happened, as the owner reads it."""
    lines = [f'{len(result["moved"])} file(s) moved in {result["folder"]}.']
    for item in result['moved']:
        lines.append('  ' + item['file'] + ' → ' + Path(item['to']).parent.name)
    if result['failed']:
        lines.append(f'{len(result["failed"])} file(s) could not be moved:')
        for item in result['failed']:
            lines.append(f'  {item["file"]} — {item["why"]}')
    if result['left_alone']:
        lines.append(f'{len(result["left_alone"])} file(s) were left where they were.')
    if result['truncated']:
        lines.append('There were more files than one run may move, so some were left alone.')
    return '\n'.join(lines)
