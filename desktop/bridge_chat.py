"""Chat for paired devices, served by the desktop.

The service answers a message that arrived over the bridge by using the
provider the owner selected in the interface. It exists because a phone must
never hold a provider key: the key stays in the Windows vault on the PC, the
phone only sends a message and receives the answer.

Rules that are enforced here and nowhere else:

- the owner must first choose a provider for the bridge and allow it;
- a paid provider needs the consent of the owner *and* the consent flag in
  the request, so a phone can never spend money by accident;
- a local provider is used without a key and without any consent, because it
  never leaves the computer;
- the emergency stop of the desktop stops the bridge as well.

The service never touches a widget. The listener runs on its own thread, and
a widget must only be used on the Qt thread, so everything it needs comes
from the store, the vault and the router.
"""
import time

from providers.chat import ProviderError
from remote.server import BridgeHandlerError

#: The store key that holds the provider chosen for the bridge.
PROVIDER_KEY = 'bridge:chat_provider'

#: The store key that holds the owner's permission to use a paid provider.
CONSENT_KEY = 'bridge:chat_paid_consent'

#: The store key that holds the owner's permission to synchronise memory.
MEMORY_KEY = 'bridge:memory_sync'

#: The most messages that are kept for one conversation.
MAX_HISTORY = 12


class BridgeChatService:
    """Answers bridge chat requests with the desktop's provider."""

    def __init__(self, router, store, vault, *, policy=None):
        self._router = router
        self._store = store
        self._vault = vault
        self._policy = policy
        self._history: list[dict] = []

    # ------------------------------------------------------------- properties

    @property
    def provider(self) -> str:
        """The provider the owner selected for the bridge."""
        value = self._store.get(PROVIDER_KEY, '')
        return value if isinstance(value, str) else ''

    @property
    def paid_consent(self) -> bool:
        """Whether the owner allows a paid provider to answer for the bridge."""
        return bool(self._store.get(CONSENT_KEY, False))

    @property
    def memory_sync(self) -> bool:
        """Whether the owner allows memory to be synchronised."""
        return bool(self._store.get(MEMORY_KEY, False))

    def configure(self, provider: str, *, paid_consent: bool = False,
                  memory_sync: bool = False) -> None:
        """Record the owner's choice. Called by the bridge page."""
        self._store.set(PROVIDER_KEY, provider or '')
        self._store.set(CONSENT_KEY, bool(paid_consent))
        self._store.set(MEMORY_KEY, bool(memory_sync))

    # ----------------------------------------------------------------- answer

    def answer(self, message: str, consent: bool) -> dict:
        """Answer one message, or explain why it cannot be answered."""
        if self._policy is not None and self._policy.stopped:
            raise BridgeHandlerError(503, 'The Windows desktop is stopped. Resume it first.')
        provider = self.provider
        if not provider:
            raise BridgeHandlerError(503, 'The Windows desktop has not chosen a provider for paired devices.')
        try:
            spec = self._router.spec(provider)
        except KeyError:
            raise BridgeHandlerError(503, 'The chosen provider is not known to this desktop.') from None
        if not spec.local:
            if not self.paid_consent:
                raise BridgeHandlerError(403, 'The Windows desktop has not allowed a paid provider for paired devices.')
            if not consent:
                raise BridgeHandlerError(403, 'This request did not carry the consent to use a paid provider.')
        model = self._store.get('model:' + provider) or spec.default_model
        key = '' if spec.local else (self._vault.get(provider) or '')
        if not spec.local and not key:
            raise BridgeHandlerError(403, 'The Windows desktop has no key for that provider.')
        messages = self._messages(message)
        started = time.monotonic()
        try:
            text = self._router.stream(spec, model, key, messages, self._check,
                                        self._emit)
        except ProviderError as error:
            raise BridgeHandlerError(502, str(error)) from None
        except Exception:
            raise BridgeHandlerError(502, 'The provider call failed. No credentials were logged.') from None
        finally:
            key = ''
        self._remember(message, text)
        return {
            'text': text,
            'provider': provider,
            'model': model,
            'duration_ms': round((time.monotonic() - started) * 1000),
            'local': bool(spec.local),
        }

    # ---------------------------------------------------------------- helpers

    def _messages(self, message: str) -> list[dict]:
        """The message list sent to the provider, with the short history."""
        system = 'You are JARVIS, the assistant on the owner\'s Windows computer. ' \
                 'Answer briefly and plainly. The person is the owner\'s own paired device.'
        return [{'role': 'system', 'content': system}] + list(self._history) + [
            {'role': 'user', 'content': message}]

    def _remember(self, message: str, answer: str) -> None:
        """Keep the last few turns so the answer can refer to them."""
        self._history.append({'role': 'user', 'content': message})
        self._history.append({'role': 'assistant', 'content': answer})
        while len(self._history) > MAX_HISTORY:
            del self._history[0]

    def _check(self) -> None:
        """The provider call checks the emergency stop between chunks."""
        if self._policy is not None:
            self._policy.check(self._policy.ticket)

    @staticmethod
    def _emit(chunk: str) -> None:
        """The bridge answers in one piece, so chunks are dropped."""
