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
    spoken = re.sub(r'\s+', ' ', text.casefold().strip(' .!?'))
    if spoken in {'select this', 'select it', 'itha select pannu', 'idhai select pannu',
                  'இதை செலக்ட் பண்ணு', 'இத செலக்ட் பண்ணு', 'இதைத் தேர்வு செய்'}:
        return Request('select_pointed')
    if spoken in {'click here', 'mouse click here', 'இங்கே கிளிக் பண்ணு', 'inga click pannu'}:
        return Request('click_pointed')
    if has_selection:
        drag = re.fullmatch(
            r'drag (.+?) (?:into|to) (.+)|(.+?) to (.+?) (?:drag pannu|டிராக் பண்ணு)'
            r'|(.+?)-ஐ (.+?)-க்கு டிராக் பண்ணு', text, re.I)
        if drag:
            source, destination = (value for value in drag.groups() if value is not None)
            return Request('drag', control=source.strip(), value=destination.strip())
        if text.casefold() in ('show controls', 'controls kaattu'):
            return Request('inspect')
        match = re.fullmatch(r'click (.+)|(.+?) click pannu', text, re.I)
        if match:
            return Request('click', control=(match[1] or match[2]).strip())
        match = re.fullmatch(r'set (.+?) = (.+)', text, re.I)
        if match:
            return Request('set', control=match[1].strip(), value=match[2])
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
    pointed = None
    if request.verb in ('select_pointed', 'click_pointed'):
        if not selected or app_control.win_controls.foreground_window() != selected.handle:
            raise InputRefused('Select an app and point at a control in its foreground window.')
        if psutil.Process(pid).create_time() != started:
            raise InputRefused('The selected app restarted. Select it again.')
        pointed = app_control.pointed_control(pid, title, selecting=request.verb == 'select_pointed')
        checkpoint()
        if app_control.win_controls.foreground_window() != selected.handle:
            raise InputRefused('The selected window changed. Select the app again.')
        target += ' — ' + (pointed[0] or pointed[1])
    if request.control:
        target += f' — {request.control}'
    if request.verb == 'set':
        target += f' = {request.value}'
    elif request.verb == 'drag':
        target += f' → {request.value}'

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
        if pointed is not None:
            name, ident, runtime_id = pointed
            action = (app_control.select_control if request.verb == 'select_pointed'
                      else app_control.mouse_click)
            return action(pid, title, name, ident, checkpoint=guard, runtime_id=runtime_id)
        name, ident = request.control, ''
        if name.startswith('id='):
            name, ident = '', name[3:]
        if request.verb == 'drag':
            destination = request.value
            destination_id = ''
            if destination.startswith('id='):
                destination, destination_id = '', destination[3:]
            return app_control.drag_control(pid, title, name, ident, destination=destination,
                                            destination_id=destination_id, checkpoint=guard)
        return app_control.use_control(pid, title, name, ident,
                                       text=request.value if request.verb == 'set' else None,
                                       checkpoint=guard)

    status = {
        'click': 'dispatched', 'set': 'verified', 'inspect': 'completed',
        'select_pointed': 'verified', 'click_pointed': 'dispatched', 'drag': 'verified',
    }[request.verb]
    return gateway.run(Action(f'app_{request.verb}', target), confirm, operate, completion_status=status)
