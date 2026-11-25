"""Run existing JARVIS actions for the native Mark LVII plugin."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.gateway import Gateway
from automation import calculator, desktop_tasks, windows
from core.runtime_profile import data_directory
from core.store import Store
from developer_studio.codex_task import run_local_tests, split_test_command
from developer_studio.editors import editor_status, open_project_in_editor
from developer_studio.inspection import inspect_project
from developer_studio.projects import configured_launchers, find_project, load_projects, project_status
from security.policy import Action, Policy


def prepare(store, args):
    kind = args.get('operation')
    if kind == 'projects':
        names = [project.name for project in load_projects(store)]
        return {'result': 'Saved JARVIS projects: ' + ', '.join(names[:30]) if names
                else 'There are no saved projects in this JARVIS profile.'}

    value = args.get('value', '')
    if not isinstance(value, str) or len(value) > 2200 or '\x00' in value:
        raise ValueError('The request value is invalid or too long.')
    project = None
    target = value.strip()
    snapshot = {}
    if kind == 'open_app':
        target = next((app for app in windows.APPS if app.casefold() == target.casefold()), '')
        if not target:
            raise ValueError('Choose Notepad or Calculator.')
    elif kind == 'calculate':
        target = ' '.join(calculator.parse_expression(target))
    elif kind == 'notepad':
        target = value.replace('\r\n', '\n')
        if not target.strip() or len(target) > desktop_tasks.MAX_TEXT:
            raise ValueError('Provide the exact text for Notepad, up to 2,000 characters.')
    elif kind in ('project_status', 'project_open', 'project_inspect', 'project_test'):
        project = find_project(load_projects(store), target)
        if project is None:
            raise ValueError('That project is not saved in JARVIS. Ask for the saved project list.')
        if not project.exists:
            raise ValueError('The saved project folder is unavailable.')
        target = f'{project.name}\n{project.folder.resolve(strict=True)}'
        snapshot = {'path': str(project.folder.resolve(strict=True))}
        if kind == 'project_open':
            configured = next((item for item in configured_launchers(store)
                               if item['name'].casefold() == project.editor.casefold()), None)
            status = editor_status(project.editor, configured)
            if not status['installed']:
                raise ValueError('The saved project editor is unavailable.')
            snapshot['editor'] = status.get('path') or status.get('command') or project.editor
            snapshot['configured'] = configured
            target += f'\nEditor: {project.editor} ({snapshot["editor"]})'
        if kind == 'project_test':
            if not split_test_command(project.test_command):
                raise ValueError('That project has no saved test command.')
            target += '\nRun configured tests: ' + project.test_command
    else:
        raise ValueError('This JARVIS operation is unavailable in Mark.')
    payload = {'operation': kind, 'target': target, 'snapshot': snapshot}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {'action': payload, 'digest': digest, 'project': project}


def wait_for(find, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = find()
        if result:
            return result
        time.sleep(0.1)
    raise RuntimeError('Windows did not verify the expected foreground application.')


def execute(store, prepared):
    action = prepared['action']
    kind, target = action['operation'], action['target']
    project = prepared['project']
    if kind == 'open_app':
        windows.launch_app(target)
        if target == 'Calculator':
            wait_for(calculator.foreground_calculator)
        else:
            wait_for(lambda: desktop_tasks.target_is_foreground(target))
        return f'Verified {target} is open and active.'
    if kind == 'notepad':
        windows.launch_app('Notepad')
        wait_for(lambda: desktop_tasks.target_is_foreground('Notepad'))
        return desktop_tasks.type_into_target('Notepad', target)
    if kind == 'calculate':
        windows.launch_app('Calculator')
        foreground = wait_for(calculator.foreground_calculator)
        value = calculator.calculate_in_window(target, foreground, check=lambda: None)
        return f'Verified Calculator result: {target} = {value}.'
    folder = Path(action['snapshot']['path'])
    if kind == 'project_open':
        return open_project_in_editor(project.editor, folder, action['snapshot']['configured'])
    if kind == 'project_test':
        state, _ = run_local_tests(folder, project.test_command, timeout=75)
        return f'Project {project.name}: tests {state}.'
    if kind == 'project_inspect':
        findings = inspect_project(folder).problems_text()
        return f'Static inspection of {project.name}: {findings[:500]}'
    status = project_status(project)
    return (f'{project.name} is available. Editor: {project.editor}. '
            f'Uncommitted changes: {status["uncommitted"]}. '
            f'Tests configured: {"yes" if project.test_command else "no"}.')


def handle(store, request):
    prepared = prepare(store, request['arguments'])
    if 'result' in prepared:
        return prepared
    action = prepared['action']
    if request['mode'] == 'prepare':
        return {'target': action['target'], 'digest': prepared['digest']}
    if request['mode'] != 'execute' or request.get('digest') != prepared['digest']:
        raise ValueError('JARVIS approval no longer matches this action. Ask again to review it.')
    policy = Policy()
    result = Gateway(policy, store).run(
        Action('mark:' + action['operation'], action['target'], prepared['digest']),
        lambda _action: True,  # Mark invoked this private worker after its HUD confirmation.
        lambda: str(execute(store, prepared)),
    )
    return {'result': result}


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(12000))
        os.environ.pop('JARVIS_DEVELOPMENT_PROFILE', None)
        if request.get('development') is True:
            profile = os.path.normcase(str(ROOT.resolve()))
            os.environ['JARVIS_DEVELOPMENT_PROFILE'] = hashlib.sha256(os.fsencode(profile)).hexdigest()[:24]
        response = handle(Store(data_directory() / 'history.sqlite3'), request)
    except sqlite3.Error:
        response = {'error': 'The JARVIS profile could not be opened. Check the configured profile and permissions.'}
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as error:
        response = {'error': str(error)[:600]}
    print(json.dumps(response, ensure_ascii=True))


if __name__ == '__main__':
    main()
