"""Opt-in streaming fallback adapter for JARVIS-AI v0.3 chat.stream_chat.

Never automatically sends a prompt to another provider.
"""
from dataclasses import dataclass
from typing import Callable


class FallbackBlocked(RuntimeError):
    """No safe, authorized fallback was available."""


@dataclass(frozen=True)
class StreamTarget:
    name: str
    model: str
    key: str


def stream_with_fallback(primary: StreamTarget, backup: StreamTarget | None,
                         messages, check: Callable[[], None], emit: Callable[[str], None],
                         stream: Callable, *, consent_to_backup: bool = False,
                         retryable_errors: tuple[type[Exception], ...] = (TimeoutError, ConnectionError)):
    """Try backup only after a primary failure *before* any emitted text.

    `stream` uses the repository's stream_chat(provider, model, key, messages,
    check, emit) signature. Provider errors are supplied through
    `retryable_errors`; do not retry cancellation, programming errors, or
    errors from the caller's emit callback.
    """
    if (not isinstance(retryable_errors, tuple) or not retryable_errors or
            any(not isinstance(error, type) or
                not issubclass(error, Exception) or
                error in (Exception, BaseException) or
                issubclass(Exception, error)
                for error in retryable_errors)):
        raise ValueError('Retryable errors must be specific Exception subclasses')
    if type(consent_to_backup) is not bool:
        raise TypeError('Fallback consent must be an explicit boolean')
    if not primary.name or not primary.model or not primary.key:
        raise ValueError('Primary provider configuration is incomplete')
    if not isinstance(messages, list) or not messages:
        raise ValueError('Messages must be a nonempty list')

    emitted = False

    class CallbackFailure(Exception):
        def __init__(self, original):
            self.original = original

    def safe_emit(chunk):
        nonlocal emitted
        emitted = True
        try:
            emit(chunk)
        except Exception as exc:
            raise CallbackFailure(exc) from exc

    def safe_check():
        try:
            check()
        except Exception as exc:
            raise CallbackFailure(exc) from exc

    try:
        return primary.name, stream(primary.name, primary.model, primary.key,
                                    messages, safe_check, safe_emit)
    except CallbackFailure as exc:
        raise exc.original
    except retryable_errors as exc:
        if emitted:
            raise FallbackBlocked('Partial response already displayed; retry manually') from exc
        if not consent_to_backup or backup is None or backup.name == primary.name:
            raise FallbackBlocked('Cross-provider fallback not authorized') from exc
        if not backup.name or not backup.model or not backup.key:
            raise FallbackBlocked('Backup provider configuration is incomplete') from exc
        try:
            safe_check()
            return backup.name, stream(backup.name, backup.model, backup.key,
                                       messages, safe_check, safe_emit)
        except CallbackFailure as callback_exc:
            raise callback_exc.original
