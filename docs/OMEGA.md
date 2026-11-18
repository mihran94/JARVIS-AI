# JARVIS PRIME desktop and Island

The current Windows product has **one production interface**: JARVIS PRIME,
with command-first chat, Settings and the optional floating Island. The old
Omega Home dashboard, duplicate Omega Settings, animated startup design, and
expandable application dock are retired from user navigation.

## Use

1. Install the checked-out version using `setup.cmd`.
2. Launch with `START_JARVIS.cmd`.
3. Ask JARVIS in Tamil, Tanglish or English, or type `/help` for supported
   project, coding, memory and device commands.
4. Open **Settings** for themes, API credentials, permissions, projects and
   voice. Open **Island** to use the floating assistant. Use **Emergency Stop**
   to interrupt work.

Advanced tools remain available through existing commands; they do not need
a second menu or dashboard. The legacy `Ctrl+D` dock shortcut and Stealth
presentation are intentionally not available. Saved legacy mode preferences
cannot reactivate them. The older `Omega Home` and `Omega Settings` routes
resolve to PRIME Chat and Settings respectively.

Some historical widget internals are retained in `desktop/omega.py` for the
working floating assistant, visual state, and compatibility smoke tests. That
does **not** create another user-facing design or another application.

## Verification

On Windows:

```powershell
.venv\Scripts\python.exe main.py --smoke-test
.venv\Scripts\python.exe -m pytest -q tests/test_omega.py tests/test_prime_theme.py tests/test_command_first_window.py
```

Validate the real PC at normal/125%/150%/200% display scaling and verify
that chat, Island, Settings, permission prompts, and Emergency Stop work.
A headless smoke test alone does not validate real microphone, phone pairing,
Tamil voice quality or signed installers.

The old `desktop/personal_theme.py` and `desktop/blue_theme.py` stylesheets
and the outdated `scripts/port_chat_first_omega.py` migration were deleted.
Runtime worker `desktop/background.py`, the Android remote, local memory,
provider configurations and project/source history were not removed.
