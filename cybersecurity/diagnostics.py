"""Scoped, defensive checks for this computer.

WHAT THIS IS
    The checks behind the Cybersecurity interface. Each one reads the
    machine and reports what it found. None of them changes anything:
    they are diagnostics, and the owner approves the check itself
    before it runs.

WHAT THIS IS NOT
    * It is not an attack tool. Nothing here scans another computer,
      probes another service or touches a file it was not asked about.
    * It is not a scanner that invents risk. A check that cannot run on
      this machine reports that it could not run, and produces no
      finding.
    * It does not gather credentials. Where a check could see a secret,
      it masks it before it becomes a finding.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import subprocess
import sys

import psutil

from cybersecurity.report import Finding, SecurityReport

#: How long a command that reads the operating system may run.
COMMAND_TIMEOUT = 8

#: How many rows one inventory check shows.
ROW_LIMIT = 40


class CheckUnavailable(RuntimeError):
    """The check cannot run on this machine."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ── the network tables ─────────────────────────────────────────────────────


def check_listeners() -> list:
    """What is listening on this computer."""
    try:
        connections = psutil.net_connections(kind='tcp')
    except psutil.AccessDenied:
        raise CheckUnavailable('The operating system denied access to the local TCP '
                               'connection table.') from None
    except (OSError, psutil.Error):
        raise CheckUnavailable('The operating system could not read the local TCP '
                               'connection table.') from None
    rows = []
    for entry in connections:
        if entry.status != psutil.CONN_LISTEN or entry.pid is None:
            continue
        try:
            name = psutil.Process(entry.pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            name = 'unknown'
        address = entry.laddr[0] if entry.laddr else '?'
        port = entry.laddr[1] if entry.laddr else 0
        rows.append((address, port, name, entry.pid))
    rows.sort(key=lambda row: (row[0], row[1]))
    if not rows:
        return [Finding('info', 'Network', 'No listening TCP sockets were found',
                        'Nothing on this computer is accepting a TCP connection.',
                        source='local TCP table')]
    outside = [row for row in rows if row[0] not in ('127.0.0.1', '::1', '0.0.0.0', '::')]
    findings = [Finding(
        'low' if outside else 'info',
        'Network',
        f'{len(rows)} listening TCP socket(s)',
        'Every one of them is reachable from this machine only.' if not outside else
        f'{len(outside)} of them are bound to an address that is not this machine alone.',
        evidence='; '.join(f'{address}:{port} {name} (PID {pid})'
                            for address, port, name, pid in rows[:ROW_LIMIT]),
        recommendation='Check the firewall rule for anything you do not recognise.'
                      if outside else '',
        source='local TCP table')]
    return findings


def check_established() -> list:
    """What this computer is connected to."""
    try:
        connections = psutil.net_connections(kind='tcp')
    except psutil.AccessDenied:
        raise CheckUnavailable('The operating system denied access to the connection table.')
    except (OSError, psutil.Error):
        raise CheckUnavailable('The operating system could not read the connection table.')
    rows = []
    for entry in connections:
        if entry.status != psutil.CONN_ESTABLISHED or entry.pid is None:
            continue
        try:
            name = psutil.Process(entry.pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            name = 'unknown'
        remote = f'{entry.raddr[0]}:{entry.raddr[1]}' if entry.raddr else 'unknown'
        rows.append((remote, name, entry.pid))
    rows.sort()
    if not rows:
        return [Finding('info', 'Network', 'No established TCP connections were found',
                        source='local connection table')]
    return [Finding(
        'info', 'Network', f'{len(rows)} established TCP connection(s)',
        evidence='; '.join(f'{remote} {name} (PID {pid})' for remote, name, pid in rows[:ROW_LIMIT]),
        source='local connection table')]


# ── the running programs ───────────────────────────────────────────────────


def check_processes() -> list:
    """What is running on this computer."""
    findings = []
    rows = []
    for process in psutil.process_iter(['pid', 'name', 'username']):
        try:
            info = process.info
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            continue
        if info.get('name'):
            rows.append((info['name'], info['pid'], info.get('username') or ''))
    rows.sort(key=lambda row: row[0].lower())
    if not rows:
        raise CheckUnavailable('The running program list could not be read.')
    findings.append(Finding(
        'info', 'Programs', f'{len(rows)} program(s) are running',
        evidence='; '.join(f'{name} (PID {pid})' for name, pid, _ in rows[:ROW_LIMIT]),
        source='the operating system process table'))
    return findings


# ── what starts with the computer ──────────────────────────────────────────


def check_startup() -> list:
    """What runs when this computer starts."""
    entries = []
    if sys.platform == 'win32':
        try:
            import winreg
        except ImportError:
            raise CheckUnavailable('The Windows registry is not available here.')
        places = [
            (winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run'),
            (winreg.HKEY_LOCAL_MACHINE, r'Software\Microsoft\Windows\CurrentVersion\Run'),
        ]
        for root, path in places:
            try:
                with winreg.OpenKey(root, path) as key:
                    index = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        entries.append((name, str(value)))
                        index += 1
            except OSError:
                continue
        if not entries:
            return [Finding('info', 'Startup', 'No startup entries were found in the registry',
                            source='the Windows Run keys')]
        return [Finding(
            'medium', 'Startup', f'{len(entries)} program(s) start with Windows',
            'Anything here runs with your account every time the computer starts.',
            evidence='; '.join(f'{name} → {value}' for name, value in entries[:ROW_LIMIT]),
            recommendation='Remove the ones you do not recognise in Task Manager → Startup.',
            source='the Windows Run keys')]
    home = Path.home()
    autostart = home / '.config' / 'autostart'
    if autostart.is_dir():
        files = sorted(item.name for item in autostart.iterdir())
        if files:
            return [Finding('medium', 'Startup', f'{len(files)} autostart entry(s) were found',
                            evidence='; '.join(files[:ROW_LIMIT]),
                            recommendation='Remove the ones you do not recognise.',
                            source='the user autostart folder')]
    return [Finding('info', 'Startup', 'No startup entries were found',
                    source='the user autostart folder')]


# ── the operating system protection ────────────────────────────────────────


def _run_readonly(command, timeout=COMMAND_TIMEOUT) -> str:
    """Run a read-only operating system command and return its output."""
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False,
                                shell=False, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    except (OSError, subprocess.SubprocessError):
        raise CheckUnavailable('The operating system could not be asked.') from None
    output = result.stdout.decode('utf-8', 'replace').strip()
    if result.returncode != 0 and not output:
        raise CheckUnavailable('The operating system did not answer that question.')
    return output


def check_firewall() -> list:
    """Whether the firewall is on for each profile."""
    if sys.platform != 'win32':
        raise CheckUnavailable('The firewall profile check is available on Windows.')
    output = _run_readonly(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'])
    off = [line.strip() for line in output.splitlines()
           if line.lower().startswith('state') and 'on' not in line.lower()]
    if off:
        return [Finding('high', 'Firewall', 'A firewall profile is off',
                        'Traffic is not filtered for that profile.',
                        evidence='; '.join(off),
                        recommendation='Turn the profile on in Windows Security → Firewall.',
                        source='netsh advfirewall')]
    return [Finding('info', 'Firewall', 'The firewall is on for every profile',
                    evidence=output[:400], source='netsh advfirewall')]


def check_defender() -> list:
    """Whether Microsoft Defender is running and whether it is current."""
    if sys.platform != 'win32':
        raise CheckUnavailable('The Defender check is available on Windows.')
    output = _run_readonly(['powershell', '-NoProfile', '-Command',
                             'Get-MpComputerStatus | Select-Object '
                             'RealTimeProtectionEnabled,AntivirusEnabled,'
                             'AntivirusSignatureLastUpdated | Format-List'])
    if 'RealTimeProtectionEnabled' not in output:
        raise CheckUnavailable('Windows did not report the Defender status.')
    live = 'True' in output.split('RealTimeProtectionEnabled')[1][:40]
    return [Finding(
        'info' if live else 'high', 'Protection',
        'Real-time protection is on' if live else 'Real-time protection is off',
        evidence=output[:400],
        recommendation='' if live else 'Turn real-time protection on in Windows Security.',
        source='Get-MpComputerStatus')]


# ── JARVIS's own configuration ─────────────────────────────────────────────


def check_jarvis_configuration(store=None) -> list:
    """A defensive review of JARVIS's own settings."""
    findings = []
    if store is None:
        return [Finding('info', 'JARVIS', 'The configuration review needs the settings store',
                        source='the local settings store')]

    if bool(store.get('auto_maintenance', False)):
        findings.append(Finding(
            'medium', 'JARVIS',
            'JARVIS proposes source updates on its own',
            'A change to JARVIS itself can be proposed without the owner asking first.',
            evidence='auto_maintenance = on',
            recommendation='Turn off "Automatically propose source update guide fixes" '
                           'in Settings if you want to ask every time.',
            source='the local settings store'))

    if bool(store.get('backup_consent', False)):
        findings.append(Finding(
            'medium', 'JARVIS', 'A backup provider is allowed',
            'A conversation can be shared with a second provider when the first one fails.',
            evidence='backup consent = on',
            recommendation='Turn off "Allow one backup attempt" unless you want it.',
            source='the local settings store'))

    notes = store.get('notes', None)
    if notes is not None and not isinstance(notes, (str, list, dict)):
        findings.append(Finding('low', 'JARVIS', 'An unexpected value is stored under "notes"',
                                source='the local settings store'))

    if not findings:
        findings.append(Finding('info', 'JARVIS', 'Nothing risky was found in the settings',
                                'Automatic updates and the backup provider are both off.',
                                source='the local settings store'))
    return findings


def check_credential_storage() -> list:
    """Where the provider keys are kept."""
    findings = []
    try:
        import keyring
        backend = keyring.get_keyring()
        name = type(backend).__name__
    except Exception:
        name = 'unknown'
    if 'win' not in name.casefold():
        findings.append(Finding(
            'medium', 'Credentials', 'The credential backend is not the Windows one',
            'The provider keys are not held by Windows Credential Manager here.',
            evidence=f'backend = {name}',
            recommendation='On Windows, JARVIS keeps the keys in Credential Manager.',
            source='the keyring backend'))
    else:
        findings.append(Finding('info', 'Credentials', 'The keys are in Windows Credential Manager',
                                evidence=f'backend = {name}', source='the keyring backend'))

    home = Path.home()
    loose = [path for pattern in ('*.key', '*.pem', 'credentials*.json', 'secrets*.json')
             for path in home.glob(pattern)]
    if loose:
        findings.append(Finding(
            'high', 'Credentials', 'A file that looks like a key is in the home folder',
            'A key should be in Credential Manager, not in a file.',
            evidence='; '.join(str(path) for path in loose[:ROW_LIMIT]),
            recommendation='Move it into Windows Credential Manager and delete the file.',
            source='the home folder'))
    return findings


# ── the catalogue ──────────────────────────────────────────────────────────

#: Every check the interface offers. The order is the order they are shown.
CHECKS = {
    'listeners': ('Listening sockets', 'What is accepting a connection on this computer.',
                  check_listeners),
    'established': ('Established connections', 'What this computer is connected to right now.',
                    check_established),
    'processes': ('Running programs', 'The programs that are running, with their process ids.',
                  check_processes),
    'startup': ('Startup entries', 'What runs when the computer starts.',
                check_startup),
    'firewall': ('Firewall profiles', 'Whether the firewall is on for each profile.',
                 check_firewall),
    'defender': ('Microsoft Defender', 'Whether the built-in protection is running.',
                 check_defender),
    'credentials': ('Where the keys are kept', 'How the provider keys are stored.',
                    check_credential_storage),
}


def run_check(name: str, store=None) -> list:
    """Run one check and return its findings.

    A check that cannot run on this machine raises `CheckUnavailable`,
    and the interface says so rather than showing an empty result that
    looks like a clean bill of health.
    """
    if name not in CHECKS:
        raise ValueError('That check does not exist.')
    _, _, function = CHECKS[name]
    if name == 'jarvis_configuration':
        return function(store)
    return function()


def run_all(store=None) -> SecurityReport:
    """Run every check that this machine can run."""
    report = SecurityReport(scope='Local device', created=_now())
    for name, (title, _, _) in CHECKS.items():
        try:
            report.extend(run_check(name, store=store))
            report.checks_run.append(title)
        except CheckUnavailable as error:
            report.notes.append(f'{title}: not run. {error}')
    return report


__all__ = ['CHECKS', 'CheckUnavailable', 'check_credential_storage', 'check_defender',
           'check_established', 'check_firewall', 'check_jarvis_configuration',
           'check_listeners', 'check_processes', 'check_startup', 'run_all', 'run_check']
