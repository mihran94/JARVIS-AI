"""The TLS certificate of the private bridge listener.

The desktop does not run a certificate authority. It either uses the
certificate the owner provides, or it creates a self-signed one for the
private listener so the bridge works out of the box. A phone that talks to
that listener pins the certificate by its fingerprint, and the fingerprint
travels in the pairing code.

The fingerprint is the SHA-256 of the DER form of the certificate, written as
lowercase hex. It is computed from the PEM file alone, so it can be shown
before the listener is started.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess

#: The block markers of a PEM certificate.
_PEM_CERTIFICATE = re.compile(
    rb'-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----', re.DOTALL)

#: How long a certificate that is created here stays valid.
DEFAULT_VALIDITY_DAYS = 825

#: The subject of a certificate that is created here.
DEFAULT_SUBJECT = '/CN=JARVIS AI bridge/O=JARVIS AI'


class CertificateError(RuntimeError):
    """A certificate could not be read or created."""


def _der_from_pem(pem: bytes) -> bytes:
    """The DER bytes of the first certificate in a PEM text."""
    match = _PEM_CERTIFICATE.search(pem)
    if not match:
        raise CertificateError('The file does not hold a PEM certificate.')
    body = re.sub(rb'\s+', b'', match.group(1))
    try:
        return base64.b64decode(body, validate=True)
    except (ValueError, TypeError):
        raise CertificateError('The PEM certificate is damaged.') from None


def fingerprint(pem: bytes | str) -> str:
    """The SHA-256 fingerprint of a PEM certificate, as lowercase hex."""
    if isinstance(pem, str):
        pem = pem.encode('utf-8')
    return hashlib.sha256(_der_from_pem(pem)).hexdigest()


def fingerprint_from_file(path: str) -> str:
    """The SHA-256 fingerprint of the certificate in a file."""
    try:
        with open(path, 'rb') as handle:
            return fingerprint(handle.read())
    except OSError as error:
        raise CertificateError(f'The certificate could not be read: {error}') from None


def describe(path: str) -> str:
    """A short description of the certificate, for the owner."""
    try:
        with open(path, 'rb') as handle:
            fingerprint(handle.read())
    except (OSError, CertificateError) as error:
        return 'The certificate could not be read: ' + str(error)
    openssl = shutil.which('openssl')
    if not openssl:
        return 'SHA-256 ' + fingerprint_from_file(path)
    try:
        result = subprocess.run(
            [openssl, 'x509', '-in', path, '-noout', '-subject', '-enddate'],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 'SHA-256 ' + fingerprint_from_file(path)
    if result.returncode != 0:
        return 'SHA-256 ' + fingerprint_from_file(path)
    return ' '.join(result.stdout.split())


def create_certificate(cert_path: str, key_path: str,
                       subject: str = DEFAULT_SUBJECT,
                       validity_days: int = DEFAULT_VALIDITY_DAYS) -> str:
    """Create a self-signed certificate and its key.

    The key never leaves the machine that made it. The certificate is for the
    private listener only: the phone pins it, so it does not have to be
    signed by a public authority.
    """
    openssl = shutil.which('openssl')
    if not openssl:
        raise CertificateError(
            'OpenSSL was not found, so a certificate could not be created. '
            'Provide a PEM certificate and key instead.')
    for path in (cert_path, key_path):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
    try:
        result = subprocess.run(
            [openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
             '-keyout', key_path, '-out', cert_path,
             '-days', str(int(validity_days)), '-subj', subject],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CertificateError(f'The certificate could not be created: {error}') from None
    if result.returncode != 0:
        raise CertificateError(
            'The certificate could not be created: ' + (result.stderr or '').strip())
    # The key is only readable by the owner of the machine.
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return fingerprint_from_file(cert_path)


def ensure_certificate(cert_path: str, key_path: str) -> str:
    """The fingerprint of the certificate, creating one when needed."""
    if cert_path and os.path.exists(cert_path):
        return fingerprint_from_file(cert_path)
    if cert_path and key_path and os.path.exists(key_path):
        raise CertificateError(
            'The key is there but the certificate is missing. Delete the key or '
            'point at the certificate that belongs to it.')
    return create_certificate(cert_path, key_path)
