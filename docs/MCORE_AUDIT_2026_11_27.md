# JARVIS M-CORE preparation audit — 27 November 2026

## Baseline and scope

Audited production baseline: `d0c2910bf27b36fe227e18a561d922e6dda7b539`
(main, weather animation and native M icon). Product version remains `0.3.0`.
The M-CORE 1.0.0 document is a release plan, not a published release.

Enumerated 675 Git-tracked files and parsed/byte-compiled all 347 tracked Python
files. No Python syntax errors or duplicate definitions within module/class scopes
were found. Source-integrity and signing-material filename checks passed.
Manually inspected desktop input/focus validation, approval and stop boundaries,
voice intent routing, local model startup, camera freshness, remote listener
restrictions, first-run configuration and source-update application checks.
This is a structural audit plus targeted review, not a line-by-line review of every
file or a complete vulnerability assessment.

## Verified production CI

Both jobs ran against the exact baseline above:
[Desktop and core tests](https://github.com/mihran94/JARVIS-AI/actions/runs/45920066445).

| Environment | Result |
| --- | --- |
| Windows CI | 1,694 passed, 29 skipped |
| Linux CI | 1,698 passed, 25 skipped |
| Windows integration/installer CI | Success; [run](https://github.com/mihran94/JARVIS-AI/actions/runs/45920066407) |
| Existing PC application venv | Pinned runtime imports and `pip check` passed |
| Existing venv, isolated offscreen startup | `scripts/launch.py --smoke-test` exited 0 |
| Real browser acceptance | Controlled headless browser document: Tamil fill/readback, file selection, receipt and refusal checks passed |

Installer CI success is evidence for its existing workflow, not a claim that a
signed M-CORE 1.0.0 installer has been released.

## Local regression method

The first single-process run was stopped after its Qt process grew to approximately
4 GB and slowed down. It also exposed test-environment PDF dependency access
failures, a host-dependent Ollama test and one transient WebSocket timing failure.
It is not recorded as a successful full run.

The suite was then run as all 143 `test_*.py` modules in fresh pytest subprocesses,
with three independent queues, isolated temporary directories and JUnit results.
This used PC-user access to the already-installed PDF test dependency. The tests
were not rewritten to skip failures. The opt-in real-browser test was also run
separately against a controlled page, without using the owner's accounts.

All 143 modules completed. Local result: **1,691 primary test cases passed,
32 skipped, zero assertion failures/errors**, plus 12 passing unittest subtests.
The local test executable is pytest 9.2.0; production CI above uses the pinned
pytest 8.3.5. The newer local runner includes subtests in JUnit totals (1,735
including subtests), so raw JUnit counters must not be compared directly with
the 1,723 collected primary cases. Extra local skips reflect local prerequisites.

The original voice-module process exited abnormally after passing its assertions;
it is retained as a failed process run. After explicit fixture cleanup, two fresh
runs passed all 35 tests and exited 0. The editor-isolation correction also passed
its full 28-test module with exit 0. A module's successful assertions alone do not
count as a clean run if its process exits abnormally.

## Defects found and fixed in the test harness

### Unexpected VS Code windows

`tests/test_context_assistant.py` approved an editor step while mocking the coding
provider but not the native editor launcher. On a PC with VS Code installed, its
demo workflow opened the real temporary `project-a` folder. During the audit, the
observed VS Code process command referenced the audit's temporary test directory.

The fixture now replaces `desktop.app.open_project_in_editor` with a recording
stub, and the full-workflow test asserts that the requested editor and exact
project were dispatched once. It still exercises the workflow and approvals, but
does not launch the owner's editor. The corrected module passed all 28 tests.
Other personal-coding and phase-1 workflow fixtures already stub this boundary.

### Missing-Ollama test depended on the PC

The missing-installation test supplied an empty executable, which still invokes
automatic executable discovery. It failed on this PC because Ollama is installed.
The test now explicitly supplies a missing-discovery result. Production automatic
discovery is unchanged. Local-model and LiveVoice regression: 23 passed.

### Voice module exited abnormally after reporting success

An isolated voice-panel run reported 35 passing assertions, then failed during
native Qt shutdown. The test fixtures left voice widgets/deferred deletions for
interpreter teardown. Fixtures now stop workers and destroy their voice widgets
while QApplication still exists, then flush deferred deletion events.
Two fresh corrected runs passed all 35 tests and exited 0.

These corrections affect tests and evidence reliability. They do not redesign the
production interface, change credentials, modify the user's profile, or bump the
application version. The source-integrity manifest is updated with them.

## Coverage and remaining acceptance

The automated suite exercises command routing, mouse/keyboard validation,
Calculator result parsing, editor save/readback, approvals, emergency stop,
provider selection, voice transcripts/barge-in/transport reconnect, camera state,
memory, authenticated remote requests, pairing/revocation, coding review and
update/rollback. Mocked/native-boundary tests are not proof that every installed
application can be controlled successfully.

Skip reasons include unavailable FFmpeg/ffprobe and Tesseract, opt-in Docker/live
Azure checks, platform-specific assertions and unavailable symlink privileges.
The browser opt-in skip is supplemented by the separate successful real-browser run.

Still required before claiming M-CORE 1.0.0 acceptance:

- Physical Tamil/Tanglish microphone accuracy, Gemini voice identity and interruption.
- Real object recognition through the PC and phone cameras, including latency measurements.
- Real phone QR pairing, audio/video interaction and Tamil voice/chat reply on the phone.
- Actual Internet outage and recovery; the successful controlled WebSocket disconnect is
  a narrower transport test.
- Native desktop Calculator/Notepad interaction through the current user session.
- A real Mac first-run, Keychain save and audio/camera session.
- Continuous phone audio/video call parity. Current browser capture is turn-based and
  browser speech synthesis is not proof of a Gemini audio stream.

These items are not silently marked passed while the owner is away. Their gates
and work order are in `MCORE_1_0_0_PLAN.md`.
