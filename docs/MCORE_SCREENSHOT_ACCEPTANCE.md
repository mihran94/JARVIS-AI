# JARVIS M-CORE visual acceptance

This checklist is for the native JARVIS desktop app, not a browser prototype.
Compare with the owner's reference at approximately 1227 × 912 and at a
smaller desktop size. Use a separate source checkout and a disposable profile.

## Layout

- Header: JARVIS M identity and Settings on the left; live state in the
  center; local time, weekday, date, year, and Fullscreen on the right.
- Left: Systems meters, Status, and Tasks/Routines. Measurements must be
  live or explicitly unavailable. Never display sample measurements as live.
- Center: large Voice Interface with the JARVIS orb, actual voice status
  and mic level; News below. News stays empty until fetched on request.
- Right: Communications over Command, with long Tamil replies still
  readable. Command exposes the same attachment staging and sharing review
  as regular Chat, text input, mic control and Interrupt.
- Footer: engine/mic/protocol on the left; F4 Mute, F11 Fullscreen, Esc
  Interrupt and JARVIS M on the right. Provider labels distinguish a
  selected route from an active live session. For narrower windows, check
  that panels can be reached and text does not overlap the controls.

## Boundary checks

- Open the conventional Settings and task review using their visible links.
  A typed action requiring approval must still surface a real approval card.
- Drop a synthetic local file and a folder separately; neither action
  grants provider sharing, sends a command or opens the item automatically.
- F4 changes actual mic mute state without granting consent or starting a
  fresh listen. F11 uses the existing fullscreen route. Esc and Interrupt
  stop an active reply, not a pending PC approval or a desktop task.
  Emergency Stop remains separate. No microphone or cloud session is needed
  for automated tests of these controls.
- In a separate, explicitly approved live turn, verify the physical speaker
  and microphone, actual state transitions, and that stopping playback
  does not resume a muted or stopped microphone. A hosted test cannot
  replace that observation.

Run source checks in CMD: `VERIFY_JARVIS.cmd --phase1`. Use the dedicated
M-CORE tests for layout/interaction regressions. Launch the review source
with the existing interpreter and `scripts\launch.py --dev-data`; do not
change the normal installation or use a packaging workflow.
