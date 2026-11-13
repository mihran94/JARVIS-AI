# JARVIS BLUE MOBILE — User Guide

A practical tour of every screen.

---

## The command centre

The bottom bar has five destinations: **Assistant**, **Chat**, **Studio**,
**Control** and **Settings**. The blue-and-black theme is the default; a light
theme is available in Settings.

---

## Assistant

The home screen. A slowly pulsing orb, a live voice waveform, a language
selector and the microphone button.

* **Language chips** — தமிழ் / English / Français. The chip you pick is the
  language used for recognition *and* for the spoken reply.
* **Talk / Allow microphone / Stop** — the button reflects the state:
  it asks for the microphone permission the first time, then starts a
  one-shot recognition, then stops.
* **On-device ASR / Cloud ASR badge** — shows which recogniser Android
  actually gave us. If the badge says *Cloud ASR*, the audio went to the
  network; the app never hides that.
* **Voice pack badge** — shows whether the selected language has a TTS voice
  installed.
* **Wake word switch** — arms "Hey Jarvis Blue".

> On Android 14+ the wake-word service can only be started while the app is
> visible. Android shows a permanent microphone indicator and a notification
> for as long as it runs. That is the platform's privacy guarantee and the app
> does not attempt to work around it.

---

## Chat

The full AI conversation with a live tool-call trace.

* **Provider chips** — pick a specific provider for this conversation, or leave
  it on *Auto* and let the router choose by priority, health and task.
* **Model chip** — the model that actually answered.
* **Tool bubbles** — under each assistant reply you see every tool that was
  requested, its risk level and the real result. A refused call says so.
* **Confirmation dialog** — when a tool needs approval the dialog states the
  tool, what it does, which permissions it will use and whether it may remove
  data. *Approve once* runs it one time; *Decline* reports the refusal to the
  model, which then tells you it did not run.

---

## Studio

Three laboratories.

### Dev

A code editor over a sample snippet, with ten languages. Five actions:

| Button | Needs the network? | What it does |
|--------|--------------------|--------------|
| **Explain** | yes | Explains the code in the selected output language |
| **Review** | yes | Correctness first, then security, then maintainability |
| **Tests** | yes | Writes a focused test file |
| **Quality check** | no | On-device structural checks: unbalanced brackets, `!!`, broad catches, long lines, TODO markers |
| **Security scan** | no | On-device defensive analysis: cleartext HTTP, disabled TLS validation, hard-coded secrets, exported components, world-readable files, backup flags — each with a remediation and an OWASP/CWE reference |

> Generated code is **never executed** on the device. Local checks are static
> only. Anything that needs a real toolchain is delegated to your Windows
> machine.

### Cyber

Defensive work only, and it will not touch anything until you record an
authorisation.

1. Choose the authorisation kind (owned network / written permission / lab
   exercise / self device) and type the scope.
2. **Record authorisation**.
3. Enter a host and port → **Inspect host**: DNS resolution, TCP connect time,
   TLS version, cipher, subject, issuer, expiry, chain length and whether the
   device trust store accepts the chain.
4. Paste source or manifest text → **Review** for OWASP-mapped findings.

There is no exploit generator, no credential tester and no persistence module.

### Quantum

A labelled research module. Build a circuit from H/X/Y/Z/S/T/RX/RY/RZ/CNOT/CZ/
SWAP gates, pick the preset circuits (Bell pair, GHZ-3, 2-qubit QFT), and
simulate.

> The banner is not decoration: **a phone has no quantum processor.** Every
> number you see comes from a classical state-vector simulation running on the
> CPU. The report shows the simulator time next to a classical baseline so the
> cost is obvious, and no quantum speed-up is claimed.

---

## Control

Four tabs.

### Permissions

* **Emergency stop** — engages a global block on every tool, service and remote
  command. It is sticky: it survives restarts and reboots until you release
  it.
* **App lock** — require an unlock on launch, require biometrics for sensitive
  tools, set the session timeout.
* **Capabilities** — 18 switches, each one independent. Sensitive ones are
  marked. You must also grant the matching Android permission.
* **Tools** — a switch per tool. Switching off *Summarise notifications* does
  not revoke your other capabilities.
* **Revoke every in-app grant** — one tap to return to a fully locked state.

### Tasks

Type a command in plain language:

* "organize my downloaded PDF files"
* "open my development project"
* "explain this code in Tamil"
* "remind me about tomorrow's appointment"
* "check the progress of my Windows render job"
* "inspect this application for security issues"

The rule engine shows you **which rule matched and with what confidence**
before anything is queued. Tasks run through the same permission and risk gate
as a chat request — queuing one does not grant it anything.

### Memory

Your durable notes. Stored in the encrypted database. Add one, or let the
assistant store one for you ("remember that I prefer Tamil for explanations").

**Delete all memories** wipes them immediately.

### Windows

* **Not paired** — host, port and the shared secret from
  `python -m jarvis_bridge.server --generate-secret`.
* **Paired** — live status (online/offline, CPU, RAM, disk free, running and
  queued jobs), a job submission form, and a job list with progress and a log
  preview. Jobs can be cancelled.
* **Unpair** deletes the pairing secret from the vault.

---

## Settings

* **AI providers** — enable, base URL, model id, API key, and **Health check**
  per provider. The key field shows a masked value once saved.
* **Appearance & security** — dark theme, app lock, biometrics, session
  timeout, and whether the Keystore key is **hardware backed**.
* **Your data** — delete all memories, clear the audit log.
* **Audit trail** — the recent event log.
* **Build** — version, min/target SDK.

---

## The emergency stop

Reachable from **Control → Permissions** and shown as a red banner over every
screen while it is engaged. It blocks:

* every tool call (with an `EMERGENCY_STOP` verdict),
* the in-flight confirmation prompt,
* remote commands to the Windows machine.

It does **not** stop the microphone foreground service on its own — stop that
from the notification shade as well if that is what you want.

---

## What the assistant will never do

* It will never claim an action succeeded before the app has verified it.
* It will never send a message, delete a file, spend money or publish anything
  without a fresh confirmation.
* It will never read a notification, a file or the screen without the matching
  grant.
* It will never run arbitrary code from the model on your device.
* It will never hide that a recogniser went to the cloud.
