# The local-first assistant

What was built, where it lives, what it was tested against, and what was
not run.

---

## 1. The local engine and the Gemini fallback

### What was built

| Piece | Where |
| --- | --- |
| The engine router | `core/engines.py` |
| The on-device model supervisor | `core/local_model.py` |
| The setting | `desktop/app.py` → Settings → **AI engines** |
| The HUD engine chip | `desktop/hud.py` |
| The mission wiring | `desktop/mission_controller.py` |

**Starting the on-device model.** `core/local_model.py` finds Ollama, checks
whether it is already serving, and starts it when it is not. The server is
bound to `127.0.0.1:11434` and to nothing else, so a local model can never be
turned into an open relay. A model that is not installed is reported as
missing; nothing is ever downloaded. The window starts the model in a worker
thread at startup (`LocalModelWorker` in `desktop/app.py`).

**The toggle.** *Settings → AI engines → Use Gemini automatically when
needed*. It uses the existing Gemini provider configuration: the model from
the provider page and the key from the Windows Credential Manager. The
choice is remembered under `engines:gemini_fallback`.

**Per-step fallback.** A mission is a bounded loop of at most six steps
(`core/mission.py`). The planner is now the engine router:

* the **on-device model** answers the step through the same provider router
  as everything else (`ProviderRouter.stream` with the local `Ollama`
  specification, so there is never a second way out of the application);
* if that answer cannot be used as a decision — the "complex planning step"
  the local model could not complete — and the owner allowed the fallback,
  **exactly that step** goes to Gemini;
* the reason is recorded in three places: the `EngineStep` record, the HUD
  chip, and `engines:history` in the store, so it survives a restart.

**Only the context that step needs is shared.** `core.engines.step_context`
keeps the system instructions, the goal and the last two exchanges, and
drops everything older.

**Nothing sensitive leaves without the owner's approval.** Before a step
goes to Gemini, `classify_context` names what the context carries — a
protected file, the content of the screen, or microphone audio — and the
owner is asked through the **same approval gateway** as every other action
(`Gateway.run` → `Policy.approve`). A refusal blocks the step and nothing is
sent.

**When Gemini is not available**, the step is reported as blocked, the
mission says so, and it carries on with the steps the local model can do.
This is a new third outcome in the mission runtime (`action: "skip"`), and
the blocked step is on the rail like any other step.

**Routine chat, voice and PC actions stay local.** The chat keeps the
provider the owner chose, and on a fresh install that is the local model
(`on_local_model_ready` sets it when the owner has never chosen one). The
voice is the Windows offline recogniser and the Windows SAPI voices. A PC
action is a tool call: it never consults a model at all.

### The local models used

| Job | Model | Where it runs |
| --- | --- | --- |
| Understanding and planning | Ollama `qwen3:8b` | this computer, `127.0.0.1:11434` |
| Understanding and planning (fallback) | Gemini `gemini-3.5-flash-lite` | Google's endpoint, only for one step |
| Speech recognition | Windows System.Speech `en-US` and `ta-IN` | this computer, offline |
| Speech | Windows SAPI voices, LANGID `409` (English), `449`/`849` (Tamil) | this computer, offline |

The engine chip in the HUD says **Local** or **Gemini**, and under it the
sentence that says why Gemini was used.

---

## 2. Offline Tamil and Tanglish voice

### What was built

| Piece | Where |
| --- | --- |
| Tanglish detection, transliteration and script splitting | `voice/tanglish.py` |
| Which local voice models are ready | `voice/models.py` |
| The readiness display | Settings → AI engines, and the Voice page |

The Windows offline recogniser only understands the Tamil script, so a
Tanglish sentence is turned into the Tamil script before the recogniser
hears it. `voice/tanglish.py` does that with a word list for the words that
matter and a phonetic rule for the rest. A word the owner wrote in English
is left exactly as it was: turning "report" into Tamil in the middle of an
English sentence changes what the sentence says.

A sentence that mixes Tamil and English is split into its parts, and each
part is handled by the model that understands it. `language_for` routes a
Tanglish sentence to the Tamil recogniser and an English sentence to the
English one.

