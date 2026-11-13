# JARVIS bridge protocol, version 1

This is the shared contract between the JARVIS AI desktop and the JARVIS BLUE
Android client. Both halves must agree byte for byte, so the canonical values
below are pinned by tests on each side.

- Desktop half: `remote/` in this repository.
- Phone half: `mihran94/jarvis-blue-android`, `core/windows/BridgeClient.kt`
  and `core/model/WindowsBridge.kt`.

## Transport rules

- HTTPS/TLS only. There is no plaintext fallback for the control API.
- The Windows machine is expected to sit behind a VPN or a private tunnel
  such as Tailscale or WireGuard. No control port is published to the public
  internet.
- `remote/server.py` binds no socket. Choosing the listening interface is an
  operator decision, and the handler rejects any request that did not arrive
  over an allowed address. The default allowlist is loopback only.
- Every request carries a HMAC-SHA256 signature. The shared secret never
  travels over the wire and never appears in a log, a source file or SQLite.

## Request headers

| Header | Meaning |
| --- | --- |
| `X-Jarvis-Key-Id` | Identifies the paired device. The current client sends `jarvis-blue-mobile-v1`. |
| `X-Jarvis-Timestamp` | Unix epoch milliseconds. |
| `X-Jarvis-Nonce` | A unique value for this request. |
| `X-Jarvis-Signature` | Lowercase hex HMAC-SHA256, see below. |

Header names are matched case insensitively.

## Canonical signature

The signed string is five fields joined with a newline. The field order is
part of the protocol:

```
METHOD_UPPERCASE \n PATH \n TIMESTAMP \n NONCE \n SHA256_HEX(BODY)
```

The signature is `HMAC-SHA256(secret, canonical)` in lowercase hex.

```python
canonical = '\n'.join([
    method.upper(), path, timestamp, nonce, hashlib.sha256(body.encode('utf-8')).hexdigest(),
])
signature = hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
```

Shared test vectors, asserted by `tests/test_bridge_protocol.py` here and by
`BridgeSignatureTest.kt` on the phone:

```
sha256("") = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
sign("GET", "/api/status", "1700000000000", "", "test-secret", "nonce-123")
         = 5a0eff83c8875fc160be921c708461920dfa3f9775821784555822eb38d32a3d
```

Because the body digest is part of the canonical string, a captured signature
cannot be moved onto a different payload.

## Replay protection

Three independent checks must all pass before a request is served:

1. the timestamp must be within 300 seconds of the server clock;
2. the nonce must not have been seen before, and nonces are remembered for 900
   seconds, which is longer than the clock window;
3. the signature must match exactly, compared in constant time.

A request that fails any check is answered with the same generic message, so a
caller cannot learn whether a key id exists.

## Pairing and revocation

A device is paired explicitly with a key id and a shared secret of at least 32
characters. The secret is generated on the desktop and handed to the phone out
of band. `PairingStore` keeps the record; the secret itself belongs in the
Windows credential vault (`security.vault.Vault`), never in the repository.

Revoking a key id removes the secret immediately, so the next request from that
device is rejected. Revocation is not a soft flag that a request can race.

The Windows desktop now saves only device IDs, labels, last-seen timestamps and
revocation flags in its existing local SQLite configuration. Pairing secrets
remain exclusively in the Windows Credential Manager. A saved metadata record
without its vault key cannot authenticate. Restarting the desktop preserves
pairing and revocation, but does not enable the listener automatically. Device
metadata in SQLite is private user data and is not encrypted by the bridge.

## Endpoints

| Method | Path | Answer |
| --- | --- | --- |
| `GET` | `/api/status` | PC status object |
| `GET` | `/api/jobs` | `{"jobs": [...]}` |
| `GET` | `/api/jobs/<id>` | one job record |
| `POST` | `/api/jobs` | one job record |
| `POST` | `/api/jobs/<id>/cancel` | `{"ok": true\|false}` |
| `POST` | `/api/chat` | the answer of the desktop |
| `GET` | `/api/memory` | `{"memory": [...]}` |
| `POST` | `/api/memory` | one memory entry |
| `GET` | `/api/notifications` | `{"notifications": [...]}` |
| `POST` | `/api/notifications/<id>/ack` | `{"ok": true\|false}` |

