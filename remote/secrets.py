"""Secret storage for the bridge.

The bridge secrets live in the Windows credential vault next to the provider
keys. The adapter keeps the vault behind a small mapping interface so the
pairing registry never writes a secret to a file or to a log.
"""
from security.vault import Vault


class VaultSecrets:
    """Stores bridge secrets in the Windows credential vault.

    The vault is Windows only. On another system the adapter raises, so a
    pairing cannot silently fall back to a plaintext file.
    """

    PREFIX = 'bridge:'

    def __init__(self, vault: Vault | None = None):
        self._vault = vault if vault is not None else Vault()

    def _name(self, key: str) -> str:
        return self.PREFIX + key

    def __getitem__(self, key: str) -> str:
        return self._vault.get(self._name(key))

    def __setitem__(self, key: str, value: str) -> None:
        self._vault.put(self._name(key), value)

    def __delitem__(self, key: str) -> None:
        self._vault.delete(self._name(key))

    def get(self, key: str, default=None):
        try:
            value = self._vault.get(self._name(key))
        except Exception:
            raise
        return value or default

    def pop(self, key: str, default=None):
        value = self.get(key, None)
        if value:
            self._vault.delete(self._name(key))
            return value
        return default
