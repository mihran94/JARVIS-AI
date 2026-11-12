# JARVIS iPhone PWA (early prototype)

This is a static installable Safari web app with a status/jobs **read-only** UI. It signs requests using the existing remote/protocol.py HMAC-SHA256 canonical scheme. No provider API keys or pairing secrets are included. No QR pairing, chat, push notifications, file transfer or task submission yet.

## Run / deployment

Serve the contents of this directory from a trusted HTTPS origin with an approved, authenticated **same-origin** /api reverse proxy to the Windows bridge. Do **not** expose the Windows bridge to the public Internet. A private VPN with a trusted HTTPS hostname and TLS termination is recommended. The Windows listener currently binds loopback and only permits approved peer addresses. A deployment-specific proxy and owner-approved pairing are prerequisites; they are NOT provisioned by this prototype.

The app allows entering a bridge base URL, but cross-origin requests will fail until the bridge/proxy has an appropriately restricted CORS preflight policy. Prefer same-origin routing. Never use permissive wildcard CORS for authenticated control endpoints.

On Windows, pair the iPhone as a distinct key ID using the desktop Mobile Bridge page. Transfer the one-time secret privately; paste it into the PWA. It stays in JavaScript memory and disappears on reload. Do not put secrets in URL query strings or localStorage.

Open the HTTPS PWA URL in Safari on iPhone, choose Share → Add to Home Screen. Service worker caches the shell only, not API responses or credentials.

## Limitations

This is a source-code prototype, **not** a deployed or verified iPhone-to-PC connection. HTTPS certificates, VPN/proxy, Windows bridge, per-device pairing and real device testing are required. Existing bridge only queues jobs for desktop owner approval. No direct phone/PC execution is performed by the PWA.
