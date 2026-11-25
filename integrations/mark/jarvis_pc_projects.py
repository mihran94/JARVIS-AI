"""Native Mark LVII plugin. The Mark HUD owns the approval click."""
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Lock

from core import confirm


PLUGIN = {
    'name': 'jarvis_pc_projects',
    'description': (
        'Use for an explicit owner request to use JARVIS PC tools or JARVIS saved projects, '
        'including Tamil and Tanglish. Use this tool for “JARVIS project list kaattu” or '
        '“JARVIS PC Calculator-la 17 times 23 calculate pannu.” It uses the JARVIS saved '
        'project list and a Mark HUD approval for each operation other than listing. '
        'Do not use it for mentioned apps without an instruction to act.'
    ),
    'parameters': {
        'type': 'OBJECT',
        'properties': {
            'operation': {
                'type': 'STRING',
                'enum': ['projects', 'project_status', 'project_open', 'project_inspect',
                         'project_test', 'open_app', 'calculate', 'notepad'],
            },
            'value': {
                'type': 'STRING',
                'description': ('Saved project name for project operations, Notepad or Calculator '
                                'for open_app, two integers and one +, - or * for calculate, '
                                'or only the exact text to insert for notepad. Omit for projects.'),
            },
        },
        'required': ['operation'],
    },
}

_approval_lock = Lock()


def _bridge(mode, arguments, digest=None):
    config = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8-sig'))
    root = Path(config['root']).resolve(strict=True)
    python = root / '.venv' / 'Scripts' / 'python.exe'
    worker = root / 'scripts' / 'mark_bridge.py'
    if not python.is_file() or not worker.is_file():
        raise RuntimeError('The JARVIS bridge or its Python environment is unavailable.')
    payload = json.dumps({'mode': mode, 'arguments': arguments, 'digest': digest,
                          'development': config.get('development') is True}).encode('utf-8')
    with tempfile.TemporaryFile() as output:
        completed = subprocess.run(
            [str(python), str(worker)], input=payload, stdout=output, stderr=subprocess.DEVNULL,
            cwd=root, timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        output.seek(0)
        if completed.returncode:
            raise RuntimeError('The JARVIS worker failed before reporting a result.')
        response = json.loads(output.read(20000))
    if 'error' in response:
        raise RuntimeError(response['error'])
    return response


def run(parameters, player=None, session_memory=None):
    arguments = {key: parameters[key] for key in ('operation', 'value') if key in parameters}
    try:
        prepared = _bridge('prepare', arguments)
        if 'result' in prepared:
            return prepared['result']
        with _approval_lock:
            if confirm.pending_title():
                return 'Finish or cancel the confirmation already on the Mark HUD first.'
            return confirm.request(
                'jarvis_pc_projects', 'JARVIS · ' + arguments['operation'].replace('_', ' '),
                prepared['target'],
                lambda: _bridge('execute', arguments, prepared['digest'])['result'],
            )
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        return f'JARVIS work did not run: {error}'
