# Owner acceptance checklist — JARVIS PRIME

**What this is.** Everything below has to be run **on a real Windows
machine**, by the owner, because none of it can be proven from a build
server. The list is written so each line can be answered *yes* or *no*.

**What has already been proven.** Every commit in the stack was tested on
an Ubuntu runner and on a Windows runner by the workflow that runs by
itself. The Windows installer job also built the executable and the
installer. What those runners cannot do is talk to a microphone, draw on
a scaled display, or hold a phone.

## A. What the build servers have already proved

These are done, on the exact tree of the integration pull request, at
commit `21c29013dbfec5886dc34db1bd32c9abad77a407`. **The owner does not
have to do any of them.**

| What | Result | Where |
| --- | --- | --- |
| The desktop test suite on Ubuntu | **1071 passed, 9 skipped** | [run 44427139746](https://github.com/mihran94/JARVIS-AI/actions/runs/44427139746) |
| The desktop test suite on Windows | **1067 passed, 13 skipped** | [run 44427139746](https://github.com/mihran94/JARVIS-AI/actions/runs/44427139746) |
| The same suite on Linux, run by hand | **1075 passed, 5 skipped** | the tree of this branch |
| The source integrity manifest | matches the tree | `python scripts/source_manifest.py --check`, **after** `python iphone-pwa/icons/restore-icons.py` |
| The Windows application | built with PyInstaller | [run 44427139768](https://github.com/mihran94/JARVIS-AI/actions/runs/44427139768) |
| The Windows installer | built, Inno Setup reports **Successful compile** | the same run |
| The Windows installer artefact | `JARVIS-unified-windows-unsigned-21c29013dbfec5886dc34db1bd32c9abad77a407` | download it from the run above |
| The Android unit tests | **46 tests, 0 failures, 0 errors** | `:core:common:test`, `:core:windows:testDebugUnitTest`, `:feature:command:testDebugUnitTest` |
| The Android debug APK | built and audited | see below |
| The workflow patches | all five apply to this tree, in order | `git apply --check` |

The PWA icons are pictures, and the repository carries only their base64
copies. **`python iphone-pwa/icons/restore-icons.py` has to be run first**,
or the integrity check reports three files as missing and the served page has
no icons and no offline shell.

The Android APK built from this tree asks for `INTERNET`,
`ACCESS_NETWORK_STATE` and `USE_BIOMETRIC`, and for none of the
permissions the workflow forbids. It has no background component other
than the launcher. Its SHA-256 is
`9e0431ab64285162e9b69615774620b011717f85df361904ffe0894ab1971e19`.

**What the servers did not do.** The Android application was not built by
the workflow, because `android-integration.yml` has no `pull_request`
trigger and the patch that adds one is not applied yet. It was built by
hand here instead, with the same tasks the workflow runs.

## B. What only the owner can answer

Nothing below can be proven from a build server. Each line needs a
person, a real machine and, in some cases, a real phone.

| What | Why a server cannot answer it |
| --- | --- |
| The microphone, the Tamil speech input and the spoken reply | a runner has no microphone and no speaker |
| The interface at 125 %, 150 % and 200 % scaling | a runner has one screen at one size |
| The Tamil text in the interface on a real display | a runner has no font that shows it as a person does |
| The Android pairing, a remote job, the revocation and the reconnection | a runner cannot hold a phone |
| The certificate refusal on a real phone | the phone has to be the one that was told to refuse |
| The global hotkey pressed in another application | a runner has no other application and no keyboard |
| Install, launch, restart and uninstall of the Windows installer | a runner cannot install a program on a desktop |
| The signed release | a signing key is not in the repository |

The numbered list below is the detailed form of this table, in the order
the work was done. Answer each line **yes** or **no**, and say which one
could not be answered and why.

**Order.** The stack is fourteen branches and each one builds on the one
before it, so they are merged in order. The checklist is written in the
same order. Section 0a says how to merge them in one command.

| # | Phase | Pull request | Branch |
| --- | --- | --- | --- |
| 1 | P0 — the failing tests and three real defects | #44 | `fix/p0-ci-stability-20261118` |
| 2 | P1 — the conversation memory | #46 | `feature/p1-conversation-memory-20261118` |
| 3 | P2 — what a request costs | #47 | `feature/p2-cost-visibility-20261118` |
| 4 | P3 — reading documents | #49 | `feature/p3-document-intelligence-20261118` |
| 5 | P4 — the bridge certificate | #53 | `feature/phone-bridge-trust-20261118` |
| 6 | P5 — the visible task plan | #54 | `feature/p5-task-plan-20261118` |
| 7 | P6 — the project inspection | #55 | `feature/p6-developer-inspection-20261118` |
| 8 | P7 — the voice | #56 | `feature/p7-voice-local-commands-20261118` |
| 9 | P8 — the approval boundary | #58 | `feature/p8-safe-control-20261118` |
| 10 | P9 — the document search | #59 | `feature/p9-document-search-20261118` |
| 11 | P10 — reading a page | #60 | `feature/p10-web-research-20261118` |
| 12 | P11 — the certificate is pinned on the phone | #61 | `feature/bridge-certificate-pinning-20261118` |
| 13 | P12 — the key that brings JARVIS up | #62 | `feature/p12-global-hotkey-20261118` |
| 14 | P13 — the workflow, and one command to merge the stack | #63 | `feature/p13-workflow-20261119` |

---

## 0. Five patches, before anything else

The GitHub App that pushes this repository cannot write
`.github/workflows/`, so some workflow changes travel as patches. Apply
them once, before you merge:

```
git apply patches/github-actions-green.patch
git apply patches/ci-libegl-failfast.patch
git apply patches/windows-app-icon.patch
git apply patches/ci-stack-verification.patch
git apply patches/android-debug-apk.patch
```

* `github-actions-green.patch` turns off `fail-fast`, so a Linux only
  failure never hides the Windows result.
* `ci-libegl-failfast.patch` gives the Linux runner the Qt runtime
  libraries it needs, so the suite can import PySide6 at all. It used
  to add the `fail-fast` setting as well, with the very same lines that
  `github-actions-green.patch` adds, so the two could not both be
  applied. They now carry different halves of the same change.
* `windows-app-icon.patch` gives the application its own icon: the build
  draws the orb the desktop draws, the executable is built with it, and
  the installer uses it. The three parts travel together on purpose: the
  installer must not point at an icon that is not there, because the
  Windows installer job fails on a file it cannot find.
* `ci-stack-verification.patch` makes the CI check the work while it is
  still a pull request. The Windows installer is built for a pull
  request to **any** branch, because the work arrives as a stack of
  branches and each one of them is a pull request to the branch below
  it.
* `android-debug-apk.patch` carries the Android build for the phone
  client into the repository that holds it.

Check that all five applied:

```
git apply --check --reverse patches/github-actions-green.patch
git apply --check --reverse patches/ci-libegl-failfast.patch
git apply --check --reverse patches/windows-app-icon.patch
git apply --check --reverse patches/ci-stack-verification.patch
git apply --check --reverse patches/android-debug-apk.patch
```

They are checked by `tests/test_workflow_patches.py` on every run, so a
patch that stops applying is caught before the owner meets it.

## 0a. Merging the stack, in one command

The thirteen branches were pushed through an API that cannot rewrite
history, so they do not sit on one another's commits. Merging them one
by one leaves a conflict in `docs/SOURCE_INTEGRITY.sha256`, because that
file is written for the tree of one branch and two different trees give
two different files. The script does the whole thing and checks the
result:

```
git fetch origin
python scripts/merge_stack.py --out merged/jarvis-prime
git checkout merged/jarvis-prime
python -m pytest -q
```

The script merges the branches in order, writes the manifest again for
each merged tree, and stops and says so if it meets a conflict it does
not know rather than choosing for the owner. It keeps the application
icon, which the first branch carries and the later ones do not.

If you merge by hand instead, the only conflict you should meet is the
manifest, and the answer is always the same: write it again with
`python scripts/source_manifest.py` and add it.

## 1. The installer (Phase 11)

1. Download the `JARVIS-unified-windows-unsigned-<sha>` artefact from the
   Windows installer run of the branch you are merging.
2. Run `JarvisAI-Setup-Windows-x64.exe`. It is **unsigned**, so Windows
   will say so; that is expected and it is not a defect.
3. Confirm a Start menu entry and an optional desktop shortcut.
4. Start JARVIS. Confirm the window opens, the orb animates, and there is
   **no console window** left behind.
5. Close it. Confirm the user data folder holds the chat history and the
   saved projects, and that **no API key** is in it. The key must be in
   Windows Credential Manager only.
6. Install again over the top. Confirm the chat history and the saved
   projects are still there.
7. Uninstall. Confirm the application is gone. **Confirm the user data
   folder is still there** unless you deleted it yourself — an uninstall
   must not silently throw the history away.
8. Reinstall. Confirm the history came back.

## 2. The interface (Phase 1)

9. Choose the light theme in Settings, close the window, open it again.
   Confirm the light theme is still chosen.
10. Choose the dark theme. Confirm the Island, the Settings page and the
    Chat all use it.
11. Set Windows to **125%**, **150%** and **200%** scaling in turn.
    Confirm at each one: no clipped text, no overlapping controls, the
    composer still visible at the bottom, and the chat still scrolls.
12. Make the window narrow. Confirm nothing scrolls sideways.
13. Plug in a second screen. Move the window between them. Confirm the
    Island stays where you put it and does not appear on both screens.
14. Type Tamil in the chat. Confirm the letters are joined and readable,
    not split apart.

## 3. The local questions (Phase 8)

15. Type `Jarvis, enna help pannuva?`. Confirm the answer names the
    provider, the microphone permission and what is **not** verified, and
    that no provider request was made (no usage row appears).
16. Repeat in English, in French, and in plain Tamil. Same answer.
17. Say it out loud with the microphone on. Same answer, and it is spoken
    back if you have turned on *read replies aloud*.
18. Ask `what time is it`. Confirm the local clock, not a model.
19. Ask `help me fix my project`. Confirm this one **goes to the model**
    and is not answered locally — the local matcher must not swallow a
    real request.

## 4. The microphone (Phase 8)

20. Turn the microphone on. Confirm the HUD says **LISTENING** and that
    it really says that while the microphone is open.
21. Say a wake phrase and a request. Confirm the request is drafted and
    **not sent** on its own.
22. Say the wake phrase twice quickly. Confirm only one request is
    drafted.
23. Let JARVIS speak, and let the microphone hear itself. Confirm the
    echo is ignored and is not treated as your request.
24. Press **Emergency Stop** while it is listening. Confirm the
    microphone is released and the HUD says **STOPPED**. Press Resume.
    Confirm the old request does **not** come back.

## 5. The documents (Phases 6 and P9)

25. Open a **PDF** with text in it. Confirm the text is shown and the
    page count is right. Confirm a PDF whose pages are pictures says
    *"this PDF has no text layer"* and does not pretend the page is empty.
26. Open a **password-protected** PDF. Confirm it is refused and the
    reason is given.
27. Open a **DOCX with a table**. Confirm the cells are separated and
    not run together.
28. Open a file that is not text. Confirm it is refused.
29. Choose a folder, press **Search a folder…**, and search for a word
    you know is in one of the files. Confirm the file and the line are
    named. Confirm **no usage row** appeared — the search is local.
30. Press **Summarise in chat**. Confirm the text lands in the composer
    and is **not** sent until you press *Ask JARVIS*.
31. Press **Export the summary…**. Open the saved file. Confirm it holds
    what the assistant said, with a date, and nothing invented.
32. Compare two documents. Confirm the comparison names the lines only in
    the first, only in the second, and in both.

## 6. The folder tidier (Phase 9)

33. Make a folder with a few files of different kinds and one hidden
    file. Press **Tidy a folder…**. Confirm a **plan** is shown and
    **nothing has moved**.
34. Confirm the plan does not include the hidden file, and does not
    include anything that looks like a secret.
35. Say `tidy it` and approve. Confirm **only** the files in the plan
    moved, and that a file of an unknown kind stayed where it was.
36. Run the tidy again on a folder that already has a file of the same
    name in the target folder. Confirm nothing is overwritten and the
    report names the file it left alone.

## 7. The approval boundary (Phase 9)

37. On the **Windows Automation** page, confirm the *Approval boundary*
    panel is there.
38. Launch an app and decline it. Confirm the panel counts it as
    **refused**.
39. Launch an app and approve it. Confirm the panel counts it as
    **allowed**.
40. Start an action and press **Emergency Stop** before approving it.
    Confirm the panel says the approval was **thrown away** and not that
    you refused it.

## 8. The phone remote (Phases 4 and 10)

41. On the **Phone Remote** page, press **Create a private certificate**.
    Confirm a SHA-256 fingerprint appears.
42. Start the listener. Confirm the pairing code now carries that
    fingerprint.
43. Pair the Android phone. Confirm it connects and the chat works.
44. Revoke the phone. Confirm it is refused on its next request.
45. Turn the phone's network off and on. Confirm it reconnects.
46. Read a page with **Research a page**. Confirm the answer comes from
    that page. Confirm a page inside your own network is **refused**.

### The certificate is pinned on the phone (Phase 10)

47. On the **Phone Remote** page, press **Create a private certificate**
    and then **Show the pairing code**. Copy the whole code.
48. On the phone, in the **Windows JARVIS** card, paste the **whole code**
    into the pairing field. Confirm the address, the secret and the
    fingerprint are all read out of it.
49. Confirm the phone says the certificate **is pinned**.
50. Pair the phone. Confirm it connects.
51. Now change the certificate on the desktop: press **Create a private
    certificate** again and restart the listener. Confirm the phone is
    **refused**, and that the refusal is not a silent hang.
52. Pair a second phone with the **bare secret** instead of the whole
    code. Confirm the phone says **no certificate was pinned** rather
    than claiming a pinned connection.
53. Unpair the phone. Confirm the certificate goes with the secret: pair
    again and the phone is refused until it is paired with the code
    again.

Steps 47 to 53 are the checks for the certificate pinning. They need a
real phone and a desktop on the same network. The rules behind them are
tested without a phone (`CertificatePinTest` and `PairingCodeTest` in
`android/core/common`), but a phone that is told to refuse a certificate
is only really proved by a phone that refuses one.

### The key that brings JARVIS up (Phase 12)

54. Open **Settings**. Find **Key that brings JARVIS up**. Write
    `Ctrl+Alt+Space` and press **Apply**. Confirm the line under it says
    the key is ready.
55. Switch to another application, for example the browser. Press the
    key. Confirm JARVIS comes to the front.
56. Confirm the microphone did **not** open. The key brings JARVIS up
    and nothing else.
57. Write `Ctrl+Alt+Del` and press **Apply**. Confirm the application
    refuses it and says the key belongs to Windows.
58. Write `Ctrl+T` and press **Apply**. Confirm it is accepted and that
    the owner is told other applications use that key.
59. Restart JARVIS. Confirm the key still works without setting it
    again.

Steps 54 to 59 need a real Windows desktop session. The rules behind
them are tested on any machine (`tests/test_global_hotkey.py`), and the
test that takes a key from Windows runs on the Windows runner of the
workflow. On Linux and macOS the shortcut is saved and shown, and the
application says that it does nothing there.

## 9. The developer flow (Phases 5 and 7)

62. Point JARVIS at a project with a broken Python file. Confirm the
    card names the file and the line **before** anything is changed.
63. Let it make a change. Confirm it happened in a **worktree** and that
    your own working folder, including uncommitted work, is untouched.
64. Run the tests. Confirm the **actual** result is shown, including a
    failure as a failure.
65. Press **Review diff**. Confirm it is a real diff.
66. Press **Accept the change**. Confirm it is recorded and that nothing
    was written into your project folder.
67. Press **Reject the change** on the next one. Confirm the worktree is
    still there to read and your project is untouched.

## 10. The plan (Phase 7)

68. Run a plan of two steps. Confirm the card names each step and its
    **real state**: pending, waiting for approval, running, verified.
69. Confirm there is **no percentage** anywhere on the card.
70. Make a step fail. Confirm the steps that already succeeded are not
    run again when you retry the failed step.

## 11. The cost (Phase 2)

71. Send a message. Open **System & Usage**. Confirm there is an
    **estimated cost** column and an estimated total.
72. Confirm a model with no known price says **price unknown** and not
    zero.

## What is deliberately not there

Say so plainly if you are asked:

- **No OCR.** A PDF whose pages are pictures is not read. It says so.
- **No screen capture.** It needs a real permission flow and a capture
  indicator that can only be trusted on a real screen.
- **The Android app does not pin the certificate yet.** The fingerprint
  travels in the pairing code and the desktop shows it, but the phone
  does not enforce it yet. That work needs a real device.
- **No signed installer.** The one that is built is unsigned and says so.
- **The voice engine is the Windows one.** Whisper and Piper are listed
  under *not yet verified* because they are not installed.

## What to record

For every line: the answer, the date, and the Windows build. If a line
cannot be answered, say which one and why. A checklist that is partly
answered is worth more than one that claims everything passed.
