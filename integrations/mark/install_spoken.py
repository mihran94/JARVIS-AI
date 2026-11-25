"""Install JARVIS M hooks into a compatible user-owned Mark LVII checkout."""
import ast
import json
from pathlib import Path
import shutil
import sys


ANCHOR = '                                self._session_log.append(f"User: {full_in}")'
HOOK = (
    '                                from plugins._jarvis_spoken import dispatch_spoken\n'
    '                                self._keep_task(asyncio.create_task(dispatch_spoken(self, full_in)))'
)
TEXT_ANCHOR = '''            self.ui.write_log("SYS: I'm asleep — say 'Hey Jarvis' or tap WAKE NOW first.")
            return'''
TEXT_HOOK = '''        from plugins._jarvis_spoken import dispatch_spoken, parse_spoken
        if parse_spoken(text):
            asyncio.run_coroutine_threadsafe(dispatch_spoken(self, text, origin='text'), self._loop)
            return'''
PROMPT_ANCHOR = '        parts.append(sys_prompt)'
PROMPT_HOOK = (
    '        parts.append("JARVIS M routes complete Calculator arithmetic and saved project lists locally. '
    'Never call a tool for these commands, open an app as a substitute, or state that the action '
    'was done. Wait for the local JARVIS result and read it aloud when provided.")'
)


def window_title(value):
    original = f'self.setWindowTitle(f"{{{value}}} — {{APP_VERSION}}")'
    changed = f'self.setWindowTitle({value} if {value} == "JARVIS M" else f"{{{value}}} — {{APP_VERSION}}")'
    return original, changed


def prepare(root):
    main = root / 'main.py'
    window = root / 'gui' / 'window.py'
    first = main.read_text(encoding='utf-8-sig')
    second = window.read_text(encoding='utf-8-sig')
    if HOOK not in first:
        if first.count(ANCHOR) != 1:
            raise ValueError('This Mark version does not have the expected completed speech-turn hook.')
        first = first.replace(ANCHOR, ANCHOR + '\n' + HOOK, 1)
    if TEXT_HOOK not in first:
        if first.count(TEXT_ANCHOR) != 1:
            raise ValueError('This Mark version does not have the expected text-command hook.')
        first = first.replace(TEXT_ANCHOR, TEXT_ANCHOR + '\n' + TEXT_HOOK, 1)
    if PROMPT_HOOK not in first:
        if first.count(PROMPT_ANCHOR) != 1:
            raise ValueError('This Mark version does not have the expected voice prompt hook.')
        first = first.replace(PROMPT_ANCHOR, PROMPT_ANCHOR + '\n' + PROMPT_HOOK, 1)
    for value in ('_display', 'display'):
        original, changed = window_title(value)
        if changed in second:
            continue
        if second.count(original) != 1:
            raise ValueError('This Mark version does not have the expected window-title hooks.')
        second = second.replace(original, changed)
    ast.parse(first)
    ast.parse(second)
    config = root / 'config' / 'api_keys.json'
    values = json.loads(config.read_text(encoding='utf-8-sig')) if config.is_file() else {}
    if not isinstance(values, dict):
        raise ValueError('Mark settings must be a JSON object.')
    values['assistant_name'] = 'JARVIS M'
    return ((main, first), (window, second),
            (config, json.dumps(values, ensure_ascii=False, indent=2) + '\n'))


def install(root):
    files = prepare(root)
    # Save the original source once so the owner can roll back the local hooks.
    for path, content in files:
        if path.exists() and path.read_text(encoding='utf-8-sig') == content:
            continue
        if path.suffix == '.py':
            backup = path.with_suffix('.pre-jarvis-m.py.bak')
            if not backup.exists():
                shutil.copy2(path, backup)
        temp = path.with_suffix(path.suffix + '.jarvis-m.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(path)


if __name__ == '__main__':
    install(Path(sys.argv[1]).resolve(strict=True))
