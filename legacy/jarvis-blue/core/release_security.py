"""Ed25519 verification with owner-pinned public keys; never trust keys in a feed."""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ('format', 'version', 'url', 'sha256', 'notes', 'expires', 'key_id')
DOMAIN = b'Jarvis-Blue signed update v1\x00'


def canonical(manifest):
    if not isinstance(manifest, dict) or any(not isinstance(manifest.get(k), str) for k in FIELDS):
        raise ValueError('Malformed signed update manifest.')
    if len(manifest['notes']) > 20000:
        raise ValueError('Release notes exceed size limit.')
    return DOMAIN + json.dumps({k: manifest[k] for k in FIELDS},
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def trusted_keys():
    path = Path(__file__).with_name('update_trust.json')
    block = json.loads(path.read_text(encoding='utf-8'))
    if block.get('schema') != 1 or not isinstance(block.get('keys'), dict):
        raise ValueError('Invalid update public-key configuration.')
    return block['keys']


def verify(manifest):
    data = canonical(manifest)
    keys = trusted_keys()
    if not keys:
        raise ValueError('Update signing is not activated: pin the owner public key first.')
    key = keys.get(manifest['key_id'])
    if not key:
        raise ValueError('Unknown update signing key; release rejected.')
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True))
        signature = base64.b64decode(manifest['signature'], validate=True)
        public.verify(signature, data)
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError('Invalid update signature; release rejected.') from error
    except ImportError as error:
        raise ValueError('Install the existing cryptography requirement before updating.') from error
    except Exception as error:
        from cryptography.exceptions import InvalidSignature
        if isinstance(error, InvalidSignature):
            raise ValueError('Invalid update signature; release rejected.') from error
        raise
    try:
        expires = datetime.strptime(manifest['expires'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError('Invalid release expiry timestamp.') from error
    if expires <= datetime.now(timezone.utc):
        raise ValueError('Signed update manifest has expired; release rejected.')
    return True