`voice/models.py` reads what is installed — the Windows recognisers for each
culture and the SAPI voices for each language — and says which are ready
and which are missing. The probe never opens the microphone and never
reaches the network. The microphone state and the mute are in the HUD and
on the Voice page, as they were.

---

## 3. One holographic JARVIS window

### What was built

| Piece | Where |
| --- | --- |
| The HUD | `desktop/hud.py` |
| The Automation page | `desktop/automation_panel.py` and `desktop/app.py` |
| The consolidated Settings view | `desktop/app.py` → `permissions_page()` |

The HUD is mounted above the pages of the one window, so it is in sight on
every page: an arc-reactor core with a slow sweep, the CPU and the memory
as dials, the step of the task, the engine that answered, an approval
badge, the microphone and the mute, and Emergency Stop.

Every reading is real. A reading that cannot be taken is drawn as an empty
dial and says so. The motion is slow, and it stops when the owner has asked
for less motion (`omega:reduced`).

The Tamil is drawn with the Tamil font of Windows: `desktop/hud.py` names
`Nirmala UI` in the type stack, so the Tamil the owner reads is measured
and drawn with the same font rather than with a fallback that has no Tamil
glyphs.

**Automation** is one page. It holds the browser, Suggestion Mode, Work on
this, Any App Control, the task activity and the proposed actions. The
allowlisted applications, the file and folder actions and the approval
boundary summary are on the same page.

**Settings** is one view. The **AI engines** group sits at the top of it,
next to the action approvals: the Gemini fallback toggle, the on-device
model and its **Start the on-device model** button, and the local voice
models with their **Check the voice models** button.

---

## 4. Automation and Any App Control

### What was built

The existing browser controls (`desktop/browser_control.py`,
`automation/browser.py`) and the verified Windows keyboard and mouse input
(`automation/input.py`, `automation/uia.py`, `automation/app_control.py`)
were reused as they are. What was added:

* **Run, Edit and Dismiss.** A proposed action is a card in Automation with
  three answers. Run runs it as it is. Edit opens the arguments, lets the
  owner change them, and runs it that way — the changed arguments are
  converted to the types the tool's own schema names and are checked
  against that schema again, so an edit cannot widen the call. Dismiss
  records the decision and does not run it.
* **The same gateway.** A mission's tool call now goes through the
  proposal card, and the card's answer goes through `Gateway.run` →
  `Policy.approve` → `Policy.execute`, which is the one path every action
  in JARVIS takes. A proposed action from the Gemini engine and one from
  the local engine are the same card.
* **The target is inspected before it is acted on.** Any App Control lists
  the open applications, reads the controls of the one in front, and then
  proposes one exact action.
* **Browser drafts stay reviewable.** The draft is in the Automation page,
  with the text, and it is not sent until the owner runs it.

---

## 5. The acceptance results

Run them with:

```
python scripts/run_windows_acceptance.py
```

The script builds the real window, runs every check, restarts the window,
runs the "one window" check again, and writes
`docs/WINDOWS_ACCEPTANCE.md`.

### What was run, and where

**These results were produced on Linux (Debian 12, Python 3.11), not on
Windows.** The two checks that need the real Windows desktop — the offline
recogniser hearing a mixed Tamil and English sentence, and the Calculator
display showing 391 — are reported as **not run**, not as passes.

| Result | Check | Requirement |
| --- | --- | --- |
| PASS | One JARVIS window | One JARVIS window after restart |
| PASS | The HUD is on every page | One holographic JARVIS window |
| PASS | The engine settings are in one view | Related settings are consolidated into one view |
| PASS | Automation is one page | Browser, Suggestion Mode, Work on this, Any App Control and task activity inside Automation |
| PASS | Offline Tamil and Tanglish voice | Offline Tamil and Tanglish voice |
| **NOT RUN** | The offline recogniser hears Tamil and English in one sentence | Offline Tamil and Tanglish voice |
| PASS | Saved projects | Saved projects survive a restart |
| PASS | Approve for me persists | Approve for me persists |
| PASS | Calculator runs without prompting | Calculator shows 391 for 17 × 23 without prompting |
| **NOT RUN** | The Calculator display shows 391 | Calculator shows 391 for 17 × 23 without prompting |
| PASS | Notepad Save still asks | Notepad Save still asks |
| PASS | A browser draft waits inside Automation | A browser draft is reviewable inside Automation |
| PASS | A routine task stays local | One routine task stays local |
| PASS | One step uses Gemini | One task automatically uses Gemini |
| PASS | Local tasks work with the network unplugged | Local tasks still work offline |

