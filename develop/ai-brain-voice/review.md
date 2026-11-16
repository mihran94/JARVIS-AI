# AI Brain & Voice — section review

**Section slug:** `ai-brain-voice`
**Source baseline:** `47ac1e21d0682502ec117b457a0f16cc718070f6` ("Integrate the JARVIS Command Center HUD", 2026-11-16)
**Submission branch:** `development` (from `9b7e611`)
**Changes:** `develop/ai-brain-voice/changes.patch`
**Status:** Ready for Review

> **The Video Editing Studio section is built on top of this one.** Its patch
> applies after this patch, because this section is submitted but not yet
> merged into `main`. See
> [develop/video-editing-studio/review.md](../video-editing-studio/review.md).

---

## 1. What this section does

It makes the AI brain honest about four things that were previously indistinguishable,
and it makes the choice of provider the owner's rather than a hardcoded default.

1. **Which brain answers.** The chat page now remembers the provider the owner chose
   and shows it: `Active brain: Gemini · Fast · gemini-3.5-flash-lite`. Before, the
   provider was a drop-down that reset to Gemini every time the application started,
   and nothing on screen said which model was about to be paid for.
2. **Why a provider failed.** One sentence used to cover five different problems.
   Now every failure is classified, and the message says what to do about it.
3. **Whether the model exists.** A new free check asks the provider for its own model
   list and compares. No prompt is sent, so it costs nothing and puts none of the
   owner's words on the provider's servers.
4. **Whether voice is actually available.** The speech language can be chosen, and a
   missing microphone or a missing language voice now produces a sentence the owner
   can act on.

## 2. The Gemini HTTP 404

This was the reported problem, and it is now answered precisely.

Gemini answers **HTTP 404** for two completely different reasons, and the old code
treated both as "the model was not available":

| Situation | Gemini's answer | Now classified as | What the owner is told |
|---|---|---|---|
| The model ID is not served for this API version | `models/gemini-x is not found for API version v1beta` | `model_unavailable` | Use the recommended model, or one the key can use |
| The endpoint itself is wrong | `The requested URL was not found on this server` | `wrong_endpoint` | The URL is wrong; the provider never saw a model |
| The answer says neither | no useful evidence | `model_unavailable` | The model is named first, because it is the part the owner can get wrong |

The decisive evidence is the **response body**, which the old code discarded. The
classifier reads the body to decide the kind of failure and then **never echoes it**,
because a provider can return the key inside an error body, and that text ends up in
a message box and in a screenshot.

The Gemini case is now a solved problem rather than a guess: the new **Check model
availability** action asks Gemini for its catalogue. If the catalogue answers and the
model is not in it, the model is wrong. If the catalogue request itself fails with a
404, the endpoint is wrong. That is a definite answer, not an inference from a
sentence.

### The full classification

`providers/errors.py` is the single place that decides. Every kind is distinct, has
its own next step, and is covered by a test:

| Kind | Raised for | Backup allowed? |
|---|---|---|
| `model_unavailable` | the model is not served for this key | no |
| `wrong_endpoint` | the URL is wrong | no |
| `invalid_credentials` | 401, or a 400 that says the key is not valid | no |
| `no_access` | 403, the key is valid but not allowed | no |
| `quota` | 429 with a quota or billing body | no |
| `rate_limit` | 429 with a rate body | no |
| `bad_request` | 400 / 422 the request itself | no |
| `empty_key` | no key is configured | no |
| `server_error` | HTTP 500 | no |
| `network` | connection refused, DNS, TLS | **yes** |
| `timeout` | the provider did not answer in time | **yes** |
| `transient` | 502 / 503 / 504 | **yes** |

**The backup rule is unchanged.** Only a provider that is *not answering* justifies the
one backup attempt the owner can consent to. A throttled key, an exhausted quota, a
rejected key and a bad model never spend the backup provider. This matches the
existing contract in `tests/test_desktop_fallback.py`, which pins 429 and 500 as
non-retryable; the classification keeps it.

## 3. Changed files

