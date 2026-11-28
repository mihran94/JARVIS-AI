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


@dataclass(frozen=True)
class SelectedWindow:
    pid: int
    title: str
    started: float
    handle: int


def parse(message, *, has_selection=False):
    text = addressed_request(message)
    if text.casefold() in ('list installed apps', 'installed apps kaattu'):
        return Request('list')
    if text.casefold() in ('list open windows', 'open windows kaattu'):
        return Request('windows')
    match = re.fullmatch(r'select app (.+)|(.+?) app select pannu', text, re.I)
    if match:
        return Request('select', (match[1] or match[2]).strip())
    if text.casefold() in ('release selected app', 'app release pannu'):
        return Request('release')
    for pattern in (r'open (?:installed )?app (.+)', r'(.+?) app open pannu', r'installed app (.+?) open pannu'):
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
    target = re.fullmatch(r'in app (.+?), (.+)', text, re.I)
    if target:
        return input_command(target[2], target[1].strip())
    if has_selection:
        direct = input_command(text)
        if direct:
            return direct
        if text.casefold() in ('show controls', 'controls kaattu'):
            return Request('inspect')
        match = re.fullmatch(r'click (.+)|(.+?) click pannu', text, re.I)
        if match:
            return Request('click', control=(match[1] or match[2]).strip())
        match = re.fullmatch(r'set (.+?) = (.+)', text, re.I)
        if match:
            return Request('set', control=match[1].strip(), value=match[2])
    return None


def input_command(text, app=''):
    spoken = re.sub(r'\s+', ' ', text.casefold().strip(' .!?'))
    actions = {
        'play this': 'Play', 'play': 'Play', 'play pannu': 'Play',
        'ப்ளே பண்ணு': 'Play', 'இதை ப்ளே பண்ணு': 'Play',
        'pause': 'Pause', 'pause pannu': 'Pause', 'பாஸ் பண்ணு': 'Pause',
        'open timeline': 'Timeline', 'timeline open pannu': 'Timeline',
        'டைம்லைன் ஓபன் பண்ணு': 'Timeline',
        'split at playhead': 'Split', 'playhead-la split pannu': 'Split',
        'playhead-ல கட் பண்ணு': 'Split',
    }
    if spoken in actions:
        return Request('mouse_click', app, actions[spoken])
    selection = re.fullmatch(r'select (.+)|(.+?) (?:select pannu|செலக்ட் பண்ணு)', text.rstrip(' .!?'), re.I)
    if selection:
        label = (selection[1] or selection[2]).strip()
        if label.casefold() not in {'this', 'it', 'இதை', 'இத', 'அதை'}:
            return Request('select_control', app, label)
    click = re.fullmatch(r'mouse click (.+)|(.+?) mouse click pannu', text, re.I)
    if click:
        return Request('mouse_click', app, (click[1] or click[2]).strip())
    key = re.fullmatch(r'(?:keyboard )?press (\S+) in (.+)', text, re.I)
    if key:
        return Request('keyboard_key', app, key[2].strip(), key[1].casefold())
    typed = re.fullmatch(r'(?:keyboard )?type in (.+?) = (.+)', text, re.I)
    if typed:
        return Request('keyboard_text', app, typed[1].strip(), typed[2])
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


def select(name, gateway, confirm, checkpoint):
    checkpoint()
    pid, title, started = resolve_window(name)
    target = None

    def inspect():
        nonlocal target
        checkpoint()
        if psutil.Process(pid).create_time() != started:
            raise InputRefused('The app restarted. Select its window again.')
        app_control.focus_selected(pid, title)
        handle = app_control.win_controls.foreground_window()
        controls = app_control.see_controls(pid, title)
        if not handle or app_control.win_controls.foreground_window() != handle:
            raise InputRefused('The window changed during inspection. Select it again.')
        target = SelectedWindow(pid, title, started, handle)
        return f'Selected {title}.\n{controls}'

    detail = gateway.run(Action('select_app', f'{title} (PID {pid})'), confirm, inspect)
    return target, detail


def run(request, gateway, confirm, checkpoint, *, selected=None):
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

    if request.app:
        pid, title, started = resolve_window(request.app)
    elif selected:
        pid, title, started = selected.pid, selected.title, selected.started
    else:
        raise InputRefused('Select an app first.')
    target = f'{title} (PID {pid})'
    if request.control:
        target += f' — {request.control}'
    if request.verb in ('set', 'keyboard_key', 'keyboard_text'):
        target += f' = {request.value}'

    def operate():
        checkpoint()
        if psutil.Process(pid).create_time() != started:
            raise InputRefused('The selected app restarted. Select it again.')
        app_control.focus_selected(pid, title)

        def guard():
            checkpoint()
            if selected and app_control.win_controls.foreground_window() != selected.handle:
                raise InputRefused('The selected window changed. Select the app again.')

        guard()
        if request.verb == 'inspect':
            return app_control.see_controls(pid, title)
        name, ident = request.control, ''
        if name.startswith('id='):
            name, ident = '', name[3:]
        if request.verb == 'select_control':
            return app_control.select_control(pid, title, name, ident, checkpoint=guard)
        if request.verb == 'mouse_click':
            return app_control.mouse_click(pid, title, name, ident, checkpoint=guard)
        if request.verb in ('keyboard_key', 'keyboard_text'):
            return app_control.keyboard_input(
                pid, title, name, ident,
                text=request.value if request.verb == 'keyboard_text' else None,
                key=request.value if request.verb == 'keyboard_key' else None,
                checkpoint=guard)
        return app_control.use_control(pid, title, name, ident,
                                       text=request.value if request.verb == 'set' else None,
                                       checkpoint=guard)

    status = {
        'click': 'dispatched', 'mouse_click': 'dispatched', 'keyboard_key': 'dispatched',
        'select_control': 'verified', 'set': 'verified', 'keyboard_text': 'verified', 'inspect': 'completed',
    }[request.verb]
    return gateway.run(Action(f'app_{request.verb}', target), confirm, operate, completion_status=status)
