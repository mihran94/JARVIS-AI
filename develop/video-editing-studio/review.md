# Video Editing Studio — section review

**Section slug:** `video-editing-studio`
**Source baseline:** `47ac1e21d0682502ec117b457a0f16cc718070f6` ("Integrate the JARVIS Command Center HUD", 2026-11-16)
**Changes:** `develop/video-editing-studio/changes.patch`
**Status:** Ready for Review

> **This patch applies on top of the AI Brain & Voice patch.**
> `develop/ai-brain-voice/changes.patch` is already submitted and is not yet
> merged into `main`, so this section's changes were developed on top of it.
> Apply them in that order — see §8.

---

## 1. What this section does

One Tamil brief becomes one finished package for the editor.

Before this section, a plan was a list of shots with a summary and **one**
prompt for **one** engine. Getting a Higgsfield prompt meant regenerating the
whole plan with a different engine selected, and the story could drift between
the two runs.

Now one brief produces:

* **A cinematic shot list.** Every shot carries its duration, the camera
  movement, the lighting, the sound cues, the Tamil voiceover and the English
  subtitle — as separate, visible fields rather than prose folded into one
  sentence.
* **A copy-ready prompt for Flow AND for Higgsfield.** Both are written from the
  same shot, in the same plan, in one model call. The owner copies whichever
  one they need; there is no second brief and no second generation.
* **An editing checklist for CapCut Desktop and DaVinci Resolve**, built from the
  same plan: every shot with its clip name, target length, camera, lighting,
  sound cue and subtitle, then each editor's own steps in its own order.

## 2. What changed

| File | Change |
|---|---|
| `video_studio/planning.py` | The plan carries `camera`, `lighting`, `sound` and `higgsfield_prompt` per shot. The model is asked for both engine prompts. `parse_plan` accepts the old shape too. New: `shot_list()` and `prompt_sheet()`. |
| `video_studio/editing.py` | **New.** `editing_checklist()` (CapCut + DaVinci Resolve), `export_davinci()`, `clip_name()`. |
| `desktop/app.py` | The Video Editor shows the shot list, a sheet chooser (Shot list / Flow prompts / Higgsfield prompts / Editing checklist), a **Copy to clipboard** button, and **Export for DaVinci Resolve**. |
| `tests/test_video_editing_studio.py` | **New.** 14 tests, driven through the JARVIS window. |

### The two engine prompts

The plan now holds both, and each one is written in that engine's own style:

| Field | Written for | Guidance given to the model |
|---|---|---|
| `flow_prompt` | Google Flow | reference use, composition, camera movement, lighting, one main action |
| `higgsfield_prompt` | Higgsfield | subject action, then setting and lighting, then ONE camera move, then mood |

Both describe **the same shot**. The prompt sheet is what gets pasted into the
engine, so it carries only prompts — one after another, nothing else.

### Backwards compatibility

An older plan that carries only one prompt still parses, still renders, and
still answers for both engines: the missing half is filled in from the prompt
that IS there. Such a plan is marked **PARTIAL PLAN** and every missing field
reads `(not specified)`, so the interface never shows an empty column as if it
had been designed that way.

## 3. Labelled behaviour

Everything in this section that is an estimate, a fallback or a limitation says
so on the screen:

| What | Where it is labelled |
|---|---|
| Caption timings come from the plan, not from a recorded voiceover | `ESTIMATED TIMINGS` at the top of the checklist |
| The model left some fields out | `PARTIAL PLAN` in the shot list, the prompt sheet and the checklist, with each missing field marked `(not specified)` |
| JARVIS does not write a DaVinci Resolve XML timeline | a line in the DaVinci checklist: *"Build the timeline by hand. JARVIS hands over the MP4, the English SRT and this checklist, not a Resolve XML timeline."* |
| The FFmpeg preview cannot run without FFmpeg | the existing *"Install FFmpeg with ffprobe and add both to PATH, then restart JARVIS."* |

The Command Center HUD's device panels already carried `SIMULATION` and
`SAMPLE DEVICES` labels and are unchanged.

## 4. Test results

Measured on the same machine, same command, from a clean checkout of the
baseline with the patches applied:

