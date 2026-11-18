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
a second menu or dashboard.

## The key that brings JARVIS up

The owner can give JARVIS one key that works in **every** application, not
only while the JARVIS window has the focus.

* Open **Settings**, find **Key that brings JARVIS up**, and write the
  shortcut, for example `Ctrl+Alt+Space`. Press **Apply**.
* The line under it says what happened. If another program already holds
  the key, that is said plainly, and the old key is kept.
* The key brings JARVIS to the front. It does **not** open the microphone.
  The microphone only ever follows the consent the owner gave inside the
  application.

What the shortcut may be:

* A key with at least one modifier, such as `Ctrl`, `Alt`, `Shift` or
  `Win`. A bare letter would be taken while the owner types. The function
  keys, `F1` to `F24`, are allowed on their own.
* One key only. `Ctrl+Shift+Alt+J` is a shortcut; `Ctrl+J+K` is not.
* Nothing that Windows keeps for itself. `Ctrl+Alt+Del`, `Alt+Tab`,
  `Ctrl+Esc`, `Alt+F4`, `Win+L` and `F12` are refused with a reason.
* Keys that other applications usually take, such as `Ctrl+T`, are
  allowed, and the owner is warned that the key may reach that
  application instead.

On Windows the key is registered with the operating system through
`RegisterHotKey`. On Linux and macOS the operating system cannot be asked
for a key from here without extra native libraries, so the shortcut is
still saved and still shown, and the application says that it does
nothing on that system. It never claims the key works when it does not.

## Files & Folders

Choose **Attach** beside the chat input (or type `/files`, `/folders`,
`/upload` or `/attach`). Select individual files or a folder under two
separate sections and preview a local text snapshot. Checking **Include
selected file text in my NEXT AI message** permits a single cloud-provider
request after the owner explicitly presses **Ask JARVIS**. The content is
cleared from the selection on submission, never stored in conversation
history or automatically uploaded. Folder selection is bounded and excludes
hidden/secret files and symlinks. Only text/code/CSV/JSON and small DOCX
formats are supported; PDF and binary attachments remain unsupported. The legacy `Ctrl+D` dock shortcut and Stealth
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
