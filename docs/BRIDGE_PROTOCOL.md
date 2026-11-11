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

## Endpoints

| Method | Path | Answer |
| --- | --- | --- |
| `GET` | `/api/status` | PC status object |
| `GET` | `/api/jobs` | `{"jobs": [...]}` |
| `POST` | `/api/jobs` | one job record |
| `POST` | `/api/jobs/<id>/cancel` | `{"ok": true\|false}` |

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

## Status

Implemented and unit tested on the desktop side: the signing scheme, replay
protection, pairing and revocation, the four endpoints and the job state
machine. 33 bridge tests pass locally.

Not implemented and therefore not available to a user today: a bound listener,
TLS configuration, a tunnel, desktop UI wiring, and job execution. A phone
cannot reach a JARVIS installation with this code as it stands.
