# JARVIS iPhone PWA

An installable web app for the iPhone that talks to the JARVIS desktop over
the signed bridge protocol. It is a companion: the PC keeps the keys, the
PC keeps the approval, and the phone asks.

## What it does

| | |
| --- | --- |
| Pairing | Scan the pairing code the desktop shows, or paste it |
| Status | Live state of the PC, with the CPU, memory and disk numbers |
| Chat | Send a message, get the answer from the PC's provider, in Tamil or English |
| Voice | Listen with the microphone, hear the answers |
| Tasks | Send a task for the owner to approve, watch it, cancel it |
| Memory | Read and write the memory the desktop allows to be synchronised |
| Notifications | See what the desktop has waiting, mark it as seen |
| Offline | The shell is cached, so the page opens without a network |

The page never holds a provider key. It signs every request with the shared
scheme in `remote/protocol.py` on the desktop and
`core/windows/BridgeClient.kt` on the Android client, and the pinned vector
is checked from both sides.

## Before serving it

The icons are pictures, and the repository carries text files only, so each
picture travels as a base64 sidecar. Write the pictures again with:

```
python iphone-pwa/icons/restore-icons.py
```

The manifest and the apple touch icon point at those pictures, so this step
is needed once after a fresh checkout.

## Running it

Serve this directory from a trusted HTTPS origin that has an approved,
authenticated, **same-origin** `/api` reverse proxy to the Windows bridge.
The Windows bridge itself binds the loopback interface and only accepts
approved peer addresses.

**Do not expose the Windows bridge to the public internet.** A private VPN
with a trusted HTTPS hostname and TLS termination is the expected
arrangement.

The app allows a bridge URL to be entered, but a cross-origin request fails
unless the proxy has a CORS policy that is restricted on purpose. Prefer
same-origin routing. Never use a permissive wildcard CORS for an
authenticated control endpoint.

On Windows:

1. open the **Phone Remote** page,
2. press **Pair this iPhone**,
3. fill in the address the phone reaches the PC on, for example
   `https://pc.example.lan:8765`,
4. press **Show the pairing code** and scan it with the phone, or copy the
   text into the page.

On the iPhone: open the HTTPS address in Safari, choose **Share → Add to Home
Screen**. The app is then installed and opens without a browser bar.

## The limits of iOS Safari

These are real limits, not missing work:

- an installed web app **cannot run in the background**; nothing happens
  while it is closed;
- **voice recognition has to be started by a tap**, and it only works while
  the page is in front;
- **notifications need the permission of the person**, and iOS only shows
  them for an app that was added to the Home Screen;
- the app **cannot control the phone**. It cannot read the camera, open other
  apps or change any setting;
- the camera is used **only** to read a QR code from a picture the person
  chose. The picture is decoded in the page and is never uploaded.

The Android client is the one that can act on the phone. This page is the
companion.

## Privacy

- The pairing secret is held in the memory of the page. It is never written
  to storage, never put in a URL and never logged.
- The service worker caches the shell only. No API answer, no chat message
  and no secret is ever cached.
- The page sends `credentials: 'omit'` and refuses to follow a redirect, so a
  redirect cannot move a signed request somewhere else.

## Layout

```
index.html            the page
style.css             the look, light and dark
app.js                the wiring
sw.js                 the offline shell
manifest.webmanifest  the install information
js/bridge.js          the signed client
js/pairing.js         reading the pairing code
js/chat.js            the transcript
js/offline.js         the outbox for a phone that is out of reach
js/qr.js              reading a QR code from a picture
js/speech.js          Tamil and English voice
tests/                the node test suite
tools/decode-matrix.mjs  reads a QR code that was drawn elsewhere
icons/                the icons and the script that writes them
vendor/               the vendored QR decoder
```

## Tests

```
npm test
```

or, from the repository root, `python -m pytest tests/test_pwa_javascript.py`,
which starts the same suite. The GitHub Actions recipe runs pytest, so the
JavaScript is covered there as well.

The suite checks the signing against the vector that is pinned in the
desktop test suite, the pairing code, the outbox, the transcript, the voice
rules and the QR reader.

## What is not claimed

This is a working client, not a deployed one. It has not been used on a
physical iPhone, and the bridge has not been reached over a real VPN. The
pairing, the TLS termination and the tunnel are the owner's part.
