"""Backup and restore of the JARVIS history database.

WHAT THIS IS
    The owner's conversations, the saved notes, the task history and the
    usage ledger live in one SQLite file, `history.sqlite3`. This module
    takes a consistent copy of that file, encrypts it, and puts it
    somewhere the owner chose. It also restores one, and it never
    overwrites live history without keeping the old copy first.

WHAT THIS IS NOT
    * It is not an encryption of the live database. The running database
      stays a plain SQLite file, exactly as it is today, so the
      application keeps opening it in milliseconds. What this module
      encrypts is the *backup*, and the module says so plainly.
    * It is not a cloud backup. Nothing leaves the machine.
    * It does not restore over an existing database without protecting
      it. The current file is copied aside first, and the restore
      reports where that copy went.

THE ENCRYPTION
    The archive is encrypted with a key derived from a passphrase using
    scrypt, and the payload is sealed with HMAC-SHA256 in counter mode
    and authenticated with a separate HMAC. There is no dependency
    beyond the standard library, so the backup works on a machine that
    has never seen an extra package.

    On Windows the passphrase is not stored at all: the derived key is
    wrapped with DPAPI (`CryptProtectData`), which means only the
    Windows user who made the backup can unwrap it. On other systems
    the passphrase is required to restore, and the archive records that
    it was not sealed with a Windows key.

THE FORMAT
    A backup is a single file with a small text header and the sealed
    payload:

        JARVIS-BACKUP-1 <json header>\\n<binary payload>

    The header carries the creation time, the size of the plain
    database, its SHA-256, the schema version and the tables it holds.
    It is readable without the passphrase, so the owner can see what a
    backup is before restoring it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import tempfile

#: The marker at the start of every backup file.
MAGIC = 'JARVIS-BACKUP-1'

#: The scrypt cost parameters. They are recorded in the header, so a
#: future version can raise them and still read the old archives.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LENGTH = 32
SCRYPT_SALT_BYTES = 16

#: The memory scrypt may use. The default in OpenSSL is too small for
#: the cost this module asks for, and the failure is an error rather
#: than a weaker key.
SCRYPT_MAXMEM = 96 * 1024 * 1024

#: The key length used for the payload cipher.
KEY_BYTES = 32

#: The size of one counter block.
BLOCK_BYTES = 32

#: The maximum size of a backup file that will be read.
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024

#: The schema versions this module can restore.
SUPPORTED_SCHEMA = (1, 2, 3)


class BackupError(RuntimeError):
    """A backup could not be made, read or restored."""


class BackupLocked(BackupError):
    """The archive needs a passphrase or a Windows key that was not given."""


@dataclass(frozen=True)
class BackupHeader:
    """What an archive says about itself, readable without the key."""

    created: str
    source: str
    plain_bytes: int
    plain_sha256: str
    schema_version: int
    tables: tuple = ()
    sealed_with_windows_key: bool = False
    note_count: int = 0
    message_count: int = 0
    kdf: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            'created': self.created,
            'source': self.source,
            'plain_bytes': self.plain_bytes,
            'plain_sha256': self.plain_sha256,
            'schema_version': self.schema_version,
            'tables': list(self.tables),
            'sealed_with_windows_key': self.sealed_with_windows_key,
            'note_count': self.note_count,
            'message_count': self.message_count,
            'kdf': dict(self.kdf),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BackupHeader':
        try:
            return cls(
                created=str(data['created']),
                source=str(data['source']),
                plain_bytes=int(data['plain_bytes']),
                plain_sha256=str(data['plain_sha256']),
                schema_version=int(data['schema_version']),
                tables=tuple(data.get('tables') or ()),
                sealed_with_windows_key=bool(data.get('sealed_with_windows_key', False)),
                note_count=int(data.get('note_count', 0)),
                message_count=int(data.get('message_count', 0)),
                kdf=dict(data.get('kdf') or {}),
            )
        except (KeyError, TypeError, ValueError):
            raise BackupError('The backup header is not readable.') from None


@dataclass
class BackupResult:
    """What a backup or a restore actually did."""

    path: Path
    created: str
    bytes: int
    sha256: str
    encrypted: bool
    sealed_with_windows_key: bool = False
    replaced: bool = False
    previous_copy: Path | None = None
    note_count: int = 0
    message_count: int = 0
    message: str = ''


# ── the crypto ─────────────────────────────────────────────────────────────


def derive_key(passphrase: str, salt: bytes, *, n: int = SCRYPT_N, r: int = SCRYPT_R,
                p: int = SCRYPT_P) -> bytes:
    """Derive the payload key from a passphrase.

    The cost parameters are arguments, because the archive records the
    ones that were used. A backup made with older, cheaper parameters
    still opens.
    """
    if not isinstance(passphrase, str) or not passphrase:
        raise BackupError('A passphrase is required to seal a backup.')
    try:
        return hashlib.scrypt(passphrase.encode('utf-8'), salt=salt, n=int(n), r=int(r),
                               p=int(p), dklen=SCRYPT_LENGTH, maxmem=SCRYPT_MAXMEM)
    except ValueError:
        raise BackupError('This machine cannot derive a key with those parameters.') from None


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    """The keystream for HMAC-SHA256 in counter mode."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + struct.pack('>Q', counter), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def seal(plain: bytes, key: bytes, nonce: bytes) -> bytes:
    """Encrypt and authenticate the payload."""
    if len(key) != KEY_BYTES:
        raise BackupError('The sealing key is not the right length.')
    if len(nonce) != 16:
        raise BackupError('The nonce is not the right length.')
    stream = _stream(key, nonce, len(plain))
    cipher = bytes(a ^ b for a, b in zip(plain, stream))
    tag = hmac.new(key, b'tag' + nonce + cipher, hashlib.sha256).digest()
    return cipher + tag


