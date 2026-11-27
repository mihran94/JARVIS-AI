# M-CORE stage 1 — recovery and session reliability

27 November 2026. This is the first production reliability batch from the
M-CORE 1.0.0 plan. Product name, version 0.3.0, UI layout, credentials and owner
profile are unchanged. Physical voice/phone/camera acceptance remains separate.

## Reproduced faults and resulting behavior

| Trigger | Previous behavior | Result |
| --- | --- | --- |
| Restart with a pending/running saved coding improvement | Store marked it `interrupted`, but the retry query and task property did not recognize that state | The task is available for explicit retry with its original goal/provider preserved. A fresh approval is still required; startup does not replay it. |
| Invalid saved camera device preference | Hex decoding raised ValueError/TypeError while constructing the desktop | Fall back to the default device selection without overwriting the saved value or turning the camera on. |
| Old socket delivers a delayed text/binary packet after reconnect | Old session content could terminate or modify the replacement session | Each inbound socket callback is bound to its originating socket and ignored after replacement. |
| Speaker reset triggers Stop while interrupting a reply | Interrupt dereferenced the cleared player or reopened audio after Stop | Check player/session identity after reset/start; stop leaves audio closed. |
| Turn completion or Heard callback starts another turn/session | Old processing could erase the next transcript or append the old reply | Clear completed-turn buffers before emitting callbacks, and discard remaining old content after a session change. |

`tests/test_reliability_baseline.py` adds 11 cases. The initial nine fault cases
failed against the previous production behavior before the fixes. Additional
cases verify approval on retry and reentrant session replacement.

## Validation

- Focused voice/update/rollback regression: 57 passed.
- Focused recovery, LiveVoice and development-workflow integration: 33 passed
  using the repository-pinned pytest 8.3.5.
- Full local regression uses fresh pytest subprocesses per module and isolated
  temporary directories. pytest 8.3.5 is loaded from a dedicated QA directory;
  neither the global test installation nor the application venv is changed.
- Source-integrity, diff/byte-compilation and startup checks accompany the final
  result. Full-run totals are recorded in the associated pull request's validation
  section after the queues complete.

No real microphone, camera frame, provider key or paid provider request is needed
by the new regression cases. Fake socket/audio devices reproduce delayed signals
and stop races deterministically.

## Remaining stage-1 work

This batch does not claim that all reliability work is finished. Continue with
long-session worker/resource soak tests, physical device disconnect/reconnect,
real Internet-loss recovery and update/restart acceptance on the owner's PC.
Those gates remain in `MCORE_1_0_0_PLAN.md`.
