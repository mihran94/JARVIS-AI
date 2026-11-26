# Windows acceptance results

- Machine: **Linux-5.10.134-18.0.12.lifsea8.x86_64-x86_64-with-glibc2.36** (Python 3.11.2)
- Checks run here: **13**
- Checks that need the real Windows desktop: **2**
- Passed: **13**
- Failed: **0**

| Result | Check | What was found |
| --- | --- | --- |
| PASS | One JARVIS window | Exactly one JARVIS window is open. |
| PASS | The HUD is on every page | The HUD sits above the pages of the one window, with the CPU and memory dials, the task step, the engine and Emergency Stop. |
| PASS | The engine settings are in one view | Settings carries the AI engines group: the Gemini fallback toggle, the on-device model and the local voice models. |
| PASS | Automation is one page | The Automation page holds the browser, Suggestion Mode, Work on this, Any App Control, the proposed actions and the task activity. |
| PASS | Offline Tamil and Tanglish voice | Tanglish becomes the Tamil script and is routed to the Tamil model. No voice model is installed on this computer yet. |
| NOT RUN | The offline recogniser hears Tamil and English in one sentence | The Windows offline recogniser and the SAPI voices are Windows only. This check has not been run on this computer. |
| PASS | Saved projects | The project was saved and read back. |
| PASS | Approve for me persists | The approval mode is remembered and is in force after a restart. |
| PASS | Calculator runs without prompting | The Calculator action is a routine action, so it runs without a prompt, and 17 × 23 is 391. |
| NOT RUN | The Calculator display shows 391 | The Windows Calculator is Windows only. This check has not been run on this computer. |
| PASS | Notepad Save still asks | The save is a local write, so it asks in every mode except full access. |
| PASS | A browser draft waits inside Automation | The draft is shown in Automation with Run, Edit and Dismiss, and it is not sent until the owner runs it. |
| PASS | A routine task stays local | The routine task was answered on this computer, with the Gemini fallback turned on. |
| PASS | One step uses Gemini | The on-device model could not complete this step, so Gemini answered it. |
| PASS | Local tasks work with the network unplugged | The task was answered on this computer with no key and no network, and Gemini was not needed. |

- **The offline recogniser hears Tamil and English in one sentence** — The Windows offline recogniser and the SAPI voices are Windows only. This check has not been run on this computer.
- **The Calculator display shows 391** — The Windows Calculator is Windows only. This check has not been run on this computer.