| File | Change |
|---|---|
| `providers/errors.py` | **New.** The classifier: 12 failure kinds, each with its own title, sentence and next step. Never returns the response body. |
| `providers/models.py` | **New.** Model availability. Lists the provider's catalogue (Gemini `v1beta/models`, OpenAI-compatible `…/models`, Claude `v1/models`) and compares. No prompt is sent. |
| `providers/profiles.py` | **New.** Fast and Deep as one concept. A provider declares whether it has two models or one. |
| `providers/chat.py` | The chat path now raises a classified failure. `ProviderFailure` carries the diagnosis; `TransientProviderError` is a subclass, so the existing backup gate is untouched. |
| `desktop/app.py` | The primary chat provider and the backup provider are remembered. The active brain is shown. The Provider Manager gains a profile chooser and **Check model availability**. The voice states use the agreed words. |
| `desktop/voice_panel.py` | A speech-language chooser (English / தமிழ் / Français), a clear message when that language has no installed voice, and Tamil text is always spoken with a Tamil voice. |
| `desktop/speech.py` | "Speech unavailable: RuntimeError" became a sentence the owner can act on. |
| `quantum_core/launcher.py` | `hud_info` names the provider as well as the model. |
| `quantum_core/web/index.html` | The Command Center HUD names the provider, and the voice line now says **Thinking** instead of nothing. |
| `tests/test_ai_brain_voice.py` | **New.** 46 tests. |
| `docs/SOURCE_INTEGRITY.sha256` | Refreshed. **Deliberately left out of the patch** — see §8. |

## 4. How each requirement is met

| Requirement | Where |
|---|---|
| Choose OpenAI or Gemini as the primary chat provider | `desktop/app.py` — `stored_chat_provider`, `on_chat_provider_changed`. All eight existing providers stay available; the choice is remembered. |
| Keep existing provider choices, reuse saved credentials | The registry, the router and `security/vault.py` are untouched. Keys stay in Windows Credential Manager and are read through the existing `get_key`. |
| Show the active provider and model | `brain_label` on the chat page, and the HUD model label now reads `Gemini · gemini-3.5-flash-lite`. |
| Preserve Fast and Deep for supported configurations | `providers/profiles.py`. Gemini keeps Fast (`gemini-3.5-flash-lite`) and Deep (`gemini-3.8-flash`) — the same pair the HUD already used. A test fails if the HUD and the desktop drift apart. |
| Verify model availability for the configured provider | **Check model availability** in the Provider Manager. A `GET`, never a prompt. |
| Actionable error for an unavailable model or a wrong endpoint | `providers/errors.py`, `model_unavailable` vs `wrong_endpoint`. |
| Distinguish invalid credentials, quota and network errors | Separate kinds, each with its own next step (§2). |
| Provider selection works from settings through the chat flow | The Provider Manager's **Save provider settings** switches the chat provider and refreshes the active brain; `send()` uses the selected provider, profile and model. |
| Backup provider only when enabled | Unchanged. `backup_consent` still gates it, and the classification keeps a bad key, a quota and a rate limit from ever reaching it. |
| Tamil, English and French text chat | The chat already accepted all three and the system prompt asks for the user's language. The speech-language chooser now makes it explicit for voice as well. |
| Push-to-talk kept | The Speak button and **Talk once** are untouched. |
| Listening, Thinking, Speaking, Idle states | The desktop HUD now reads `IDLE`, `LISTENING`, `THINKING`, `ANSWERING`, `SPEAKING`, `STOPPED`. The browser HUD reads `Listening`, `Thinking`, `Speaking`, `Voice idle`. |
| Clear message if the microphone or a speech voice is unavailable | The voice panel says which language has no installed voice and what to install. The Speak box no longer says `Speech unavailable: RuntimeError`. |
| Existing credential store, no keys in source, logs, screenshots or browser code | The vault is untouched. `hud_info` carries no key, and a test asserts it. The classifier never returns the body. The model check runs on the desktop side and returns only a verdict. |
| PC actions behind the existing approval flow | Untouched. The chat system prompt still says the assistant cannot execute tools, and `security/policy.py` is unchanged. |

