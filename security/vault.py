"""Use the Windows credential backend explicitly; never a plaintext fallback."""
import sys

from core.runtime_profile import development_profile


class Vault:
    SERVICE = 'JARVIS-AI-0.1'

    def __init__(self):
        profile = development_profile()
        self.service = f'{self.SERVICE}-development-{profile}' if profile else self.SERVICE

    def _backend(self):
        if sys.platform != 'win32':
            raise RuntimeError('Credential storage requires Windows Credential Manager.')
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()

    def get(self, provider):
        return self._backend().get_password(self.service, provider) or ''

    def put(self, provider, secret):
        if not secret.strip() or chr(10) in secret or chr(13) in secret:
            raise ValueError('Enter a valid single-line API key.')
        self._backend().set_password(self.service, provider, secret.strip())

    def delete(self, provider):
        backend = self._backend()
        if backend.get_password(self.service, provider):
            backend.delete_password(self.service, provider)
