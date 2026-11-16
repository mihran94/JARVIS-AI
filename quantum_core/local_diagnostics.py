"""On-demand local network inventory from operating-system tables."""
from pathlib import Path
import socket
import subprocess
import sys

import psutil


REPORTS = {
    'neighbors': 'Cached neighbors',
    'listeners': 'TCP listeners',
    'connections': 'Established TCP',
}
ROW_LIMIT = 150


class DiagnosticError(RuntimeError):
    """The OS could not provide a diagnostic table."""


def neighbor_cache():
    if sys.platform == 'win32':
        from os import environ

        arp = Path(environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'arp.exe'
        try:
            result = subprocess.run([str(arp), '-a'], check=True, capture_output=True, timeout=4)
        except (OSError, subprocess.SubprocessError):
            raise DiagnosticError('Windows could not read its ARP cache.') from None
        lines = result.stdout.decode(errors='replace').strip().splitlines()
    elif sys.platform.startswith('linux'):
        try:
            lines = Path('/proc/net/arp').read_text().strip().splitlines()
        except OSError:
            raise DiagnosticError('Linux could not read its ARP cache.') from None
    else:
        raise DiagnosticError('Cached neighbors are available on Windows and Linux.')
    return format_report(
        'Cached IPv4 neighbors. Entries can be stale and the list may be incomplete.',
        [line.rstrip() for line in lines if line.strip()],
    )


def endpoint(address):
    if not address:
        return '–'
    host, port = address
    return f'[{host}]:{port}' if ':' in host else f'{host}:{port}'


def tcp_inventory(status):
    try:
        connections = psutil.net_connections(kind='tcp')
    except psutil.AccessDenied:
        raise DiagnosticError('The OS denied access to the local TCP connection table.') from None
    except (OSError, psutil.Error):
        raise DiagnosticError('The OS could not read the local TCP connection table.') from None
    rows = sorted({
        (endpoint(entry.laddr), endpoint(entry.raddr), entry.pid)
        for entry in connections
        if entry.status == status and entry.family in (socket.AF_INET, socket.AF_INET6)
    }, key=lambda row: (row[0], row[1], row[2] or 0))
    records = [f'{local}   →   {remote}   PID {pid if pid is not None else "unknown"}'
               for local, remote, pid in rows]
    introduction = (
        'Local TCP listeners. Reachability depends on Windows firewall and network configuration.'
        if status == psutil.CONN_LISTEN
        else 'Established TCP connections reported by the OS. Peers can be local or remote.'
    )
    return format_report(introduction, records)


def format_report(introduction, records):
    if not records:
        return f'{introduction}\n\nNo entries reported.'
    visible = list(records[:ROW_LIMIT])
    if len(records) > ROW_LIMIT:
        visible.append(f'… {len(records) - ROW_LIMIT} more entries.')
    return introduction + '\n\n' + '\n'.join(visible)


def read_network_report(report):
    if report == 'neighbors':
        return neighbor_cache()
    if report == 'listeners':
        return tcp_inventory(psutil.CONN_LISTEN)
    if report == 'connections':
        return tcp_inventory(psutil.CONN_ESTABLISHED)
    raise DiagnosticError('Choose an available local network report.')
