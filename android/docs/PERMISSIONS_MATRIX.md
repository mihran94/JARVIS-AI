# JARVIS BLUE MOBILE — Permissions Matrix

Two independent layers protect every capability. **Both** must be satisfied.

* **Layer 1 — Android runtime permission.** Granted by the user in the system
  dialog. Can only be granted by the user; the app never auto-grants.
* **Layer 2 — In-app capability grant.** Granted in *Permissions* inside the
  app. Defaults to **denied**. Revocable at any time, per capability and per tool.

If the app-level grant is present but the runtime permission is missing, the
tool fails with a `DENIED_PERMISSION` verdict and the model is told the truth.

---

## 1. Capability buckets

| Bucket | Label | Sensitive | Android runtime permission | In-app grant | Revocable |
|--------|-------|-----------|---------------------------|-------------|-----------|
| `microphone` | Microphone | yes | `RECORD_AUDIO` | required | ✅ |
| `notifications.read` | Read notifications | yes | *Notification access* (Settings toggle, **not** a runtime dialog) | required | ✅ |
| `notifications.post` | Post notifications | no | `POST_NOTIFICATIONS` (Android 13+) | required | ✅ |
| `contacts` | Contacts & calls | yes | *none required* (dialler intent) | required | ✅ |
| `files` | File access | yes | *none required* (SAF tree grant) | required | ✅ + revoke tree in Settings |
| `assistant` | Assistant role | no | *none* (default-assistant selection) | required | ✅ |
| `automation` | Automation | no | *none* | required | ✅ |
| `screen_capture` | Screen capture | yes | *none* (MediaProjection consent per session) | required | ✅ |
| `accessibility` | Limited UI automation | yes | *Accessibility service* toggle | required | ✅ |
| `ai.network` | Cloud AI | no | `INTERNET` | required | ✅ |
| `remote` | Remote control | yes | `INTERNET` + VPN/tunnel | required | ✅ |
| `overlay` | Overlay | no | `SYSTEM_ALERT_WINDOW` | required | ✅ |
| `package.query` | App inventory | no | *none* (`<queries>` manifest) | required | ✅ |
| `system_settings` | Open system settings | no | *none* | required | ✅ |
| `media_control` | Media control | no | *none* | required | ✅ |
| `development` | Development tools | no | *none* | required | ✅ |
| `security_scan` | Security scanning | yes | `INTERNET` | required | ✅ |
| `memory.store` | Personal memory | no | *none* | required | ✅ |
| `background.service` | Background service | no | *none* | required | ✅ |

---

## 2. Sensitive capture consent

Some things are read by a **service**, not by a tool. A tool runs when a model
asks for it; a service runs when Android binds it. For those, the in-app
grant is checked again at the moment of the capture, so taking the grant back
stops the reading at once.

| Capture | Bucket | What is read | Without the consent |
|---|---|---|---|
| `microphone.capture` | `microphone` | The audio the recogniser listens to | The service stops and the request is refused |
| `accessibility.screen` | `accessibility` | The visible text of the current window | Nothing is read, and what was read before is dropped |
| `notifications.content` | `notifications.read` | The title and the text of a posted notification | Nothing is recorded at all, not even the package name |
| `background.service` | `background.service` | The scheduled work that runs while the app is closed | The worker returns without doing anything |

The switches live in *Permissions → Privacy* and are separate from the
capability buckets, because they answer a different question: not "may this
tool run" but "may the assistant read this".

The Android grant is never enough on its own. Granting notification access in
the system settings does not let the app keep notification text, and enabling
the accessibility service in the system settings does not let it read the
screen. Both need the in-app consent as well.

The default is **denied** for all four, on a fresh install and after
"Revoke every in-app grant".

---

## 3. Tool → capability mapping

| Tool | Capabilities | Risk | Fresh confirmation |
|------|-------------|------|--------------------|
| `open_app` | `package.query` | LOW | no |
| `list_apps` | `package.query` | NONE | no |
| `open_settings` | `system_settings` | LOW | no |
| `set_alarm` | `automation` | LOW | no |
| `call_contact` | `contacts` | MEDIUM | no (opens the dialler only) |
| `compose_message` | `contacts` | HIGH | **yes** |
| `media_control` | `media_control` | LOW | no |
| `device_diagnostics` | — | NONE | no |
| `share_text` | — | LOW | no |
| `summarize_notifications` | `notifications.read` | MEDIUM | no |
| `read_screen` | `screen_capture` | MEDIUM | no (consent is per-session at the OS level) |
| `organize_files` | `files` | MEDIUM | no (deletes nothing; `move` raises the risk automatically) |
| `list_files` | `files` | LOW | no |
| `network_probe` | `security_scan` | MEDIUM | no, but **requires a recorded authorisation grant** |
| `security_review` | `security_scan` | LOW | no |
| `code_quality_check` | `development` | NONE | no |
| `quantum_simulate` | — | NONE | no |
| `remote_status` | `remote` | NONE | no |
| `remote_jobs` | `remote` | NONE | no |
| `remote_submit_job` | `remote` | HIGH | **yes** |
| `remote_cancel_job` | `remote` | HIGH | **yes** |
| `remember` | `memory.store` | LOW | no |
| `recall` | `memory.store` | NONE | no |

