"""Owner-authored commands for installed applications and their published controls."""
from dataclasses import dataclass
from pathlib import PureWindowsPath
import re
import sys

import psutil

from automation import app_control
from automation.input import InputRefused
from automation.inspection import inspect_windows
from core.conversation import addressed_request
from security.policy import Action


@dataclass(frozen=True)
class Request:
    verb: str
    app: str = ''
    control: str = ''
    value: str = ''


def parse(message):
    text = addressed_request(message)
    if text.casefold() in ('list installed apps', 'installed apps kaattu'):
        return Request('list')
    if text.casefold() in ('list open windows', 'open windows kaattu'):
        return Request('windows')
    for pattern in (r'open installed app (.+)', r'installed app (.+?) open pannu'):
        match = re.fullmatch(pattern, text, re.I)
        if match:
            return Request('open', match[1].strip())
    match = re.fullmatch(r'(?:inspect app (.+)|(.+?)-la controls kaattu)', text, re.I)
    if match:
        return Request('inspect', (match[1] or match[2]).strip())
    match = re.fullmatch(r'(.+?)-la (.+?) click pannu', text, re.I)
    if match:
        return Request('click', match[1].strip(), match[2].strip())
    match = re.fullmatch(r'in app (.+?), (click|set) (.+)', text, re.I)
    if match:
        app, verb, label = match.groups()
        if verb.casefold() == 'click':
            return Request('click', app.strip(), label.strip())
        field, sep, value = label.partition(' = ')
        if sep:
            return Request('set', app.strip(), field.strip(), value)
    return None


def installed_items():
    if sys.platform != 'win32':
        raise InputRefused('Installed app discovery requires Windows.')
    from win32com.client import Dispatch
    folder = Dispatch('Shell.Application').NameSpace('shell:AppsFolder')
    if folder is None:
        raise InputRefused('Windows could not open its installed app catalog.')
    return folder.Items()


def installed(name, identity=None):
    matches = [item for item in installed_items()
               if str(item.Name).casefold() == name.casefold()
               and (identity is None or str(item.Path) == identity)]
    if len(matches) != 1:
        raise InputRefused('Choose a unique Windows display name from “list installed apps”.')
    return matches[0]


def resolve_window(name):
    matches = []
    for row in inspect_windows():
        try:
            process = app_control._application(row['pid'])
            started = psutil.Process(row['pid']).create_time()
        except (psutil.Error, InputRefused):
            continue
        aliases = (row['title'], process, PureWindowsPath(process).stem)
        if name.casefold() in (alias.casefold() for alias in aliases):
            matches.append((row['pid'], row['title'], started))
    if len(matches) != 1:
        raise InputRefused('Choose an open process name or a unique full window title from Refresh windows.')
    return matches[0]


def run(request, gateway, confirm, checkpoint):
    checkpoint()
    if request.verb == 'windows':
        return app_control.list_apps()
    if request.verb == 'list':
        names = sorted({str(item.Name) for item in installed_items() if item.Name}, key=str.casefold)
        return '\n'.join(names) or 'No installed applications were listed.'
    if request.verb == 'open':
        item = installed(request.app)
        identity = str(item.Path or '')
        if not identity:
            raise InputRefused('Windows did not identify this installed app.')

        def launch():
            checkpoint()
            installed(request.app, identity).InvokeVerb()
            return f'Windows received the launch request for {request.app}.'

        return gateway.run(Action('open_installed_app', f'{item.Name} ({identity})'),
                           confirm, launch, completion_status='dispatched')

    pid, title, started = resolve_window(request.app)
    target = f'{title} (PID {pid})'
    if request.control:
        target += f' — {request.control}'
    if request.verb == 'set':
        target += f' = {request.value}'

    def operate():
        checkpoint()
        if psutil.Process(pid).create_time() != started:
            raise InputRefused('The selected app restarted. Select it again.')
        app_control.focus_selected(pid, title)
        if request.verb == 'inspect':
            return app_control.see_controls(pid, title)
        name, ident = request.control, ''
        if name.startswith('id='):
            name, ident = '', name[3:]
        return app_control.use_control(pid, title, name, ident,
                                       text=request.value if request.verb == 'set' else None,
                                       checkpoint=checkpoint)

    status = {'click': 'dispatched', 'set': 'verified', 'inspect': 'completed'}[request.verb]
    return gateway.run(Action(f'app_{request.verb}', target), confirm, operate, completion_status=status)
