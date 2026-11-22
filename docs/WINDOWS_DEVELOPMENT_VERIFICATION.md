# Windows development verification

Development baseline: integration merge commit `3ec4e29df7cffda964a9d7465691054035c387bf` (PR #67). PR #64 into main and the separate #66 shell proposal were open at audit. The development changes use the merged PRIME interface.

| Capability | Status | Evidence and remaining acceptance |
| --- | --- | --- |
| Main assistant and task surfaces | Partial | Qt regression tests cover PRIME navigation, task controls and legacy preferences. DPI, rendering and owner workflows need Windows testing. |
| Reasoning and provider routing | Partial | Fast and Deep profiles, model catalogue checks and opt-in routing using recent outcomes. Live Gemini, OpenAI and MiniMax generation and actual billing limits need acceptance. Autonomous planning remains incomplete. |
| Windows input and files | Partial | Existing bounded Notepad typing gains native readback. Plans record dispatch separately from verification. Workspace writes read back saved bytes. Real keyboard, mouse, UI accessibility and broader screen operations need Windows acceptance and development. |
| Browser and business | Partial | Main composer supplies approval-gated Edge commands in a dedicated profile. Draft readback, labelled file selection and receipt text checks are implemented. Browser process launch was blocked in this Linux workspace. Authenticated Fiverr, Canva, Flow, Higgsfield, social and Creative Studio workflows require Windows acceptance. |
| Creative | Partial | Existing editing and render adapters are retained inside the main assistant. Native application and SaaS exports require app-specific Windows acceptance. |
| Coding | Partial | Existing project selection, review, test runner and isolated changes retained. External coding provider and real VS Code acceptance pending. |
| Cybersecurity | Partial | Separate local OS diagnostics. Offensive or bypass workflows are unsupported. |
| Research | Working in regression tests | Failure stays visible and cancelled requests are checked before provider handoff. |
| Voice and memory | Partial | Existing Windows voice and local memory retained. Physical audio, device selection, multilingual speech and memory retention acceptance remain. |
| Updates and recovery | Partial | Existing review and rollback paths retained. Packaged install, restart and automatic rollback require Windows acceptance. |
| Installer | Blocked for this revision | The PR #67 baseline produced an unsigned installer and passed packaging smoke tests. A Windows build, install/uninstall acceptance and signing for this revision remain. |
| iPhone and Android | Deferred | Windows acceptance comes first. |

## Windows verification

1. Check out this development revision and run `setup.cmd`, then `START_JARVIS.cmd`. Confirm the PRIME shell opens.
2. Install or enable Microsoft Edge. In PowerShell run `$env:JARVIS_BROWSER_ACCEPTANCE = '1'` followed by ` .venv\Scripts\python.exe -m pytest -q tests/test_browser_control.py`. The test uses a controlled document rendered by the browser.
3. Follow [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md) on the target PC. Exercise browser actions through the composer's Browser button and use sandbox accounts or drafts for consequential actions.
4. Build the unsigned integration installer for the exact revision via the Windows integration workflow. Verify the installer SHA-256 from the workflow artifact, then install and uninstall in a clean Windows user profile. Follow the existing release process for signing.

Evidence from this workspace: 97 focused Qt and Python regression tests passed. Chromium launch reached the browser process but its required socket was denied by the runner. See the [baseline Windows job](https://github.com/mihran94/JARVIS-AI/actions/runs/44587676625).