**13 passed, 0 failed, 2 not run.**

### Which test used Gemini, and why

| Test | Engine | Why |
| --- | --- | --- |
| *A routine task stays local* | **Local** | The on-device model answered. The Gemini fallback was **turned on** for this check, and Gemini was never called: the routine step was one the local model could do, so it stayed on this computer. The check deliberately makes any Gemini call an error, so "Gemini was not called" is proved, not assumed. |
| *One step uses Gemini* | **Gemini** | The on-device model was made to answer with something that is not a usable decision, which is the "complex planning step the local model cannot complete" case. The fallback was on, Gemini was configured, and **exactly that step** was sent to Gemini. The recorded reason is `local_model_could_not_complete_the_step`, and the HUD reads *"The on-device model could not complete this step, so Gemini answered it."* |
| *Local tasks work with the network unplugged* | **Local** | No key was configured and the fallback was on, so Gemini could not have answered even if it had been asked. The task was answered on this computer. The local model is reached on the loopback interface only, so unplugging the network cannot change it. |

No other check called Gemini. The check that proves it is the one where any
Gemini call raises.

### What has to be run on the owner's Windows machine

Two checks, and they are the two that need the real desktop:

1. **The offline recogniser hears Tamil and English in one sentence.** Open
   Voice / Hey Jarvis, allow the microphone, choose *Tamil + Tanglish*, and
   say a sentence that mixes both, for example *"வணக்கம், open the
   calculator"*. The transcript must carry both parts.
2. **The Calculator display shows 391.** Ask JARVIS to *"calculate 17 times
   23 in the Calculator"*, with **Approve for me** turned on. The display
   must be read back as 391, and there must be no prompt.

`scripts/run_windows_acceptance.py` runs both on Windows and writes them
into the report, so the same table comes back filled in.

---

## 6. The pictures

| Picture | What it shows |
| --- | --- |
| `tools/shots/09-hud.png` | The HUD on its own: the core, the engine chip and its reason, the CPU and memory dials, the step of the task, the approval badge, the microphone, the mute and Emergency Stop |
| `tools/shots/04b-settings-ai-engines.png` | Settings with the **AI engines** group: the Gemini fallback toggle, the on-device model and the local voice models |
| `tools/shots/08b-automation-panel.png` | The Automation page: the browser, Suggestion Mode and Work on this, Any App Control, the proposed actions and the task activity |
| `tools/shots/08c-proposed-action-card.png` | One proposed action, with Run, Edit and Dismiss, and the editable argument open |
| `tools/shots/08-proposed-action.png` | The whole window with a proposal waiting and the HUD showing the approval |
| `tools/shots/07-automation.png` | The Automation page in the window |
| `tools/shots/01-chat-dark.png`, `02-chat-light.png` | The conversation in both themes |
| `tools/shots/03-island.png` | The floating assistant |

`python tools/screenshots.py` writes them all.

---

## 7. What changed in the existing behaviour

Two changes are worth knowing about, because they are visible.

**Missions are planned by the on-device model.** Before this, a mission was
planned by the provider the owner had chosen in the chat. It is now planned
by the on-device model, with Gemini answering the one step that needs it.
An owner without Ollama installed must either install it or turn on the
Gemini fallback; otherwise the mission says *"The on-device model could not
answer this step"* and stops. This is the local-first design the brief
asks for, and it is the one change that affects owners who have a key but
no local model.

**A proposed action is answered in Automation, not in a message box.** The
mission's tool calls were confirmed by a modal question. They are now cards
in Automation with Run, Edit and Dismiss. The approval itself is unchanged:
one-use, through the same gateway, invalidated by Emergency Stop. The
modal question is still used for the actions the owner starts themselves,
and for the question about sharing something sensitive with Gemini.
