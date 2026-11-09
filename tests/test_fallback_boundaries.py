"""Offline permission/cancellation boundaries for the opt-in helper."""
import pytest
from providers.stream_fallback import StreamTarget, FallbackBlocked, stream_with_fallback
from security.policy import Stopped

PRIMARY = StreamTarget('OpenAI', 'test', 'fake-primary-secret')
BACKUP = StreamTarget('Gemini', 'test', 'fake-backup-secret')
MESSAGES = [{'role': 'user', 'content': 'test'}]


def test_target_repr_does_not_disclose_key():
    assert PRIMARY.key not in repr(PRIMARY)
    assert 'OpenAI' in repr(PRIMARY)


def test_cancelled_before_primary_does_not_call_adapter():
    calls = []
    def check():
        raise Stopped('cancelled')
    with pytest.raises(Stopped):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, check, lambda _: None,
                             lambda *args: calls.append(args), consent_to_backup=True)
    assert not calls


def test_direct_cancellation_never_falls_back_even_if_runtime_errors_allowed():
    calls = []
    def stream(provider, *args):
        calls.append(provider)
        raise Stopped('cancelled')
    with pytest.raises(Stopped):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, lambda: None, lambda _: None,
                             stream, consent_to_backup=True, retryable_errors=(RuntimeError,))
    assert calls == ['OpenAI']


def test_partial_output_prevents_backup():
    calls, chunks = [], []
    def stream(provider, model, key, messages, check, emit):
        calls.append(provider)
        emit('partial')
        raise TimeoutError('timeout')
    with pytest.raises(FallbackBlocked, match='Partial'):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, lambda: None, chunks.append,
                             stream, consent_to_backup=True)
    assert calls == ['OpenAI'] and chunks == ['partial']


def test_callback_error_is_not_retried():
    calls = []
    def emit(_):
        raise ConnectionError('UI callback failed')
    def stream(provider, model, key, messages, check, emit):
        calls.append(provider)
        emit('text')
    with pytest.raises(ConnectionError, match='UI callback'):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, lambda: None, emit,
                             stream, consent_to_backup=True)
    assert calls == ['OpenAI']


@pytest.mark.parametrize('consent', ['yes', 1, None])
def test_non_boolean_consent_is_rejected(consent):
    with pytest.raises(TypeError):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, lambda: None, lambda _: None,
                             lambda *args: pytest.fail('Must not call provider'),
                             consent_to_backup=consent)


@pytest.mark.parametrize('errors', [(Exception,), (BaseException,), ()])
def test_overbroad_retry_policy_rejected(errors):
    with pytest.raises(ValueError):
        stream_with_fallback(PRIMARY, BACKUP, MESSAGES, lambda: None, lambda _: None,
                             lambda *args: pytest.fail('Must not call provider'),
                             retryable_errors=errors)