Each tool can additionally be switched **off individually** in the Permissions
dashboard without revoking the whole capability bucket.

---

## 4. Android manifest permissions and why each is present

| Permission | Why | Consequence for the user |
|------------|-----|--------------------------|
| `INTERNET` | Cloud AI providers, Windows bridge, DNS/TLS probes | Network traffic to the configured providers only |
| `ACCESS_NETWORK_STATE` | Connectivity diagnostics, VPN detection | Read-only |
| `ACCESS_WIFI_STATE` | SSID reporting in diagnostics | Read-only; the SSID is not stored |
| `RECORD_AUDIO` | Speech recognition and wake-word listening | System microphone indicator is shown the whole time |
| `POST_NOTIFICATIONS` | Reminders and job alerts (Android 13+) | User can disable notifications at any time |
| `VIBRATE` | Alert haptics | — |
| `FOREGROUND_SERVICE` | Wake word + screen capture | A persistent notification is always shown |
| `FOREGROUND_SERVICE_MICROPHONE` | Microphone foreground service | Same |
| `FOREGROUND_SERVICE_DATA_SYNC` | Background job sync | Same |
| `RECEIVE_BOOT_COMPLETED` | Re-arm scheduled tasks after reboot | The microphone service is **not** restarted |
| `WAKE_LOCK` | Reminder delivery | — |
| `SCHEDULE_EXACT_ALARM` / `USE_EXACT_ALARM` | Precise reminder times | Android 13+ may require the user to allow *Alarms & reminders* |
| `USE_BIOMETRIC` | App lock and sensitive-action confirmation | — |
| `SYSTEM_ALERT_WINDOW` | Optional overlay | Not requested by default; the user must grant it in Settings |

**Not requested, by design:** `READ_SMS`, `READ_CONTACTS`, `READ_EXTERNAL_STORAGE`,
`READ_MEDIA_IMAGES`, `CAMERA`, `ACCESS_FINE_LOCATION`, `QUERY_ALL_PACKAGES`,
`MANAGE_EXTERNAL_STORAGE`, `BIND_DEVICE_ADMIN`, `REQUEST_INSTALL_PACKAGES`.

App discovery uses the `<queries>` element instead of `QUERY_ALL_PACKAGES`, so
the app can only see the app types it actually launches.

---

## 5. How each sensitive access is disclosed

| Access | Disclosure |
|--------|------------|
| Microphone | System mic indicator + ongoing notification + on-screen listening state + pause button |
| Notifications | Android's own *Notification access* screen + in-app grant + the permission dashboard |
| Files | The system document picker; the granted tree is revocable from Android settings |
| Screen | The MediaProjection system consent dialog, every time |
| Accessibility | The system accessibility settings screen with a full disclosure string, plus the system's permanent status-bar indicator |
| Biometric | The system biometric prompt |
| Remote commands | HMAC-signed requests, an explicit per-action confirmation, and an emergency stop |

---

## 6. Emergency stop

The emergency stop is a **sticky** global switch:

* every tool call is refused with `EMERGENCY_STOP`,
* the in-flight confirmation is cancelled,
* it survives app restarts and reboots,
* only the user can release it.

It is reachable from the Permissions dashboard and from the persistent banner
that overlays every screen while it is engaged.

---

## 7. Revocation checklist — "make the assistant forget everything"

1. **Permissions → Revoke every in-app grant** (one tap).
2. **Permissions → Emergency stop → Engage** (blocks everything immediately).
3. **Control → Windows → Unpair** (deletes the pairing secret).
4. **Settings → Your data → Delete all memories** and **Clear audit log**.
5. **Settings → revoke provider keys** (clears the Keystore-encrypted vault).
6. Uninstall the app — the SQLCipher key lives in the Keystore and dies with
   the app's data, so the database is unrecoverable.
7. On the desktop: stop the bridge and rotate `JARVIS_BRIDGE_SECRET`.