| Tree | Result |
|---|---|
| Baseline `main` @ `47ac1e21` | `534 passed, 3 skipped, 1 failed` |
| AI Brain & Voice applied | `580 passed, 3 skipped, 1 failed` |
| AI Brain & Voice + this section | **`594 passed, 3 skipped, 1 failed`** |

The 14 extra passing tests are the 14 new tests in
`tests/test_video_editing_studio.py`.

**The single failure is the same failure that exists on the baseline** and is
not caused by this work:

```
tests/test_personal_layout.py::test_chat_and_phone_stay_readable_at_narrow_desktop_size
assert 6 == 0
```

The iPhone pairing tab asks for sideways scrolling at a 680-pixel window.
**PR #28 (`fix/windows-test-env-20261116`) already fixes it** and is green on
all three workflows. It is deliberately not duplicated here, because PR #28 also
changes `docs/SOURCE_INTEGRITY.sha256` and `providers/chat.py`, and copying it
would create a conflict for no gain. **Merge PR #28 first.**

### Passed with mocks

| Check | Test |
|---|---|
| A Tamil brief is recognised and reaches the provider unchanged | `test_the_tamil_brief_reaches_the_provider_unchanged` |
| The instruction asks for both engines and both prompt fields | same test |
| The shot list shows duration, camera, lighting, sound and the English subtitle | `test_the_shot_list_shows_duration_camera_lighting_sound_and_subtitles` |
| A plan without the cinematic fields is labelled partial | `test_a_plan_without_the_cinematic_fields_is_labelled_partial` |
| One brief produces a different prompt for each engine | `test_one_brief_produces_a_prompt_for_both_engines` |
| A one-prompt plan still answers for both engines | `test_the_prompt_sheet_of_a_partial_plan_still_answers` |
| The checklist covers CapCut and DaVinci Resolve and every shot | `test_the_editing_checklist_covers_capcut_and_davinci_resolve` |
| The checklist is built from the plan alone | `test_the_checklist_is_built_from_the_plan_alone` |
| The copy button puts the chosen sheet on the clipboard | `test_the_copy_button_puts_the_sheet_on_the_clipboard` |
| The page offers the sheets, the copy button and the Resolve export | `test_the_video_page_offers_the_sheets_the_copy_and_the_resolve_export` |
| The Shot list sheet is the same list the preview shows | `test_the_sheet_list_is_the_same_shot_list_the_preview_shows` |
| The page does not ask to scroll sideways at 680 pixels | `test_the_video_editor_page_stays_readable_at_narrow_desktop_size` |

### Passed with the real toolchain

FFmpeg and ffprobe were on `PATH`, so the export path was **really** run, not
mocked:

| Check | Test |
|---|---|
| The DaVinci handoff really contains the video, the captions and the checklist | `test_the_davinci_handoff_carries_the_video_the_captions_and_the_checklist` |
| The CapCut handoff still works | `test_the_capcut_handoff_still_works` |

### Blocked — needs the owner's machine

| Check | Why | What the owner does |
|---|---|---|
| A **live Gemini plan** | No `GEMINI_API_KEY` here | Generate with Gemini in the Video Editor |
| The **actual model output** for the new fields | A model that ignores the new fields would produce a plan marked PARTIAL | Generate once and confirm the shot list shows camera, lighting and sound |
| **Google Flow** and **Higgsfield** | No accounts here | Copy the Flow prompts into Flow and the Higgsfield prompts into Higgsfield, and confirm each reads as a usable prompt |
| **CapCut Desktop** | Not installed here | Import `video.mp4` + `english.srt` and follow the checklist |
| **DaVinci Resolve** | Not installed here | Import the same two files and follow the Resolve checklist |
| A **real Tamil voiceover** | No microphone | Record the narration and check every caption against it — the checklist timings are estimates |

### A narrow-window defect fixed on the way

The Video Editor page asked for 486 pixels inside a 442-pixel viewport at a
680-pixel window, so the page scrolled sideways. The cause was the long labels
on the full-width export buttons ("Export for DaVinci Resolve" and friends),
whose minimum width was wider than the window.

This defect is **pre-existing** — the baseline `main` has the same 44-pixel
overflow — and it was found by rendering the page at a narrow width, which is
part of this cycle's verification. The buttons now keep their natural width
when there is room and give some of it back when there is not, the same
approach PR #28 uses for the iPhone pairing buttons. `test_the_video_editor_page_stays_readable_at_narrow_desktop_size`
now guards it.

