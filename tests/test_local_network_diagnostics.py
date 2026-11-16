"""Local diagnostics only consume OS table snapshots."""
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from quantum_core import local_diagnostics as diagnostics


def test_listener_report_uses_local_os_table_and_formats_ipv6(monkeypatch):
    entries = [
        SimpleNamespace(family=socket.AF_INET6, status=psutil.CONN_LISTEN,
                        laddr=('::1', 8766), raddr=(), pid=42),
        SimpleNamespace(family=socket.AF_INET, status=psutil.CONN_ESTABLISHED,
                        laddr=('127.0.0.1', 8767), raddr=('127.0.0.1', 443), pid=None),
    ]
    read_table = Mock(return_value=entries)
    monkeypatch.setattr(diagnostics.psutil, 'net_connections', read_table)

    assert '[::1]:8766' in diagnostics.read_network_report('listeners')
    assert '127.0.0.1:8767' not in diagnostics.read_network_report('listeners')
    assert '127.0.0.1:443' in diagnostics.read_network_report('connections')
    read_table.assert_called_with(kind='tcp')


def test_local_reports_reject_unknown_modes_and_explain_permission_errors(monkeypatch):
    read_table = Mock(side_effect=psutil.AccessDenied())
    monkeypatch.setattr(diagnostics.psutil, 'net_connections', read_table)

    with pytest.raises(diagnostics.DiagnosticError, match='available local network report'):
        diagnostics.read_network_report('unrecognized-mode')
    read_table.assert_not_called()
    with pytest.raises(diagnostics.DiagnosticError, match='denied access'):
        diagnostics.read_network_report('listeners')


def test_windows_neighbors_uses_the_fixed_arp_read_command(monkeypatch):
    monkeypatch.setattr(diagnostics.sys, 'platform', 'win32')
    run = Mock(return_value=SimpleNamespace(stdout=b'Interface: 192.0.2.1\n  192.0.2.2\n'))
    monkeypatch.setattr(diagnostics.subprocess, 'run', run)
    assert '192.0.2.2' in diagnostics.read_network_report('neighbors')
    assert run.call_args.args[0][0].endswith('arp.exe')
    assert run.call_args.args[0][1:] == ['-a']
    assert run.call_args.kwargs['timeout'] == 4
    assert 'shell' not in run.call_args.kwargs