The Android client uses the first four. The iPhone PWA uses all of them.

The status object is snake case: `peer_id`, `state`, `hostname`, `platform`,
`agent_version`, `heartbeat`, `queued_jobs`, `running_jobs`, `cpu_percent`,
`memory_percent`, `gpu_percent`, `disk_free_gb`, `detail`. `state` is one of
`unknown`, `online`, `offline`, `degraded`, `pairing_required`.

A job record is snake case too: `id`, `kind`, `title`, `state`, `progress`,
`created_at`, `updated_at`, `logs`, `outputs`, `error`, `requires_approval`.
`kind` and `state` are upper case. The kinds are `PYTHON_PROJECT`,
`AFTER_EFFECTS_RENDER`, `CODE_REVIEW`, `DOCUMENT_ACCESS`, `WORKFLOW`, `CUSTOM`.
The states are `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`,
`REJECTED`.

A submitted job is never executed by the bridge. It is recorded as `QUEUED`,
and when the request asked for approval it stays `QUEUED` until the owner
approves it in the desktop interface. That keeps the existing one-use,
per-action confirmation boundary in force for remote requests as well.

## Chat

`POST /api/chat` is answered by the desktop, not by the bridge. The request
body is:

```json
{"message": "what is running?", "consent": false}
```

The answer is:

```json
{"text": "...", "provider": "ollama", "model": "llama3", "duration_ms": 812, "local": true}
```

The rules:

- the owner chooses a provider for the bridge in the Mobile Bridge page, and
  the choice is remembered;
- a **local** provider answers without a key and without any consent, because
  it never leaves the computer;
- a **paid** provider needs the permission of the owner *and* the `consent`
  flag in the request, so a phone cannot spend money by accident;
- the provider key is read from the Windows vault on the PC and never travels
  to the phone;
- the emergency stop of the desktop stops the bridge as well.

The desktop keeps the last few turns so an answer can refer to them.

## Memory and notifications

`GET` and `POST /api/memory` carry the memory that the owner allowed to be
synchronised. An entry is `{"id", "text", "source", "created_at"}`. The store
is bounded, it is not written to disk by the bridge, and a desktop that has
not allowed memory synchronisation refuses **both read and write** requests
with `403`. A missing or failing permission checker also denies access; pairing
alone does not grant permission to read memories.

`GET /api/notifications` returns the notifications that were not acknowledged
yet, and `POST /api/notifications/<id>/ack` marks one as seen. A notification
is `{"id", "title", "body", "level", "created_at", "acknowledged"}`.

## The audit log

Every request is recorded: the key id, the method, the path, the result and a
short digest of the body. The body itself is never recorded, because a chat
message and a memory entry are private content. The log is in memory and
bounded.

## The iPhone pairing code

The desktop can show a pairing code that the iPhone scans:

```
JARVIS-BRIDGE-v1
bridge=https://pc.example.lan:8765
key=jarvis-iphone-v1
secret=<the one time secret>
expires=1764000000
```

The code expires, the secret is shown once, and the phone holds it in memory
only. The iPhone has its own key id, so revoking the Android phone does not
revoke the iPhone.

## Status

Implemented and unit tested on the desktop side: the signing scheme, replay
protection, pairing and revocation, the ten endpoints and the job state
machine. The iPhone PWA signs the same way, and the pinned vector in
`tests/test_bridge_protocol.py` is repeated in `iphone-pwa/tests/bridge.test.mjs`
so the two halves cannot drift apart.

Not implemented and therefore not available to a user today: a tunnel, a
public HTTPS address for the bridge, and the execution of the queued jobs.
A phone still needs the owner to pair it and to reach the PC over a private
network.
