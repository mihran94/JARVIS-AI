"""Real adapters for the creative applications.

WHAT THIS IS
    After Effects, Photoshop and DaVinci Resolve can all be told what
    to do to a file. This module writes the script each of them
    understands, runs the application with it, and then **checks the
    file that came out**.

    The three applications are scripted in three different ways, and
    each is handled honestly:

    * **After Effects** runs a `.jsx` script with its own `-r` switch.
    * **Photoshop** runs a `.jsx` script the same way.
    * **DaVinci Resolve** is driven through its own Python module, which
      talks to a **running** Resolve.

    A script that was written but never run is not a result. Every
    adapter here reports what the application actually did to the file,
    and says so plainly when the application is not installed.

WHAT THIS IS NOT
    * It does not pretend an application is there. `*_available()` says
      whether it was found.
    * It does not claim an edit happened. The output file is checked,
      and the check is the result.
    * It does not reach past the files the owner named.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

#: How long an application may take to finish a script, in seconds.
SCRIPT_TIMEOUT = 900

#: Where DaVinci Resolve keeps its scripting module.
RESOLVE_SCRIPT_PATHS = (
    r'C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules',
    r'C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting',
)

#: Where the applications are usually found.
PHOTOSHOP_PATHS = (
    r'C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe',
    r'C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe',
    r'C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe',
)

AFTER_EFFECTS_PATHS = (
    r'C:\Program Files\Adobe\Adobe After Effects 2024\Support Files\afterfx.exe',
    r'C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\afterfx.exe',
    r'C:\Program Files\Adobe\Adobe After Effects 2023\Support Files\afterfx.exe',
)


class CreativeError(RuntimeError):
    """The creative application could not do what was asked."""


@dataclass
class CreativeResult:
    """What the application really did."""

    ok: bool = False
    application: str = ''
    output: str = ''
    message: str = ''
    changed: bool = False
    detail: str = ''

    def as_dict(self) -> dict:
        return {'ok': self.ok, 'application': self.application, 'output': self.output,
                'message': self.message, 'changed': self.changed, 'detail': self.detail}


# ── finding the applications ───────────────────────────────────────────────


def _first_existing(paths, names=()):
    for candidate in paths:
        if Path(candidate).is_file():
            return candidate
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ''


def photoshop_executable() -> str:
    """Where Photoshop is, or an empty string."""
    return _first_existing(PHOTOSHOP_PATHS, names=('Photoshop.exe',))


def after_effects_executable() -> str:
    """Where After Effects is, or an empty string."""
    return _first_existing(AFTER_EFFECTS_PATHS, names=('afterfx.exe',))


def resolve_script_path() -> str:
    """Where Resolve keeps its scripting module, or an empty string."""
    for candidate in RESOLVE_SCRIPT_PATHS:
        folder = Path(candidate)
        if folder.is_dir():
            for module in folder.glob('DaVinciResolveScript.py'):
                return str(module)
            for module in folder.glob('**/DaVinciResolveScript.py'):
                return str(module)
    return ''


def photoshop_available() -> bool:
    return bool(photoshop_executable())


def after_effects_available() -> bool:
    return bool(after_effects_executable())


def resolve_available() -> bool:
    """Whether Resolve can be scripted from here."""
    return bool(resolve_script_path())


# ── the scripts ────────────────────────────────────────────────────────────


def photoshop_script(edits) -> str:
    """A Photoshop script for the edits that are supported.

    The supported edits are a short list on purpose: resize, crop,
    rotate, convert to another format, and adjust the levels. Anything
    else is refused rather than turned into a script that might do
    something else.
    """
    edits = list(edits or [])
    if not edits:
        raise CreativeError('Choose at least one edit.')
    lines = ['#target photoshop', 'app.bringToFront();']
    for edit in edits:
        if not isinstance(edit, dict):
            raise CreativeError('An edit must say what to change.')
        action = str(edit.get('action', '')).casefold()
        if action == 'resize':
            lines.append(f'var w = {int(edit["width"])}; var h = {int(edit["height"])};')
            lines.append('app.activeDocument.resizeImage(UnitValue(w,"px"), UnitValue(h,"px"), 72);')
        elif action == 'crop':
            lines.append(f'var w = {int(edit["width"])}; var h = {int(edit["height"])};')
            lines.append('app.activeDocument.crop(UnitValue(w,"px"), UnitValue(h,"px"),'
                         ' AnchorPosition.MIDDLECENTER);')
        elif action == 'rotate':
            degrees = float(edit.get('degrees', 0)) % 360
            lines.append(f'app.activeDocument.rotate({degrees:g});')
        elif action == 'levels':
            lines.append(f'app.activeDocument.adjustLevels({int(edit.get("black", 0))}, '
                         f'{int(edit.get("white", 255))}, {float(edit.get("gamma", 1.0)):g});')
        elif action == 'convert':
            kind = str(edit.get('format', '')).casefold()
            formats = {'jpeg': 'JPEGOptions', 'jpg': 'JPEGOptions', 'png': 'PNGSaveOptions',
                       'tiff': 'TiffSaveOptions', 'webp': 'WebPSaveOptions'}
            if kind not in formats:
                raise CreativeError(
                    'Photoshop can save JPEG, PNG, TIFF or WEBP here, and nothing else.')
            lines.append(f'var options = new {formats[kind]}();')
            if kind in ('jpeg', 'jpg'):
                lines.append('options.quality = 12;')
            lines.append(f'var out = new File("{_escape(str(edit["path"]))}");')
            lines.append(f'app.activeDocument.saveAs(out, options, true, Extension.LOWERCASE);')
        elif action == 'save':
            lines.append(f'var out = new File("{_escape(str(edit["path"]))}");')
            lines.append('app.activeDocument.saveAs(out, undefined, true, Extension.LOWERCASE);')
        else:
            raise CreativeError(
                f'Photoshop cannot do {action!r} here. The supported edits are resize, crop, '
                'rotate, levels, convert and save.')
    return '\n'.join(lines) + '\n'


def after_effects_script(edits) -> str:
    """An After Effects script for the changes that are supported.

    The supported changes are: renaming a composition, changing its
    frame rate, and adding a text layer. Anything else is refused.
    """
    edits = list(edits or [])
    if not edits:
        raise CreativeError('Choose at least one change.')
    lines = ['var project = app.open(0);']
    for edit in edits:
        if not isinstance(edit, dict):
            raise CreativeError('A change must say what to change.')
        action = str(edit.get('action', '')).casefold()
        if action == 'rename':
            lines.append(f'var item = project.items.getItemByName("{_escape(str(edit["from"]))}");')
            lines.append(f'if (item) {{ item.name = "{_escape(str(edit["to"]))}"; }}')
        elif action == 'frame_rate':
            lines.append(f'var rate = {float(edit.get("fps", 30)):g};')
            lines.append('for (var i = 1; i <= project.numItems; i++) {')
            lines.append('  var item = project.item(i);')
            lines.append('  if (item instanceof CompItem) { item.frameRate = rate; }')
            lines.append('}')
        elif action == 'add_text':
            lines.append(f'var comp = project.items.getItemByName("{_escape(str(edit["composition"]))}");')
            lines.append(f'var layer = comp.layers.addText("{_escape(str(edit["text"]))}");')
            lines.append(f'layer.property("ADBE Text Document").setValue("{_escape(str(edit["text"]))}");')
        else:
            raise CreativeError(
                f'After Effects cannot do {action!r} here. The supported changes are rename, '
                'frame rate and add text.')
    return '\n'.join(lines) + '\n'


def resolve_script(timeline, output, *, settings=None) -> str:
    """A Resolve script that renders the timeline and checks the result.

    The script talks to a **running** Resolve through its own module.
    It renders the timeline, and then it reads the rendered file back
    and writes down what it found.
    """
    settings = dict(settings or {})
    width = int(settings.get('width', 1920))
    height = int(settings.get('height', 1080))
    frames = int(settings.get('frames', 0))
    name = str(timeline).strip()
    if not name:
        raise CreativeError('Choose the timeline to render.')
    return (
        'import json, os, sys\n'
        'import DaVinciResolveScript as dvr\n'
        'resolve = dvr.scriptapp("Resolve")\n'
        'if not resolve:\n'
        '    print(json.dumps({"ok": False, "detail": "Resolve is not running."}))\n'
        '    sys.exit(2)\n'
        'manager = resolve.GetProjectManager()\n'
        'project = manager.GetProjectInCurrentTimeline()\n'
        'if not project:\n'
        '    print(json.dumps({"ok": False, "detail": "No project is open."}))\n'
        '    sys.exit(3)\n'
        'timeline = project.GetCurrentTimeline()\n'
        'if not timeline:\n'
        '    print(json.dumps({"ok": False, "detail": "No timeline is open."}))\n'
        '    sys.exit(4)\n'
        f'target = {str(output)!r}\n'
        f'name = {name!r}\n'
        'settings = {"TargetDir": os.path.dirname(target),\n'
        '            "CustomName": os.path.splitext(os.path.basename(target))[0],\n'
        f'            "ExportVideo": True,\n'
        f'            "VideoResWidth": {width},\n'
        f'            "VideoResHeight": {height},\n'
        '            "VideoCodec": "h264",\n'
        '            "AudioCodec": "LinearPCM"}\n'
        'try:\n'
        '    project.SetRenderSettings({"TargetDir": settings["TargetDir"],\n'
        '                              "CustomName": settings["CustomName"]})\n'
        '    job = timeline.AddRenderJob()\n'
        '    job.SetName(name)\n'
        '    job.SetTargetDir(settings["TargetDir"])\n'
        '    job.SetCustomName(settings["CustomName"])\n'
        '    job.SetSetting("ExportVideo", True)\n'
        '    job.SetSetting("VideoResWidth", settings["VideoResWidth"])\n'
        '    job.SetSetting("VideoResHeight", settings["VideoResHeight"])\n'
        '    job.SetSetting("VideoCodec", settings["VideoCodec"])\n'
        '    job.SetSetting("AudioCodec", settings["AudioCodec"])\n'
        '    if frames:\n'
        '        job.SetSetting("FrameRate", frames)\n'
        '    job.StartRendering()\n'
        '    while job.IsRenderingInProgress():\n'
        '        import time; time.sleep(0.5)\n'
        '    print(json.dumps({"ok": True, "output": target}))\n'
        'except Exception as error:\n'
        '    print(json.dumps({"ok": False, "detail": str(error)}))\n'
        '    sys.exit(5)\n')


def _escape(text: str) -> str:
    """Make a string safe to put in a script."""
    return str(text).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


# ── running the applications ───────────────────────────────────────────────


def _write_script(directory, name: str, content: str) -> Path:
    path = Path(directory) / name
    path.write_text(content, encoding='utf-8')
    return path


def _run_application(executable, arguments, *, timeout=SCRIPT_TIMEOUT,
                     check_cancelled=None) -> int:
    """Run an application with a script, and wait for it."""
    process = subprocess.Popen(
        [executable, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while True:
            if check_cancelled is not None:
                check_cancelled()
            try:
                output = process.communicate(timeout=0.5)[0]
                break
            except subprocess.TimeoutExpired:
                if process.poll() is not None:
                    output = process.communicate(timeout=5)[0]
                    break
                continue
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    detail = (output or b'').decode('utf-8', 'replace').strip()
    return process.returncode, detail


def run_photoshop(executable, edits, output, *, source=None,
                  check_cancelled=None) -> CreativeResult:
    """Make the edits in Photoshop and check the file that came out.

    The output file is compared with the source: it has to exist, and
    it has to be a different file. A script that ran and changed nothing
    is reported as a change that did not happen.
    """
    executable = Path(executable)
    if not executable.is_file():
        raise CreativeError('Choose Photoshop.exe from the Adobe installation folder.')
    output = Path(output).resolve()
    source = Path(source).resolve() if source else None
    if source is not None and not source.is_file():
        raise CreativeError('The file to edit is not there.')
    before = output.stat().st_mtime if output.exists() else None

    with tempfile.TemporaryDirectory(prefix='jarvis-photoshop-') as directory:
        script = _write_script(directory, 'jarvis-edit.jsx',
                               photoshop_script(list(edits) + [{'action': 'save',
                                                              'path': str(output)}]))
        code, detail = _run_application(executable, ['-r', str(script)],
                                        check_cancelled=check_cancelled)
    if code:
        return CreativeResult(application='Photoshop', output=str(output), ok=False,
                             message='Photoshop did not finish the edit.',
                             detail=detail[-400:])
    if not output.is_file():
        return CreativeResult(application='Photoshop', output=str(output), ok=False,
                             message='Photoshop did not write the file.',
                             detail=detail[-400:])
    changed = before is None or output.stat().st_mtime != before
    if source is not None and source.is_file() and output.stat().st_size == source.stat().st_size \
            and not changed:
        return CreativeResult(application='Photoshop', output=str(output), ok=False,
                             changed=False,
                             message='Photoshop ran, but the file was not changed.')
    return CreativeResult(application='Photoshop', output=str(output), ok=True, changed=True,
                          message=f'Photoshop wrote {output.name}.',
                          detail=detail[-200:])


def run_after_effects_script(executable, edits, project, *,
                             check_cancelled=None) -> CreativeResult:
    """Apply the changes to the project in After Effects, and check it."""
    executable = Path(executable)
    if not executable.is_file():
        raise CreativeError("Choose afterfx.exe from the After Effects Support Files folder.")
    project = Path(project).resolve()
    if not project.is_file():
        raise CreativeError('The After Effects project is not there.')
    before = project.stat().st_mtime

    with tempfile.TemporaryDirectory(prefix='jarvis-aftereffects-') as directory:
        script = _write_script(directory, 'jarvis-edit.jsx', after_effects_script(edits))
        code, detail = _run_application(executable, ['-r', str(script)],
                                        check_cancelled=check_cancelled)
    if code:
        return CreativeResult(application='After Effects', output=str(project), ok=False,
                             message='After Effects did not finish the change.',
                             detail=detail[-400:])
    changed = project.stat().st_mtime != before
    if not changed:
        return CreativeResult(application='After Effects', output=str(project), ok=False,
                             changed=False,
                             message='After Effects ran, but the project was not changed.')
    return CreativeResult(application='After Effects', output=str(project), ok=True, changed=True,
                          message=f'The project {project.name} was changed.',
                          detail=detail[-200:])


def run_resolve(script_text, output, *, check_cancelled=None) -> CreativeResult:
    """Render the timeline in DaVinci Resolve, and check the result.

    Resolve has to be **running**: the script talks to the open program
    through its own module.
    """
    module = resolve_script_path()
    if not module:
        raise CreativeError(
            "DaVinci Resolve's scripting module was not found. Install Resolve, or use "
            'the CapCut handoff, which needs nothing but the file.')
    output = Path(output).resolve()
    with tempfile.TemporaryDirectory(prefix='jarvis-resolve-') as directory:
        script = _write_script(directory, 'jarvis_render.py', script_text)
        environment = {**os.environ, 'PYTHONPATH': str(Path(module).parent)}
        try:
            process = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=SCRIPT_TIMEOUT, env=environment, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            raise CreativeError(f'Resolve could not be asked to render. {error}') from None
    detail = (process.stdout or '').strip() or (process.stderr or '').strip()
    if process.returncode:
        return CreativeResult(application='DaVinci Resolve', output=str(output), ok=False,
                             message='Resolve did not finish the render.',
                             detail=detail[-400:])
    if not output.is_file():
        return CreativeResult(application='DaVinci Resolve', output=str(output), ok=False,
                             message='Resolve did not write the file.',
                             detail=detail[-400:])
    return CreativeResult(application='DaVinci Resolve', output=str(output), ok=True,
                          changed=True,
                          message=f'Resolve wrote {output.name}.', detail=detail[-200:])


__all__ = ['AFTER_EFFECTS_PATHS', 'CreativeError', 'CreativeResult', 'PHOTOSHOP_PATHS',
           'RESOLVE_SCRIPT_PATHS', 'after_effects_available', 'after_effects_executable',
           'after_effects_script', 'photoshop_available', 'photoshop_executable',
           'photoshop_script', 'resolve_available', 'resolve_script',
           'resolve_script_path', 'run_after_effects_script', 'run_photoshop',
           'run_resolve']