def unseal(payload: bytes, key: bytes, nonce: bytes) -> bytes:
    """Decrypt and verify the payload."""
    if len(payload) < 32:
        raise BackupError('The backup payload is truncated.')
    cipher, tag = payload[:-32], payload[-32:]
    expected = hmac.new(key, b'tag' + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise BackupLocked('The passphrase is wrong, or the backup was changed.')
    stream = _stream(key, nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream))


# ── the Windows key ────────────────────────────────────────────────────────


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: DATA_BLOB) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b''
    return ctypes.string_at(blob.pbData, blob.cbData)


def windows_available() -> bool:
    """Whether this machine has the Windows key facility."""
    return sys.platform == 'win32'


def protect_for_windows(data: bytes) -> bytes:
    """Wrap a key so only this Windows user can unwrap it.

    The key never leaves this machine in a readable form, and it cannot
    be unwrapped by another user or by another computer.
    """
    if not windows_available():
        raise BackupError('The Windows key facility is only available on Windows.')
    from ctypes import wintypes as wt
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    source = _blob(data)
    output = DATA_BLOB()
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wt.LPCWSTR,
                                          ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                                          ctypes.c_void_p, wt.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = wt.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), 'JARVIS history backup', None,
                                    None, None, 0, ctypes.byref(output)):
        raise BackupError('Windows could not protect the backup key.')
    try:
        return _from_blob(output)
    finally:
        kernel32.LocalFree(output.pbData)


def unprotect_for_windows(data: bytes) -> bytes:
    """Unwrap a key that Windows protected."""
    if not windows_available():
        raise BackupError('The Windows key facility is only available on Windows.')
    from ctypes import wintypes as wt
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    source = _blob(data)
    output = DATA_BLOB()
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wt.LPWSTR),
                                            ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                                            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0,
                                      ctypes.byref(output)):
        raise BackupLocked('This backup was sealed for a different Windows user, '
                           'or by another computer.')
    try:
        return _from_blob(output)
    finally:
        kernel32.LocalFree(output.pbData)


def _windows_key_path(destination: Path) -> Path:
    """Where the wrapped key is kept next to the archive."""
    return destination.with_name(destination.name + '.key')


# ── the database work ──────────────────────────────────────────────────────


