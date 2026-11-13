"""Owner-only offline update-key setup. Private keys must stay outside the project."""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def generate(directory):
    directory = directory.expanduser().resolve()
    if directory.is_relative_to(ROOT) or ROOT.is_relative_to(directory):
        raise ValueError('Choose a dedicated private key directory outside the project tree.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(directory.iterdir()):
        raise ValueError('Key output directory must be empty; existing keys are never overwritten.')
    password = getpass.getpass('New private-key password (minimum 12 characters): ')
    if len(password) < 12 or password != getpass.getpass('Repeat password: '):
        raise ValueError('Passwords must match and contain at least 12 characters.')
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = hashlib.sha256(public).hexdigest()[:24]
    encoded = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode('utf-8')))
    path = directory / 'update-private.pem'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
    trust = {'schema': 1, 'keys': {key_id: base64.b64encode(public).decode('ascii')}}
    (directory / 'update-public.json').write_text(json.dumps(trust, indent=2), encoding='utf-8')
    print('Encrypted private key and public trust file created locally. Keep private key and password offline.')
    print('Public key fingerprint: ' + hashlib.sha256(public).hexdigest())


def pin(public_file):
    block = json.loads(public_file.read_text(encoding='utf-8'))
    if block.get('schema') != 1 or not isinstance(block.get('keys'), dict) or not block['keys']:
        raise ValueError('Invalid public trust file.')
    for key_id, key in block['keys'].items():
        raw = base64.b64decode(key, validate=True)
        if len(raw) != 32 or hashlib.sha256(raw).hexdigest()[:24] != key_id:
            raise ValueError('Invalid key fingerprint.')
    target = ROOT / 'core/update_trust.json'
    current = json.loads(target.read_text())
    if current.get('keys'):
        raise ValueError('Keys already pinned. Rotation requires a reviewed update; refusing overwrite.')
    target.write_text(json.dumps(block, indent=2), encoding='utf-8')
    print('Public key pinned. Commit only core/update_trust.json; never the private key.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('generate').add_argument('directory', type=Path)
    commands.add_parser('pin').add_argument('public_file', type=Path)
    args = parser.parse_args()
    try:
        generate(args.directory) if args.command == 'generate' else pin(args.public_file)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')

if __name__ == '__main__':
    main()