## 5. Test results

Run from a clean worktree at the baseline, with the patch applied and the
manifest refreshed:

```
580 passed, 3 skipped, 1 failed
```

**Baseline before the patch** (`47ac1e21`, measured on the same machine, same
command): `534 passed, 3 skipped, 1 failed`.

The 46 extra passing tests are the 46 new tests in
`tests/test_ai_brain_voice.py`.

Six of them drive the **real** chat entry point — `Window.send()` → `ChatWorker`
→ `providers.chat.stream_chat` — with only the HTTP transport replaced, so the
provider, the model and the key that reach the wire are the ones the application
really uses.

The single failure is **the same failure that exists on the baseline** and is **not**
caused by this work:

```
tests/test_personal_layout.py::test_chat_and_phone_stay_readable_at_narrow_desktop_size
assert 6 == 0
```

It is the iPhone pairing tab asking for sideways scrolling at a 680-pixel window.
**PR #28 (`fix/windows-test-env-20261116`) already fixes it** with the same
`setMinimumWidth(60)` change and is green on all three workflows. It is not
duplicated in this patch, because PR #28 also changes
`docs/SOURCE_INTEGRITY.sha256` and `providers/chat.py`, and duplicating it would
create a conflict for no gain. Merge PR #28 first and this test goes green.

### Passed with mocks — no network, no key, no hardware

| Check | How |
|---|---|
| Provider selection is remembered and shown | `test_the_primary_chat_provider_is_remembered`, `test_the_active_brain_names_the_provider_profile_and_model` |
| Fast / Deep switching | `test_switching_the_profile_changes_the_model`, `test_a_model_the_owner_typed_is_not_replaced_by_a_default` |
| The HUD and the desktop keep the same Fast/Deep pair | `test_the_hud_keeps_the_same_fast_and_deep_pair` |
| Every failure kind is distinct | 8 tests in `test_a_404_that_names_a_model_is_a_model_problem` … `test_no_key_at_all_is_its_own_problem` |
| The body and the key never reach the message | `test_the_diagnosis_never_repeats_the_body_or_the_key` |
| Gemini 404 names the recommended model and leaks nothing | `test_the_gemini_404_is_classified_and_names_the_recommended_model` |
| Only a transient failure may use the backup | `test_only_a_transient_failure_may_use_the_backup`, `test_a_transient_failure_is_the_only_one_marked_for_the_backup` |
| Empty key is refused before any request | `test_an_empty_key_is_refused_before_any_request` |
| Network failure is transient and carries no key | `test_a_network_failure_is_transient_and_never_carries_the_key` |
| Model availability: found, not found, list failed | 5 tests in `test_the_model_list_endpoint_is_derived_per_provider` … `test_a_snapshot_model_matches_its_stable_alias` |
| The model check sends no prompt | `test_the_model_check_sends_no_prompt` |
| The HUD never receives a key | `test_the_hud_status_never_carries_a_key` |
| Voice language, the four states, a missing voice | `test_the_speech_language_can_be_chosen`, `test_the_voice_states_use_the_words_the_owner_reads`, `test_a_missing_language_voice_is_reported_clearly` |
| The whole existing suite still passes | 580 passed |

### HUD reviewed at both widths

Rendered in headless Chromium from the patched tree. **No horizontal overflow at
either width**, and no page errors. The only console entry is the expected
`/eel.js` 404 in browser preview mode, which is how the page behaves when the Eel
backend is not running:

* desktop 1600 × 1000 — no overflow
* phone 390 × 844 — no overflow

### Blocked — needs the owner's machine

Nothing below was verified here, and no result is claimed for it:

