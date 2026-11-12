"""Provider router: one selection policy and one dispatch point.

The router never chooses a provider on its own. The owner picks the preferred
provider in the interface, and the router only applies the recorded rules:

- a provider must be configured and healthy;
- fallback happens only with explicit consent;
- offline mode can only use a local provider, so an offline request can never
  reach a paid cloud endpoint.

The router also dispatches to the adapter that matches the provider shape, so
Claude, the OpenAI compatible services and the local model share one call
site.
"""
from providers import chat, claude, ollama
from providers.registry import ProviderSpec, specs
from providers.selection import NoProviderAvailable, Provider, choose_provider


class ProviderRouter:
    """Selects a provider and streams one answer with the matching adapter."""

    def __init__(self, registry=None, *, health=None, transport=None):
        self._specs = dict(registry) if registry is not None else specs()
        self._health = dict(health) if health else {}
        self._transport = transport

    # ------------------------------------------------------------- selection

    def names(self) -> list[str]:
        """Every provider this router knows."""
        return list(self._specs)

    def spec(self, name: str) -> ProviderSpec:
        """Look up one provider."""
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError('Unknown provider.') from None

    def healthy(self, name: str) -> bool:
        """Whether a provider is currently reported healthy."""
        return bool(self._health.get(name, True))

    def available(self, configured) -> list[Provider]:
        """The selection view of the registry."""
        names = set(configured)
        return [
            Provider(name=name, configured=name in names, healthy=self.healthy(name),
                     local=spec.local)
            for name, spec in self._specs.items()
        ]

    def select(self, preferred: str, *, configured, allow_fallback: bool = False,
               offline_only: bool = False) -> ProviderSpec:
        """Return the provider to use, or raise `NoProviderAvailable`.

        `allow_fallback` and `offline_only` are explicit decisions by the
        caller. There is no implicit fallback and no implicit retry.
        """
        chosen = choose_provider(self.available(configured), preferred,
                                 allow_fallback=allow_fallback, offline_only=offline_only)
        return self._specs[chosen.name]

    # -------------------------------------------------------------- dispatch

    def stream(self, spec: ProviderSpec, model: str, key: str, messages, check, emit,
               transport=None, metrics=None) -> str:
        """Stream one answer using the adapter that matches the provider."""
        transport = transport if transport is not None else self._transport
        if spec.auth == 'anthropic':
            return claude.stream_claude(model, key, messages, check, emit,
                                         transport=transport, metrics=metrics)
        if spec.local:
            # A local provider never receives a key, even when one is supplied.
            return ollama.stream_local(model, messages, check, emit,
                                       transport=transport, metrics=metrics)
        return chat.stream_chat(spec.name, model, key, messages, check, emit,
                                transport=transport, metrics=metrics)


__all__ = ['NoProviderAvailable', 'ProviderRouter', 'ProviderSpec']
