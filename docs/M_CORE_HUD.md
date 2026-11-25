# M-CORE HUD: Windows CMD acceptance

M-CORE is the native desktop presentation of the existing JARVIS app. It does
not run the HTML mock-up, start a second server, or store credentials in a browser.
Chat, work tools, projects, Island, microphone and Emergency Stop still use
the existing application and approval policy.

## Verify from source

From CMD in a separate checkout of the review branch, using the existing
Python 3.12 x64 development environment:

```bat
git rev-parse --short HEAD
VERIFY_JARVIS.cmd --phase1
START_JARVIS.cmd --dev-data
```

The first command identifies the revision. The second checks the runtime,
starts a disposable offscreen session, then runs the HUD, Settings, keyboard
navigation, narrow-layout and approval source tests. This includes mocked
voice playback and checks that the microphone doesn't rearm during playback.
A missing pytest or a failing check gives a nonzero exit. Do not count a skipped or failed suite as
a pass. The last command opens an interactive development profile; do the
following live checks separately and note pass, fail, or not run for each.

If this checkout does not have its own `.venv`, `setup.cmd` is the existing
dependency setup. Run it only if you intend to install dependencies in the
checkout. Do not copy provider keys into the HUD or share keys in test evidence.

1. Check the centered M-CORE orb and the compact indicator that replaces it
   after the first message. Resize the window and check readability, including
   Windows display scaling and Tamil text such as `வணக்கம் ஜார்விஸ்`. Note the
   display scaling used; check that Settings and Emergency Stop remain usable.
2. Type `Hey Jarvis`. The indicator pulses unless reduced motion is enabled.
   This is a local summon, not a speech recognition or model request.
3. Confirm that the microphone reads **off** before consent. Clicking **Mic:
   off** opens Voice settings without enabling capture. After explicit consent,
   the HUD reads **ready**, not **listening**. Use Speak, or run the mic test
   from **Settings → Advanced settings → Chat options, audio tests and
   connections**. Then turn off access from the HUD. Muting spoken replies is
   separate. Gemini Live requires its separate cloud-audio confirmation.
4. In Chat, type `Open Calculator and calculate: 17 * 23`. In the default
   approval mode, decline once and check that nothing opened. Submit again,
   approve, and confirm the actual Calculator display shows 391. If readback
   cannot be verified, do not treat dispatch as success.
5. Queue the same request and use **Emergency stop** before approving.
   Check the stopped status and confirm that Resume does not retry the action.
6. Open **Island** and **Work**. Verify you can return to the same conversation,
   and that tools open existing JARVIS controls, not simulated tasks.
7. Open **Settings** and check that approvals, language, tone and theme are
   visible without opening Advanced. Open **Advanced settings** and switch
   categories with the keyboard. Check that the **Projects** rail and **Work →
   Plugin settings** still reveal their original controls. Reopen **Settings**
   and verify it returns to the short essentials view.

Local models, cloud providers, remote pairing, wake-word recognition, devices
and external applications are not certified by a visual or offscreen smoke
test. No EXE, installer, or APK is needed for this checklist.
