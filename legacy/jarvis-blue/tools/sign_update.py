"""Sign prepared latest.json using an owner-held encrypted Ed25519 private key."""
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.release_security import canonical, trusted_keys


def sign(manifest, key, days=14):
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('An Ed25519 private key is required.')
    if not 1 <= days <= 90:
        raise ValueError('Expiry must be between 1 and 90 days.')
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = hashlib.sha256(public).hexdigest()[:24]
    if trusted_keys().get(key_id) != base64.b64encode(public).decode('ascii'):
        raise ValueError('This signing key is not pinned in the application. Pin its public key first.')
    result = dict(manifest)
    result.pop('available', None)
    result['key_id'] = key_id
    result['expires'] = (datetime.now(timezone.utc) + timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    result['signature'] = base64.b64encode(key.sign(canonical(result))).decode('ascii')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--private-key', type=Path, required=True)
    parser.add_argument('--days', type=int, default=14)
    args = parser.parse_args()
    if args.private_key.resolve().is_relative_to(ROOT):
        parser.error('The private key must be stored outside the project.')
    password = getpass.getpass('Private-key password: ').encode('utf-8')
    key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=password)
    result = sign(json.loads(args.manifest.read_text(encoding='utf-8')), key, args.days)
    args.manifest.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Manifest signed. Verify signature before publishing. Do not edit signed fields afterward.')

if __name__ == '__main__':
    main()
