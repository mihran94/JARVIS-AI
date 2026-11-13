"""No-audio Windows voice packaging diagnostic contract tests."""
import sys
import types

from desktop.app import voice_runtime_smoke_test


def test_voice_runtime_check_never_runs_on_linux(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert voice_runtime_smoke_test() == 21


def test_voice_runtime_checks_clr_and_sapi_without_recording(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    calls = []
    clr = types.ModuleType('clr')
    clr.AddReference = lambda name: calls.append(('assembly', name))

    system = types.ModuleType('System')
    system.__path__ = []
    speech = types.ModuleType('System.Speech')
    speech.__path__ = []
    recognition = types.ModuleType('System.Speech.Recognition')
    recognition.Grammar = object

    win32com = types.ModuleType('win32com')
    win32com.__path__ = []
    client = types.ModuleType('win32com.client')
    client.Dispatch = lambda name: calls.append(('sapi', name)) or object()
    win32com.client = client

    for key, module in (
        ('clr', clr), ('System', system), ('System.Speech', speech),
        ('System.Speech.Recognition', recognition),
        ('win32com', win32com), ('win32com.client', client),
    ):
        monkeypatch.setitem(sys.modules, key, module)

    assert voice_runtime_smoke_test() == 0
    assert calls == [('assembly', 'System.Speech'), ('sapi', 'SAPI.SpVoice')]
