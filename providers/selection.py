"""Deterministic provider selection policy; no network or secret access.

This module does not implement provider APIs. It only chooses a configured,
healthy provider subject to explicit owner consent and a local-only policy.

The rules are deliberately strict:

- the preferred provider must exist, so a typo never silently falls through to
  another service;
- fallback happens only when the caller explicitly allows it;
- offline mode can only select a local provider, so an offline request never
  reaches a paid cloud endpoint.
"""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Provider:
    name: str
    configured: bool
    healthy: bool
    local: bool = False


class NoProviderAvailable(RuntimeError):
    pass


def choose_provider(
    providers: Iterable[Provider],
    preferred: str,
    *,
    allow_fallback: bool = False,
    offline_only: bool = False,
) -> Provider:
    """Select a provider without implicit paid or remote fallback.

    Explicit preference must exist. Fallback is only to a configured, healthy
    provider, in input order, and only if the caller explicitly opts in.
    """
    items = tuple(providers)
    if len({p.name for p in items}) != len(items):
        raise ValueError("duplicate provider names")
    if not preferred or not any(p.name == preferred for p in items):
        raise ValueError("unknown preferred provider")

    def eligible(p: Provider) -> bool:
        return p.configured and p.healthy and (not offline_only or p.local)

    primary = next(p for p in items if p.name == preferred)
    if eligible(primary):
        return primary
    if allow_fallback:
        for candidate in items:
            if candidate.name != preferred and eligible(candidate):
                return candidate
    raise NoProviderAvailable("no permitted provider available")
