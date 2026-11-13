# JARVIS BLUE Windows Bridge

Reference desktop-side service for the JARVIS BLUE MOBILE remote command centre.

## Quick start

```powershell
cd windows-bridge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Generate a shared secret (one-time)
python -m jarvis_bridge.server --generate-secret

# Start the bridge (keep it bound to localhost)
$env:JARVIS_BRIDGE_SECRET = "<paste the secret>"
python -m jarvis_bridge.server --host 127.0.0.1 --port 8765
```

## Reach it from the phone

Do **not** open port 8765 on your router. Use one of:

| Method | What to enter as the host in the app |
|---|---|
| Tailscale (recommended) | the MagicDNS name, e.g. `desktop.tailnet-name.ts.net` |
| WireGuard | the tunnel IP, e.g. `10.8.0.2` |
| SSH tunnel | `127.0.0.1` with a local port forward |

With Tailscale the app connects over `https://` (or `http://` if you terminate
TLS inside the tunnel) to the host above.

## Pairing

1. On the Windows machine: `python -m jarvis_bridge.server --generate-secret`
2. In the app: **Settings → Windows Connection → Pair**, paste the secret.
   The secret is stored encrypted with the Android Keystore master key.
3. The app signs every request with `HMAC-SHA256` over
   `method\npath\ntimestamp\nnonce\nsha256(body)` and the bridge rejects
   anything that does not verify, including replayed nonces.

## Wiring real work

Replace `JobQueue._run_job` in `jarvis_bridge/server.py` with your actual
workload — for example:

* After Effects render submission via `aerender`/`ffmpeg`,
* a Python project runner,
* a code-review job that calls your local model.

Everything else (queueing, approval, cancellation, progress, logs, outputs and
the event stream) is already wired up.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | unauthenticated liveness probe |
| GET | `/api/status` | heartbeat + CPU/RAM/GPU/disk + job counts |
| GET | `/api/jobs` | list jobs |
| POST | `/api/jobs` | submit a job |
| POST | `/api/jobs/{id}/cancel` | cancel a job |
| WS | `/ws` | live job events |