## 5. Limitations

* **The caption timings are estimated.** They come from the plan, which is
  written before the voiceover is recorded. The checklist says so. Nothing
  claims the captions are frame-accurate against a recording.
* **JARVIS does not write a DaVinci Resolve timeline.** It hands over the MP4,
  the English SRT and a shot-by-shot checklist. A hand-written Resolve XML that
  Resolve silently ignored would be worse than a checklist, and this is stated
  in the DaVinci section of the checklist itself.
* **The model may leave the new fields out.** A plan is then marked PARTIAL and
  the missing fields read `(not specified)`. Nothing is invented to fill them.
* **The plan is still 30 seconds and 1080 × 1920.** This section makes the plan
  richer; it does not change the format the rest of the product exports.
* **Both prompts describe the same shot.** If the owner changes their mind
  about a shot, both prompts have to be regenerated together, which is why the
  plan is regenerated rather than edited by hand.
* **No preview/ folder.** No Google AI Studio export was supplied, so the
  existing Video Editor page was used as the UI reference.

## 6. Running this section on Windows

```cmd
git clone https://github.com/mihran94/JARVIS-AI.git
cd JARVIS-AI
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pythonnet==3.2.1 pywin32==312
setup.cmd
START_JARVIS.cmd
```

1. Open **Video Editor**.
2. Type the Tamil brief, for example
   `அய்யன் மரக்கன் தொடர்பான கதை — திறப்பு தரைப்பாடு, புதிய காட்சி, முடிவு`.
3. Choose the primary engine and press **Generate with Gemini**.
4. The **shot list** appears below, with duration, camera, lighting, sound and
   the English subtitle for every shot.
5. Use the chooser to switch between **Shot list**, **Flow prompts**,
   **Higgsfield prompts** and **Editing checklist**, and press
   **Copy to clipboard** for the one you want to paste.
6. **Export for CapCut Desktop** or **Export for DaVinci Resolve** to get the
   video, the captions and the checklist in one folder.

FFmpeg and ffprobe must be on `PATH` for the preview and the exports.

## 7. How it was verified

The whole workflow was driven **through the JARVIS window**, not around it:
the brief was typed into the Video Editor, **Generate with Gemini** was
pressed, and the provider was reached through the real `ProviderRouter` with
only the HTTP transport replaced. The exports were run with the real FFmpeg.

## 8. Applying and reverting the patch

This section's changes were developed on top of the AI Brain & Voice section,
which is submitted but not yet merged. Apply them in that order.

**Apply**

```cmd
git checkout 47ac1e21d0682502ec117b457a0f16cc718070f6
git apply ..\ai-brain-voice\changes.patch
git apply develop\video-editing-studio\changes.patch
python scripts\source_manifest.py
python scripts\source_manifest.py --check
```

If the AI Brain & Voice section has already been merged into `main`, this
patch applies on its own.

The manifest step is required: the patch deliberately leaves
`docs/SOURCE_INTEGRITY.sha256` out, because it is a generated file and PR #28
changes the same file. A conflicting generated file would make the patch refuse
to apply for no reason.

**Revert**

```cmd
git revert <the commit that applied the patch>
```

or, before committing:

```cmd
git apply -R develop/video-editing-studio/changes.patch
```

**Verify after applying**

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Expected: `594 passed, 3 skipped`, and the one pre-existing layout failure
until PR #28 is merged.

## 9. Interaction with the open pull requests

* **PR #28** fixes the one failing test and refreshes the provider model list.
  Its hunks in `providers/chat.py` do not overlap with this section, and this
  section does not touch `providers/chat.py` at all. Both change
  `docs/SOURCE_INTEGRITY.sha256`, which is why the manifest is regenerated
  rather than patched. **Merge PR #28 first.**
* **PR #26** (versioned release candidates) and **PR #27** (certificate
  pinning) touch other areas and do not overlap.

## 10. What was not done

* No provider, model or endpoint was invented, and no key was read, stored,
  logged or transmitted.
* No PC action flow, approval dialog or security policy was changed.
* No release was published and `main` was not touched.
