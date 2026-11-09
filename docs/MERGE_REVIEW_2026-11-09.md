# Development merge review — 9 November 2026

Reviewed repository: mihran94/JARVIS-AI.
Base main: ddecf446a7b7e8a0c9883513082d50b3a6cb33b4.
Development head before corrections: ff58beb107c820b752cb892d1353a9639b2d138f.
Branch: dev/opt-in-stream-fallback-20261109, three commits ahead and none behind.
No open pull requests existed at review start.

## Scope and findings
The branch adds an opt-in streaming fallback helper and offline tests. It is not connected to the desktop chat flow. Backup requests require explicit boolean consent, occur only before output has been emitted, and are attempted at most once.

Review found a pre-existing literal backslash-n outside a string in desktop/app.py that prevented the desktop module from importing. Corrected it to a real source newline.

StreamTarget's generated repr exposed its key field. Marked that field repr=False.
The adapter now checks cancellation before invoking the primary stream and propagates Stopped directly even when RuntimeError is configured as retryable.

Additional regression tests cover hidden credential repr, cancelled preflight, direct cancellation, partial-output blocking, callback errors, non-boolean consent and overly broad retry policies.

## Executed validation
Reconstructed the exact development source in a separate review directory, preserving the newer repository implementation instead of overwriting it with the older local prototype.

Before correction: pytest failed during collection due to the desktop SyntaxError.
After correction:
    QT_QPA_PLATFORM=offscreen python -m pytest -q
    83 passed in 1.07s

python -m compileall -q . completed successfully.
The suite includes Qt desktop tests and synthetic HTTP transport tests. No real API keys or paid provider calls were used.

Windows-native behavior, real provider availability and packaged EXE remain unverified. The helper does not classify provider HTTP errors itself; callers must choose a retry policy. Existing desktop behavior remains manual provider selection with no automatic cross-provider fallback.

GitHub Actions was previously blocked by account billing/spending settings. This review uses local verification; commits use skip-ci to avoid starting those hosted jobs. No account settings, repository visibility or permission controls were changed.