| Check | Why it is blocked | What the owner does |
|---|---|---|
| A **live Gemini** answer | No `GEMINI_API_KEY` in this environment | Save the key in **AI Providers**, press **Test saved provider connection** |
| A **live OpenAI** answer | No `OPENAI_API_KEY` | Same |
| A **live model catalogue** for both | Needs a real key | Press **Check model availability** |
| The **Windows Credential Manager** path | Linux host; `Vault` refuses off Windows | Save a key, then confirm the status reads *Stored in Windows vault* |
| The **microphone** | No microphone, and System.Speech is Windows-only | Allow the microphone, choose **Talk once** |
| A **Tamil or French speech voice** | SAPI voices are Windows-only | Install the Tamil (ta-IN) and French (fr-FR) speech packs, then choose the language and press **Say it** |
| **Push-to-talk** on real hardware | No audio device | Hold the flow on the chat page and confirm `Listening → THINKING → SPEAKING` |

## 6. Limitations

* **Only Gemini has two models.** Fast and Deep are preserved where a provider
  really offers two. The other providers keep the single model they had. Inventing
  a "Deep" model ID that a provider does not serve would reproduce exactly the
  HTTP 404 problem this section exists to fix.
* **The model catalogue is not available everywhere.** Some deployments disable
  the listing. The check then answers *"I could not check"*, which is deliberately
  different from *"that model does not exist"*.
* **The Gemini 404 without evidence is reported as a model problem.** When the body
  says nothing, the model is named first, because it is the part the owner can get
  wrong. The **Check model availability** action is what turns this into a definite
  answer.
* **The desktop tests ran on Linux.** The Windows-only paths — the vault, the
  microphone and the SAPI voices — were exercised through their existing test
  doubles, not against real hardware.
* **No Google AI Studio preview was supplied**, so the existing Command Center HUD
  was used as the UI reference and no `preview/` folder is included.
* **The patch does not include `docs/SOURCE_INTEGRITY.sha256`.** See §8.

## 7. Running this section on Windows

```cmd
git clone https://github.com/mihran94/JARVIS-AI.git
cd JARVIS-AI
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pythonnet==3.2.1 pywin32==312
setup.cmd
START_JARVIS.cmd
```

Then:

1. **AI Providers** → choose **Gemini** or **OpenAI** → paste the key → **Save
   provider settings**. The status line must read *Stored in Windows vault*.
2. Open **Advanced settings** → pick **Fast** or **Deep** → **Use recommended
   model** → **Check model availability (free, no prompt sent)**.
   It must say *… is available to this key*.
3. Back on **JARVIS Chat**, the line above the composer reads
   `Active brain: Gemini · Fast · gemini-3.5-flash-lite`. Change the provider
   drop-down and it follows.
4. **Ask JARVIS** → the state line shows `THINKING`, then `ANSWERING`.
5. **Voice / Hey Jarvis** → **Allow the microphone** → choose the speech language
   → **Talk once (draft only)**. The transcript is a draft; press **Ask JARVIS** to
   send it.

## 8. Applying and reverting the patch

The patch is against the recorded baseline `47ac1e21d0682502ec117b457a0f16cc718070f6`.

**Apply**

```cmd
git checkout 47ac1e21d0682502ec117b457a0f16cc718070f6
git apply develop/ai-brain-voice/changes.patch
python scripts\source_manifest.py
python scripts\source_manifest.py --check
```

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
git apply -R develop/ai-brain-voice/changes.patch
```

**Verify after applying**

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Expected: `580 passed, 3 skipped`, and the one pre-existing layout failure until
PR #28 is merged.

## 9. Interaction with the open pull requests

* **PR #28** fixes the one failing test and refreshes the provider model list
  (`gpt-6-luna`, `MiniMax-M3.1-Flash`, `claude-sonnet-5-5`, `qwen3:8b`). The hunks
  in `providers/chat.py` do not overlap: PR #28 changes the `PROVIDERS` table, this
  patch changes the failure handling below it. Both change
  `docs/SOURCE_INTEGRITY.sha256`, which is why the manifest is regenerated rather
  than patched. **Merge PR #28 first.**
* **PR #27** and **PR #26** touch other areas and do not overlap.

## 10. What was not done

* No provider, model or endpoint was invented. Every model ID here was checked
  against the provider's own documentation, and the ones in the registry are the
  owner's from PR #28.
* No key was read, stored, logged or transmitted. The vault was not modified.
* No PC action flow, approval dialog or security policy was changed.
* No release was published and `main` was not touched.
