# Video Editing Studio — section review

**Section slug:** `video-editing-studio`
**Source baseline:** `954af152a263` ("Merge AI Brain & Voice, provider fixes, and manual release candidate workflow", 2026-11-16)
**Changes:** `develop/video-editing-studio/changes.patch`
**Status:** Ready for Review

> **This patch applies directly to `main`.** The AI Brain & Voice section it
> was originally stacked on has been merged, so this patch no longer needs it
> first. See §8.

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
| `desktop/app.py` | The Video Editor shows the shot list, a sheet chooser (Shot list / Flow prompts / Higgsfield prompts / Editing checklist), a **Copy to clipboard** button, and **Export for DaVinci Resolve**. The export buttons no longer force the page to scroll sideways. |
| `desktop/video_export.py` | The DaVinci Resolve and CapCut exports both select an existing output folder. MP4 preview still chooses a file. |
| `tests/test_video_editing_studio.py` | Tests cover the JARVIS workflow, including the DaVinci button through package creation and missing Higgsfield prompts with cinematic fields present. |
| `tests/test_ai_brain_voice.py` | Six end-to-end chat-flow tests carried over — see §6. |

### The two engine prompts

The plan now holds both, and each one is written in that engine's own style:

| Field | Written for | Guidance given to the model |
|---|---|---|
| `flow_prompt` | Google Flow | reference use, composition, camera movement, lighting, one main action |
| `higgsfield_prompt` | Higgsfield | subject action, then setting and lighting, then ONE camera move, then mood |

Both describe **the same shot**. The prompt sheet groups the text by shot so
the editor can copy the desired prompt.

### Backwards compatibility

Plans with only a Google Flow prompt remain usable. A missing Higgsfield
prompt marks the plan **PARTIAL PLAN**, even when camera, lighting, and sound
are present. The Higgsfield sheet shows `(not specified)` for the missing
prompt and labels the Google Flow fallback for adaptation.

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

The original MiniMax submission recorded 597 passing tests and 3 skips.
The corrected submission passed all 63 targeted Video Editing Studio and
AI Brain & Voice tests. These cover the DaVinci folder picker, action approval,
package creation with FFmpeg, and Higgsfield fallback labels.

```cmd
python -m pytest -q tests/test_video_editing_studio.py tests/test_ai_brain_voice.py
```

### Passed with mocks

| Check | Test |
|---|---|
| A Tamil brief is recognised and reaches the provider unchanged | `test_the_tamil_brief_reaches_the_provider_unchanged` |
| The instruction asks for both engines and both prompt fields | same test |
| The shot list shows duration, camera, lighting, sound and the English subtitle | `test_the_shot_list_shows_duration_camera_lighting_sound_and_subtitles` |
| A plan without the cinematic fields is labelled partial | `test_a_plan_without_the_cinematic_fields_is_labelled_partial` |
| One brief produces a different prompt for each engine | `test_one_brief_produces_a_prompt_for_both_engines` |
| Missing Higgsfield prompts mark the plan partial and show a labeled fallback | `test_the_higgsfield_sheet_labels_a_missing_prompt` |
| The editing checklist covers CapCut and DaVinci Resolve and every shot | `test_the_editing_checklist_covers_capcut_and_davinci_resolve` |
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
| The DaVinci button chooses a folder, requests approval, and generates the handoff with FFmpeg | `test_the_davinci_button_exports_video_captions_and_checklist` |
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

## 6. Six carried-over tests

`tests/test_ai_brain_voice.py` gains six tests that were written for the AI
Brain & Voice section **after** it was first submitted, so that section was
merged without them. They drive the **real** entry point — `Window.send()` →
`ChatWorker` → `providers.chat.stream_chat` — with only the HTTP transport
replaced, and they prove that the chosen provider really receives the request,
that the profile really decides the model, that the backup is used **only**
when it is enabled, and that a rejected key never reaches it.

They are carried here rather than left on `development` because the section they
belong to is already merged. They are additive: no existing test was changed.

## 7. A narrow-window defect fixed on the way

The Video Editor page asked for 486 pixels inside a 442-pixel viewport at a
680-pixel window, so the page scrolled sideways. The cause was the long labels
on the full-width export buttons ("Export for DaVinci Resolve" and friends),
whose minimum width was wider than the window.

This defect was **pre-existing** — the baseline had the same 44-pixel overflow —
and it was found by rendering the page at a narrow width, which is part of this
cycle's verification. The buttons now keep their natural width when there is
room and give some of it back when there is not, the same approach PR #28 used
for the iPhone pairing buttons.
`test_the_video_editor_page_stays_readable_at_narrow_desktop_size` now guards
it.

## 8. Applying and reverting the patch

**Apply**

```cmd
git fetch origin development
git show origin/development:develop/video-editing-studio/changes.patch > "%TEMP%\jarvis-video-studio.patch"
git switch --detach 954af152a263
git apply "%TEMP%\jarvis-video-studio.patch"
python scripts\source_manifest.py
python scripts\source_manifest.py --check
```

The manifest step is required: the patch deliberately leaves
`docs/SOURCE_INTEGRITY.sha256` out, because it is a generated file. A
conflicting generated file would make the patch refuse to apply for no reason.

**Revert**

```cmd
git revert <the commit that applied the patch>
```

or, before committing:

```cmd
git apply -R "%TEMP%\jarvis-video-studio.patch"
```

**Verify after applying**

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Install FFmpeg and ffprobe to exercise the media export tests.

## 9. What was not done

* No provider, model or endpoint was invented, and no key was read, stored,
  logged or transmitted.
* No PC action flow, approval dialog or security policy was changed.
* No release was published and `main` was not touched. The owner merges and
  publishes.
