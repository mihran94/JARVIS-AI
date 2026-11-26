"""The on-device model that JARVIS starts on this computer.

WHAT IS COVERED
    * The local model is only ever reached on the loopback interface, so
      it can never be turned into an open relay.
    * A model that is not installed is reported as missing, and nothing
      is downloaded.
    * The models the local server has are read from the server itself.
    * The model JARVIS uses is the owner's choice when it is there, and
      the one that is there when it is not.
"""
import httpx
import pytest

from core.local_model import (
    DEFAULT_BASE, DEFAULT_MODEL, LocalModelSupervisor, LocalModelUnavailable,
    candidate_paths, find_executable, is_loopback,
)


def tags_response(models):
    """The answer the local server gives about its models."""
    return {'models': [{'name': name} for name in models]}


def server(models=('qwen3:8b',), status=200):
    """A fake local server that answers about its models."""
    def handler(request):
        return httpx.Response(status, json=tags_response(models))
    return httpx.MockTransport(handler)


def test_only_the_loopback_interface_is_allowed():
    assert is_loopback('http://127.0.0.1:11434/api/tags') is True
    assert is_loopback('http://localhost:11434') is True
    assert is_loopback('http://192.168.1.10:11434') is False
    assert is_loopback('http://example.com') is False


def test_a_supervisor_refuses_an_address_that_is_not_this_machine():
    with pytest.raises(ValueError):
        LocalModelSupervisor(base='http://192.168.1.10:11434')


def test_the_models_the_server_has_are_read_from_the_server():
    supervisor = LocalModelSupervisor(transport=server(['qwen3:8b', 'llama3:8b']))
    assert supervisor.installed_models() == ['qwen3:8b', 'llama3:8b']


def test_a_server_that_is_not_there_has_no_models():
    supervisor = LocalModelSupervisor(transport=server(status=404))
    assert supervisor.installed_models() == []
    assert supervisor.is_running() is False


def test_a_model_that_is_not_installed_is_reported_as_missing():
    supervisor = LocalModelSupervisor(model='qwen3:8b',
                                      transport=server(['llama3:8b']),
                                      executable='/nowhere/ollama')
    status = supervisor.status()
    assert status.installed is False
    assert 'not installed' in status.detail
    assert status.ready is False


def test_the_model_is_ready_when_the_server_has_it():
    supervisor = LocalModelSupervisor(model='qwen3:8b',
                                      transport=server(['qwen3:8b']),
                                      executable='/nowhere/ollama')
    status = supervisor.status()
    assert status.running is True
    assert status.ready is True
    assert 'ready' in status.detail


def test_the_model_is_not_ready_when_the_server_does_not_have_it():
    supervisor = LocalModelSupervisor(model='qwen3:8b',
                                      transport=server(['llama3:8b']),
                                      executable='/nowhere/ollama')
    status = supervisor.status()
    assert status.running is True
    assert status.ready is False
    assert 'llama3:8b' in status.detail


def test_the_owner_model_wins_when_the_server_has_it():
    supervisor = LocalModelSupervisor(model='qwen3:8b',
                                      transport=server(['qwen3:8b', 'llama3:8b']),
                                      executable='/nowhere/ollama')
    assert supervisor.choose_model() == 'qwen3:8b'


def test_a_model_of_the_same_family_is_used_when_the_exact_one_is_missing():
    supervisor = LocalModelSupervisor(model='qwen3:8b',
                                      transport=server(['qwen3:4b']),
                                      executable='/nowhere/ollama')
    assert supervisor.choose_model() == 'qwen3:4b'


def test_the_first_model_is_used_when_the_owner_model_is_not_there():
    supervisor = LocalModelSupervisor(model='mixtral:8x7b',
                                      transport=server(['llama3:8b', 'gemma2:9b']),
                                      executable='/nowhere/ollama')
    assert supervisor.choose_model() == 'llama3:8b'


def test_starting_a_model_that_is_not_installed_says_so():
    supervisor = LocalModelSupervisor(executable='')
    with pytest.raises(LocalModelUnavailable):
        supervisor.start()


def test_the_executable_is_looked_for_in_the_known_places():
    paths = [str(path) for path in candidate_paths()]
    assert all('ollama' in path.casefold() for path in paths)
    assert isinstance(find_executable(), str)


def test_the_default_model_is_the_one_the_registry_names():
    assert DEFAULT_MODEL == 'qwen3:8b'
    assert DEFAULT_BASE == 'http://127.0.0.1:11434'
