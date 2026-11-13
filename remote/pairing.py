"""Paired device registry with explicit revocation.

A paired device is identified on the wire by its key id, because that is the
only identifier the Android client sends. The shared secret is held by an
injected secret backend: in production that is the Windows credential vault
(`security.vault.Vault`), never a file in the repository.

Pairing is explicit. There is no automatic trust of a device that merely
reaches the port, and revoking a device takes effect on the next request.
"""
from dataclasses import dataclass, field
import secrets as _secrets
import threading
import time
import uuid

from remote.protocol import KEY_ID

PAIRING_METADATA_KEY = 'bridge:paired_devices:v1'
MAX_DEVICE_RECORDS = 32


class PairingError(RuntimeError):
    """The requested pairing operation is not allowed."""


@dataclass(frozen=True)
class PairedDevice:
    """A paired device without its secret."""

    peer_id: str
    key_id: str
    label: str = ''
    paired_at_epoch_ms: int = 0
    last_seen_epoch_ms: int = 0
    revoked: bool = False


@dataclass(frozen=True)
class Pairing:
    """The result of a pairing operation, including the one-time secret."""

    device: PairedDevice
    secret: str = field(repr=False)


class PairingStore:
    """Registry of paired devices and their secrets.

    `secret_backend` is any mapping-like object that stores a secret under a
    key id. `dict` is used by the tests; production passes a vault adapter.
    """

    def __init__(self, secret_backend=None, *, now=time.time, metadata_store=None):
        self._secrets = secret_backend if secret_backend is not None else {}
        self._now = now
        self._metadata_store = metadata_store
        self._lock = threading.RLock()
        self._devices: dict[str, PairedDevice] = self._load_devices()

    def _load_devices(self) -> dict[str, PairedDevice]:
        if self._metadata_store is None:
            return {}
        saved = self._metadata_store.get(PAIRING_METADATA_KEY, [])
        if not isinstance(saved, list) or len(saved) > MAX_DEVICE_RECORDS:
            return {}
        devices = {}
        for item in saved:
            if not isinstance(item, dict):
                continue
            key_id = item.get('key_id')
            peer_id = item.get('peer_id')
            label = item.get('label', '')
            paired = item.get('paired_at_epoch_ms', 0)
            seen = item.get('last_seen_epoch_ms', 0)
            revoked = item.get('revoked', False)
            if (not isinstance(key_id, str) or not key_id or len(key_id) > 128
                    or not isinstance(peer_id, str) or not peer_id or len(peer_id) > 128
                    or not isinstance(label, str) or len(label) > 80
                    or type(paired) is not int or paired < 0
                    or type(seen) is not int or seen < 0
                    or type(revoked) is not bool or key_id in devices):
                continue
            devices[key_id] = PairedDevice(
                peer_id=peer_id, key_id=key_id, label=label,
                paired_at_epoch_ms=paired, last_seen_epoch_ms=seen, revoked=revoked)
        return devices

    def _save_devices(self, devices: dict[str, PairedDevice]) -> None:
        if self._metadata_store is None:
            return
        # Persist only an explicit allowlist of safe metadata, never secrets.
        records = [
            dict(peer_id=dev.peer_id, key_id=dev.key_id, label=dev.label,
                 paired_at_epoch_ms=dev.paired_at_epoch_ms,
                 last_seen_epoch_ms=dev.last_seen_epoch_ms, revoked=dev.revoked)
            for dev in devices.values()
        ]
        self._metadata_store.set(PAIRING_METADATA_KEY, records)

    def pair(self, key_id: str = KEY_ID, label: str = '', secret: str | None = None,
             peer_id: str | None = None) -> Pairing:
        """Pair a device and return its record plus the shared secret.

        The secret is returned once so the owner can transfer it to the phone
        out of band. It is never logged and never returned by `devices()`.
        """
        if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
            raise ValueError('A valid key id is required to pair a device')
        if not isinstance(label, str) or len(label) > 80:
            raise ValueError('A valid device label is required')
        if peer_id is not None and (not isinstance(peer_id, str) or not peer_id or len(peer_id) > 128):
            raise ValueError('A valid device peer id is required')
        if secret is not None and (not isinstance(secret, str) or len(secret) < 32):
            raise ValueError('A pairing secret must be at least 32 characters')
        with self._lock:
            existing = self._devices.get(key_id)
            if existing is not None and not existing.revoked:
                raise PairingError('That key id is already paired.')
            if key_id not in self._devices and len(self._devices) >= MAX_DEVICE_RECORDS:
                raise PairingError('Too many paired-device records.')
            device = PairedDevice(
                peer_id=peer_id or uuid.uuid4().hex,
                key_id=key_id,
                label=label,
                paired_at_epoch_ms=int(self._now() * 1000),
            )
            token = secret or _secrets.token_hex(32)
            self._secrets[key_id] = token
            proposed = dict(self._devices)
            proposed[key_id] = device
            try:
                self._save_devices(proposed)
            except Exception:
                try:
                    self._secrets.pop(key_id, None)
                except Exception:
                    pass
                raise PairingError('Could not save the paired-device record.') from None
            self._devices = proposed
            return Pairing(device=device, secret=token)

    def revoke(self, key_id: str) -> PairedDevice:
        """Revoke a device. Its secret stops working on the next request."""
        with self._lock:
            device = self._devices.get(key_id)
            if device is None:
                raise PairingError('Unknown key id.')
            if device.revoked:
                # Retry deletion if a previous vault operation failed.
                self._secrets.pop(key_id, None)
                return device
            revoked = PairedDevice(
                peer_id=device.peer_id,
                key_id=device.key_id,
                label=device.label,
                paired_at_epoch_ms=device.paired_at_epoch_ms,
                last_seen_epoch_ms=device.last_seen_epoch_ms,
                revoked=True,
            )
            self._devices[key_id] = revoked
            try:
                self._save_devices(self._devices)
            finally:
                self._secrets.pop(key_id, None)
            return revoked

    def device(self, key_id: str) -> PairedDevice | None:
        """Return the device for a key id, or None when unknown or revoked."""
        with self._lock:
            device = self._devices.get(key_id)
            if device is None or device.revoked:
                return None
            return device

    def secret_for(self, key_id: str) -> str | None:
        """Return the shared secret for an active device, else None."""
        with self._lock:
            device = self._devices.get(key_id)
            if device is None or device.revoked:
                return None
            return self._secrets.get(key_id)

    def touch(self, key_id: str) -> None:
        """Record that the device was seen just now."""
        with self._lock:
            device = self._devices.get(key_id)
            if device is None or device.revoked:
                return
            self._devices[key_id] = PairedDevice(
                peer_id=device.peer_id,
                key_id=device.key_id,
                label=device.label,
                paired_at_epoch_ms=device.paired_at_epoch_ms,
                last_seen_epoch_ms=int(self._now() * 1000),
                revoked=device.revoked,
            )
            # Last-seen tracking is advisory, never an auth failure.
            try:
                self._save_devices(self._devices)
            except Exception:
                pass

    def devices(self) -> list[PairedDevice]:
        """All paired devices, including revoked ones, without secrets."""
        with self._lock:
            return sorted(self._devices.values(), key=lambda device: device.paired_at_epoch_ms)