def _database_summary(path: Path) -> tuple:
    """The schema version, the tables and the row counts of a database."""
    try:
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=10)
    except sqlite3.Error as error:
        raise BackupError(f'The history database could not be read: {error}') from None
    try:
        version = int(db.execute('PRAGMA user_version').fetchone()[0])
        tables = tuple(sorted(row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")))
        notes = messages = 0
        if 'memories' in tables:
            notes = int(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0])
        if 'messages' in tables:
            messages = int(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
        return version, tables, notes, messages
    except sqlite3.Error:
        return 0, (), 0, 0
    finally:
        db.close()


def _consistent_copy(source: Path, destination: Path) -> None:
    """A copy of the database taken through SQLite, so it is never torn.

    The application may be writing while the backup is taken. Copying the
    file itself would capture a half-written page; SQLite's own backup
    takes a consistent snapshot instead.
    """
    try:
        origin = sqlite3.connect(str(source), timeout=15)
    except sqlite3.Error as error:
        raise BackupError(f'The history database could not be opened: {error}') from None
    try:
        target = sqlite3.connect(str(destination))
        try:
            origin.backup(target)
            target.commit()
        finally:
            target.close()
    except sqlite3.Error as error:
        raise BackupError(f'The history database could not be copied: {error}') from None
    finally:
        origin.close()


# ── the archive file ───────────────────────────────────────────────────────


def _read_archive(path: Path) -> tuple:
    """Read an archive into its header and its sealed payload."""
    try:
        size = path.stat().st_size
    except OSError:
        raise BackupError('The backup file is not there.') from None
    if size > MAX_ARCHIVE_BYTES:
        raise BackupError('The backup file is larger than this module will read.')
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise BackupError(f'The backup file could not be read: {error}') from None
    if not raw.startswith(MAGIC.encode('ascii')):
        raise BackupError('That file is not a JARVIS backup.')
    newline = raw.find(b'\n')
    if newline < 0:
        raise BackupError('The backup file is not readable.')
    try:
        header = BackupHeader.from_dict(json.loads(raw[len(MAGIC) + 1:newline].decode('utf-8')))
    except (ValueError, UnicodeDecodeError):
        raise BackupError('The backup header is not readable.') from None
    return header, raw[newline + 1:]


def inspect_backup(path) -> BackupHeader:
    """What an archive holds, without needing its key."""
    return _read_archive(Path(path))[0]


# ── making a backup ────────────────────────────────────────────────────────


def create_backup(source, destination, *, passphrase: str = '',
                  windows_key: bool = False) -> BackupResult:
    """Write an encrypted backup of the history database.

    `passphrase` is used when `windows_key` is False. When `windows_key`
    is True the derived key is wrapped with Windows DPAPI next to the
    archive, and no passphrase is needed to restore it on the same
    Windows user.
    """
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise BackupError('The history database is not there.')
    if destination.exists():
        raise BackupError('Choose a new name for the backup; that file already exists.')
    if windows_key and not windows_available():
        raise BackupError('A Windows key can only be made on Windows. '
                          'Use a passphrase on this machine.')
    if not windows_key and not passphrase:
        raise BackupError('Give a passphrase, or ask for a Windows key.')

    version, tables, notes, messages = _database_summary(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jarvis-backup-') as work:
        plain_path = Path(work) / 'history.sqlite3'
        _consistent_copy(source, plain_path)
        plain = plain_path.read_bytes()
        digest = hashlib.sha256(plain).hexdigest()

        salt = os.urandom(SCRYPT_SALT_BYTES)
        nonce = os.urandom(16)
        if windows_key:
            key = os.urandom(KEY_BYTES)
            kdf = {'name': 'windows-key'}
        else:
            key = derive_key(passphrase, salt)
            kdf = {'name': 'scrypt', 'n': SCRYPT_N, 'r': SCRYPT_R, 'p': SCRYPT_P,
                   'salt': salt.hex()}
        payload = seal(plain, key, nonce)

        header = BackupHeader(
            created=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            source=source.name,
            plain_bytes=len(plain),
            plain_sha256=digest,
            schema_version=version,
            tables=tables,
            sealed_with_windows_key=windows_key,
            note_count=notes,
            message_count=messages,
            kdf=kdf,
        )
        header_bytes = json.dumps(header.as_dict(), ensure_ascii=False).encode('utf-8')
        with destination.open('xb') as output:
            output.write(MAGIC.encode('ascii') + b' ' + header_bytes + b'\n')
            output.write(salt + nonce + payload)
        if windows_key:
            try:
                _windows_key_path(destination).write_bytes(protect_for_windows(key))
            except Exception:
                destination.unlink(missing_ok=True)
                raise

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return BackupResult(
        path=destination,
        created=header.created,
        bytes=destination.stat().st_size,
        sha256=digest,
        encrypted=True,
        sealed_with_windows_key=windows_key,
        note_count=notes,
        message_count=messages,
        message=('The backup is sealed with this Windows account.'
                 if windows_key else
                 'The backup is sealed with your passphrase. It cannot be opened '
                 'without it.'),
    )


# ── restoring a backup ─────────────────────────────────────────────────────


def _open_key(archive: Path, header: BackupHeader, passphrase: str):
    """The payload key for an archive, from the passphrase or the Windows key."""
    if header.sealed_with_windows_key:
        key_file = _windows_key_path(archive)
        if not key_file.is_file():
            raise BackupLocked('The Windows key for this backup is not beside it. '
                               'The backup cannot be opened on this computer.')
        return unprotect_for_windows(key_file.read_bytes())
    if not passphrase:
        raise BackupLocked('This backup needs its passphrase.')
    kdf = header.kdf or {}
    salt = bytes.fromhex(kdf.get('salt', '')) if kdf.get('salt') else b''
    if not salt:
        raise BackupError('The backup does not say how its key was made.')
    salt, nonce, payload = _split_payload(_read_archive(archive)[1])
    key = derive_key(passphrase, salt, n=kdf.get('n', SCRYPT_N), r=kdf.get('r', SCRYPT_R),
                     p=kdf.get('p', SCRYPT_P))
    unseal(payload, key, nonce)  # proves the passphrase before anything is written
    return key


def _split_payload(body: bytes) -> tuple:
    """The salt, the nonce and the sealed payload of an archive body."""
    if len(body) < SCRYPT_SALT_BYTES + 16 + 32:
        raise BackupError('The backup payload is truncated.')
    salt = body[:SCRYPT_SALT_BYTES]
    nonce = body[SCRYPT_SALT_BYTES:SCRYPT_SALT_BYTES + 16]
    payload = body[SCRYPT_SALT_BYTES + 16:]
    return salt, nonce, payload


def verify_backup(path, *, passphrase: str = '') -> BackupHeader:
    """Check that an archive opens and matches its header, without writing."""
    archive = Path(path)
    header, body = _read_archive(archive)
    key = _open_key(archive, header, passphrase)
    salt, nonce, payload = _split_payload(body)
    plain = unseal(payload, key, nonce)
    digest = hashlib.sha256(plain).hexdigest()
    if digest != header.plain_sha256:
        raise BackupError('The backup does not match its own header. It was changed '
                          'or it is damaged.')
    return header


def restore_backup(archive, destination, *, passphrase: str = '',
                   keep_previous: bool = True, overwrite: bool = False) -> BackupResult:
    """Restore an archive over the live history database.

    The current database is copied aside before it is replaced, so the
    owner can go back. The restore is refused when the destination
    exists and `overwrite` is not set.
    """
    archive = Path(archive)
    destination = Path(destination)
    header, body = _read_archive(archive)
    if header.schema_version > max(SUPPORTED_SCHEMA):
        raise BackupError('That backup was made by a newer JARVIS than this one.')
    if destination.exists() and not overwrite:
        raise BackupError('There is already a history database there. '
                          'Restore over it only when you mean to.')

    key = _open_key(archive, header, passphrase)
    salt, nonce, payload = _split_payload(body)
    plain = unseal(payload, key, nonce)
    if hashlib.sha256(plain).hexdigest() != header.plain_sha256:
        raise BackupError('The backup does not match its own header. It was changed '
                          'or it is damaged.')

    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    with tempfile.TemporaryDirectory(prefix='jarvis-restore-') as work:
        staged = Path(work) / 'history.sqlite3'
        staged.write_bytes(plain)
        version, tables, notes, messages = _database_summary(staged)
        if version and version not in SUPPORTED_SCHEMA:
            raise BackupError('That backup uses a history format this JARVIS does not read.')
        if destination.exists() and keep_previous:
            previous = destination.with_name(
                f'{destination.name}.before-restore-{datetime.now().strftime("%Y%m%d-%H%M%S")}')
            shutil.copy2(destination, previous)
        os.replace(staged, destination)
        for suffix in ('-wal', '-shm'):
            extra = Path(str(destination) + suffix)
            if extra.exists():
                extra.unlink()

    return BackupResult(
        path=archive,
        created=header.created,
        bytes=archive.stat().st_size,
        sha256=header.plain_sha256,
        encrypted=True,
        sealed_with_windows_key=header.sealed_with_windows_key,
        replaced=True,
        previous_copy=previous,
        note_count=notes,
        message_count=messages,
        message=('The history was restored. The previous database was kept at '
                 f'{previous}.' if previous else 'The history was restored.'),
    )


__all__ = ['BackupError', 'BackupHeader', 'BackupLocked', 'BackupResult',
           'MAGIC', 'MAX_ARCHIVE_BYTES', 'SUPPORTED_SCHEMA',
           'create_backup', 'derive_key', 'inspect_backup', 'protect_for_windows',
           'restore_backup', 'seal', 'unprotect_for_windows', 'unseal',
           'verify_backup', 'windows_available']
