"""Loopback address checks.

A local service must only be reachable from this machine. The same rule
applies to the local model and to the bridge listener, so the check lives in
one place.
"""
from urllib.parse import urlparse

LOOPBACK_HOSTS = ('127.0.0.1', '::1', 'localhost')


def is_loopback_host(host: str) -> bool:
    """True when a bare host name or address is this machine."""
    if not host:
        return False
    return str(host).strip().lower() in LOOPBACK_HOSTS


def is_loopback_url(url: str) -> bool:
    """True when the URL points at this machine."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return host in LOOPBACK_HOSTS
