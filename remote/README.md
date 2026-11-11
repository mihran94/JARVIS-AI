# remote — versioned desktop/mobile bridge

This package implements the desktop half of the JARVIS mobile bridge. The phone
half lives in `mihran94/jarvis-blue-android`
(`core/windows/BridgeClient.kt` and `core/model/WindowsBridge.kt`).

What exists today:

- `remote/protocol.py` — the canonical signing scheme, shared by both halves.
- `remote/replay.py` — the nonce registry that makes a signed request single use.
- `remote/pairing.py` — the paired device registry with explicit revocation.
- `remote/jobs.py` — the job records the phone can read.
- `remote/server.py` — the request handler for the four bridge endpoints.

What does **not** exist yet, and is therefore not claimed:

- No socket is bound. Nothing in this package opens a port.
- The desktop UI does not expose the bridge, so a phone cannot use it today.
- No TLS listener, no tunnel configuration and no background service.
- No execution of a submitted job. A submitted job is recorded as `QUEUED` and
  waits for the owner's approval in the existing Qt interface.

See `../docs/BRIDGE_PROTOCOL.md` for the protocol and `../docs/ARCHITECTURE.md`
for the permission boundaries.
