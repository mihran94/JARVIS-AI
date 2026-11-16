# JARVIS AI section development

MiniMax submits one JARVIS section at a time in this folder on the GitHub
`development` branch. Use the current `main` as the source baseline.

```text
develop/<section-slug>/
  changes.patch
  review.md
  preview/       # Optional export from Google AI Studio
```

Develop and test the proposed code in a separate local worktree based on
`main`. Export the tested changes as a Git patch relative to that worktree's
baseline. If the worktree contains changes that have not been committed, stage
the intended files there before running `git diff --cached --binary > changes.patch`.
Include the baseline commit SHA in `review.md` so the reviewer can reproduce the
patch. Keep runtime code in its existing paths when applying the patch for review.

Record the section goal, changed files, tests and results, setup steps, and any
functions that still use simulated data. Store the optional AI Studio preview
without API keys, tokens, real customer data, or machine-specific settings.

On the `development` branch, add the submission to its section folder, refresh
`docs/SOURCE_INTEGRITY.sha256` using `python scripts/source_manifest.py`, and
verify it with `python scripts/source_manifest.py --check`. Push the submission
to `development`. Add `[skip ci]` to the commit message for this review workflow.
Leave `main` and releases for the owner's approval. The approved patch is applied
to the shared JARVIS source through the normal review and merge process.

Suggested section folders

- `ai-brain-voice`
- `video-editing-studio`
- `business-studio`
- `mobile-camera-iot`
- `pc-control-automation`
- `coding-updates`
- `tamil-news`
