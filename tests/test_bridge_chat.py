"""The chat that the desktop serves for paired devices.

The rules are the point of this file: a phone may not spend money without
the consent of the owner, a phone never holds a key, and a stopped desktop
does not answer.
"""
import pytest

from desktop.bridge_chat import (
    CONSENT_KEY, MEMORY_KEY, PROVIDER_KEY, BridgeChatService,
)
from providers.router import ProviderRouter
from remote.server import BridgeHandlerError
from security.policy import Policy


class FakeVault:
    """A vault that holds one key."""

    def __init__(self, keys=None):
        self.keys = dict(keys or {})

    def get(self, provider):
        return self.keys.get(provider)

    def put(self, provider, secret):
        self.keys[provider] = secret

    def delete(self, provider):
        self.keys.pop(provider, None)


class FakeStore:
    """The part of the store the service uses."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def set(self, key, value):
        self.values[key] = value

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakePolicy:
    def __init__(self, stopped=False):
        self._stopped = stopped

    @property
    def stopped(self):
        return self._stopped

    def ticket(self):
        return 'ticket'

    def check(self, ticket):
        if self._stopped:
            raise RuntimeError('stopped')


class FakeRouter:
    """A router that answers with a fixed text and records the call."""

    def __init__(self, answer='The answer.', fail=None, local=False, on_stream=None):
        self.answer_text = answer
        self.fail = fail
        self.local = local
        #: Called in the middle of the stream, so a test can stop the desktop
        #: while the provider is still working.
        self.on_stream = on_stream
        self.calls = []

    def spec(self, name):
        if name not in ('ollama', 'openai', 'Gemini'):
            raise KeyError('Unknown provider.')
        class Spec:
            def __init__(self, local):
                self.local = local
                self.default_model = 'default-model'
        return Spec(self.local)

    def stream(self, spec, model, key, messages, check, emit, metrics=None):
        self.calls.append({'model': model, 'key': key, 'messages': messages})
        check()
        if self.on_stream is not None:
            self.on_stream()
        check()
        if self.fail is not None:
            raise self.fail
        return self.answer_text


def make_service(router=None, store=None, vault=None, policy=None):
    return BridgeChatService(router or FakeRouter(), store or FakeStore(), vault or FakeVault(),
                             policy=policy)


def test_no_provider_means_no_answer():
    service = make_service()
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', True)
    assert error.value.status == 503


def test_a_local_provider_answers_without_consent():
    router = FakeRouter(answer='Local answer.', local=True)
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}))
    answer = service.answer('hello', False)
    assert answer['text'] == 'Local answer.'
    assert answer['local'] is True
    assert router.calls[0]['key'] == ''


def test_a_paid_provider_needs_the_consent_of_the_owner():
    router = FakeRouter(local=False)
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'openai'}))
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', True)
    assert error.value.status == 403
    assert 'not allowed' in error.value.message


def test_a_paid_provider_needs_the_consent_of_the_request():
    router = FakeRouter(local=False)
    store = FakeStore({PROVIDER_KEY: 'openai', CONSENT_KEY: True})
    service = make_service(router=router, store=store)
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', False)
    assert error.value.status == 403
    assert 'consent' in error.value.message


def test_camera_frames_require_consent_and_stay_out_of_chat_history():
    router = FakeRouter()
    store = FakeStore({PROVIDER_KEY: 'Gemini', CONSENT_KEY: True})
    service = make_service(router=router, store=store, vault=FakeVault({'Gemini': 'test-key'}))
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('Look at this', False, images=['frame'])
    assert error.value.status == 403
    assert not router.calls
    service.answer('Look at this', True, images=['frame'])
    assert router.calls[0]['messages'][-1]['content'][1]['image_url']['url'].endswith(',frame')
    service.answer('Next question', True)
    assert 'frame' not in repr(router.calls[1]['messages'])


def test_a_paid_provider_answers_when_both_consents_are_given():
    router = FakeRouter(answer='Paid answer.', local=False)
    store = FakeStore({PROVIDER_KEY: 'openai', CONSENT_KEY: True, 'model:openai': 'gpt-x'})
    vault = FakeVault({'openai': 'the-key'})
    service = make_service(router=router, store=store, vault=vault)
    answer = service.answer('hello', True)
    assert answer['text'] == 'Paid answer.'
    assert answer['provider'] == 'openai'
    assert answer['model'] == 'gpt-x'
    assert router.calls[0]['key'] == 'the-key'


def test_a_provider_without_a_key_is_refused():
    router = FakeRouter(local=False)
    store = FakeStore({PROVIDER_KEY: 'openai', CONSENT_KEY: True})
    service = make_service(router=router, store=store, vault=FakeVault())
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', True)
    assert error.value.status == 403


def test_an_unknown_provider_is_refused():
    service = make_service(store=FakeStore({PROVIDER_KEY: 'nothing'}))
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', True)
    assert error.value.status == 503


def test_a_stopped_desktop_does_not_answer():
    router = FakeRouter(local=True)
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}),
                           policy=FakePolicy(stopped=True))
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', False)
    assert error.value.status == 503


def test_the_short_history_is_kept():
    router = FakeRouter(local=True)
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}))
    service.answer('one', False)
    service.answer('two', False)
    messages = router.calls[-1]['messages']
    assert messages[0]['role'] == 'system'
    assert messages[-1]['content'] == 'two'
    assert any(message['content'] == 'one' for message in messages)


def test_the_settings_are_remembered():
    store = FakeStore()
    service = make_service(store=store)
    service.configure('openai', paid_consent=True, memory_sync=True)
    assert store.values[PROVIDER_KEY] == 'openai'
    assert store.values[CONSENT_KEY] is True
    assert store.values[MEMORY_KEY] is True
    assert service.provider == 'openai'
    assert service.paid_consent is True
    assert service.memory_sync is True


def test_the_router_of_the_desktop_is_used():
    router = ProviderRouter()
    service = BridgeChatService(router, FakeStore(), FakeVault())
    assert service.provider == ''


# --------------------------------------------------------------------------
# The real approval boundary
#
# These tests use the real `security.policy.Policy` on purpose. The fake
# above answers `check()` whatever ticket it is given, so it could never
# notice that the service was passing the *method* `ticket` where the
# generation number was expected. That mistake made every request from a
# paired phone fail with a 502, and the fake hid it.
# --------------------------------------------------------------------------


def test_the_real_policy_allows_the_answer():
    router = FakeRouter(answer='Local answer.', local=True)
    policy = Policy()
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}),
                           policy=policy)
    answer = service.answer('hello', False)
    assert answer['text'] == 'Local answer.'
    assert answer['local'] is True


def test_the_real_policy_stops_a_stopped_desktop():
    router = FakeRouter(local=True)
    policy = Policy()
    policy.stop()
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}),
                           policy=policy)
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', False)
    assert error.value.status == 503


def test_an_emergency_stop_during_the_answer_abandons_it():
    """A stop that happens while the provider works must not be answered."""
    policy = Policy()
    router = FakeRouter(answer='Local answer.', local=True, on_stream=policy.stop)
    service = make_service(router=router, store=FakeStore({PROVIDER_KEY: 'ollama'}),
                           policy=policy)
    with pytest.raises(BridgeHandlerError) as error:
        service.answer('hello', False)
    assert error.value.status == 503
    assert 'stopped' in error.value.message.lower()
