# Verification report — 8 November 2026

## Executed here

Environment: Linux, Python 3.12 virtual environment. Direct dependencies: PySide6 6.8.3, httpx 0.28.1, keyring 25.6.0, pytest 8.3.5.

Command: QT_QPA_PLATFORM=offscreen python -m pytest -q

Actual final output:

    .......................................                                  [100%]
    39 passed in 0.36s

Python compilation: python -m compileall -q . completed with exit code 0.

Coverage of executed checks:
- Approval denied, bound to exact immutable action, one-use, and invalidated by stop/resume.
- Stop during confirmation and cancellation before any request.
- Gateway records denied, successful and failed tasks.
- SQLite history/config persistence, Tamil text, conversation deletion and crash recovery.
- Twelve unsafe filename patterns blocked; symlink escape blocked.
- Atomic workspace replacement retains prior contents; Python syntax is parsed without execution.
- Request URL/auth/body contract for all three providers with httpx.MockTransport.
- Sanitized HTTP 301/401/403/429/500 errors; no redirect following.
- Invalid JSON, streamed errors, truncated output, length-limited completion and empty stream failure.
- Unknown app rejected and credential storage fails closed outside Windows.
- Real Qt navigation across all seven pages, editor save, stop and resume.
- Real Qt chat worker + synthetic streaming HTTP response reaches UI and persistent history.
- Late output/result ignored after emergency stop and resume.

Actual desktop render captured to docs/desktop-preview.png and visually inspected. Native Linux offscreen Qt reports the benign message "This plugin does not support propagateSizeHints()".

## Not executed / not claimed

- Live OpenAI, MiniMax or Gemini requests: owner will add credentials later.
- Windows Credential Manager persistence and removal.
- Windows Notepad/Calculator launch.
- Windows 10/11 rendering, DPI, keyboard shortcut and clean-machine installer.
- PyInstaller build/signing.
- Voice, remote access, agent planning and other roadmap modules: not implemented.

Synthetic transport tests validate this code's protocol behavior, not the providers' live accounts, model availability or service behavior. Passing these tests does not certify enterprise security or Windows compatibility. Complete WINDOWS_ACCEPTANCE.md before treating the Windows build as validated.
