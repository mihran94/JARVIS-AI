"""The TLS certificate of the private bridge listener.

WHAT THIS IS FOR
    The desktop does not run a certificate authority. It either uses a
    certificate the owner provides, or it makes a self-signed one for the
    private listener, so the bridge works out of the box without the owner
    having to buy or run a certificate authority.

    A phone that talks to that listener pins the certificate by its
    fingerprint. The fingerprint is the SHA-256 of the DER form of the
    certificate, written as lowercase hex, and it travels in the pairing
    code so the phone knows which certificate to trust before it sends
    anything.

WHY THE FINGERPRINT IS COMPUTED FROM THE PEM ALONE
    The fingerprint can be shown before the listener is started, and before
    the phone is paired, so the owner can read it out. Nothing has to be
    listening for the owner to see what the phone will pin.

WHAT THIS MODULE WILL NOT DO
    * It never contacts anything. It reads and writes local files, so it
      can be tested without a network, without a key and without a window.
    * It never sends the private key anywhere. The key is written with
      owner-only permissions and stays on this machine.
    * It never trusts a certificate authority. The certificate is for the
      private listener only, and the phone pins it by fingerprint, so it
      does not have to be signed by anybody.
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
    """A short description of the certificate, for the owner.

    The SHA-256 fingerprint is always in it, because that is the number
    the owner compares with the phone. The subject and the expiry are
    added when OpenSSL can read them.
    """
    try:
        with open(path, 'rb') as handle:
            digest = fingerprint(handle.read())
    except (OSError, CertificateError) as error:
        return 'The certificate could not be read: ' + str(error)
    description = 'SHA-256 ' + digest
    openssl = shutil.which('openssl')
    if not openssl:
        return description
    try:
        result = subprocess.run(
            [openssl, 'x509', '-in', path, '-noout', '-subject', '-enddate'],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return description
    if result.returncode != 0:
        return description
    return description + ' • ' + ' '.join(result.stdout.split())


def create_certificate(cert_path: str, key_path: str,
                       subject: str = DEFAULT_SUBJECT,
                       validity_days: int = DEFAULT_VALIDITY_DAYS) -> str:
    """Create a self-signed certificate and its key, and return the fingerprint.

    The key never leaves the machine that made it. The certificate is for
    the private listener only: the phone pins it, so it does not have to be
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
    """The fingerprint of the certificate, creating one when it is needed.

    A certificate without its key, or a key without its certificate, is
    refused rather than silently replaced: the owner may have moved one of
    them on purpose, and overwriting a key is not something to do quietly.
    """
    if cert_path and os.path.exists(cert_path):
        if key_path and not os.path.exists(key_path):
            raise CertificateError(
                'The certificate is there but its key is missing. Point at the key '
                'that belongs to it, or create a new pair.')
        return fingerprint_from_file(cert_path)
    if cert_path and key_path and os.path.exists(key_path):
        raise CertificateError(
            'The key is there but the certificate is missing. Delete the key or '
            'point at the certificate that belongs to it.')
    return create_certificate(cert_path, key_path)
