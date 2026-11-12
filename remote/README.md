# remote — versioned desktop/mobile bridge

This package implements the desktop half of the JARVIS mobile bridge. The phone
half lives in `mihran94/jarvis-blue-android`
(`core/windows/BridgeClient.kt` and `core/model/WindowsBridge.kt`).

Implemented:

- `protocol.py` — the canonical signing scheme, shared by both halves.
- `replay.py` — the nonce registry that makes a signed request single use.
- `pairing.py` — the paired device registry with explicit revocation.
- `secrets.py` — the Windows credential vault adapter for bridge secrets.
- `jobs.py` — the job records the phone can read.
- `server.py` — the four bridge endpoints.
- `listener.py` — the listener. It refuses to start without TLS, refuses a
  non loopback address, and authenticates every request.
- `loopback.py` — the loopback check shared with the local model.

The desktop side of this is the **Mobile Bridge** page: start and stop the
listener, pair a phone, revoke a phone, and approve or reject the jobs a
phone sends.

Not implemented and therefore not claimed:

- The listener is reached over a private network or a private tunnel. It is
  never published to the public internet, and the owner must confirm a
  non loopback address explicitly.
- The bridge never executes a job. A job waits as QUEUED until the owner
  approves it in the desktop interface.
- No Windows service, no auto start and no background daemon.

See `../docs/BRIDGE_PROTOCOL.md` for the protocol and `../docs/ARCHITECTURE.md`
for the permission boundaries.
