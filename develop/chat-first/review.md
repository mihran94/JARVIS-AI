# JARVIS Chat-first desktop

Status: Ready for review on `development`.

## Using the chat screen

- The app opens to Chat. **Tools** reveals the sidebar and **Chat** returns to the conversation.
- **Settings & Plugins** holds per-tool switches and executable setup for CapCut,
  DaVinci Resolve, and After Effects. Select each installed Windows EXE before launching it.
- Type `CapCut open pannu`, `Open DaVinci`, `Open After Effects`, `Open Google Flow`, or
  `Open Higgsfield` in Chat. JARVIS displays the destination and an inline
  **Approve / Decline** row. A launch result appears in the transcript.
- Type `/video` followed by a brief and press **Ask JARVIS**. Gemini returns the shot plan
  to Chat and the same plan remains available in Video Editor for browser handoff and export.
  Hands-free local dictation leaves the command in the composer for explicit submission.
- Emergency Stop cancels a pending chat launch. App and browser launches use one-time approval.

## Review and test

Main baseline: `954af152a263da7ece11b57f7c7ec3579e1663e6`.

Apply `develop/video-editing-studio/changes.patch` from development commit
`a6655b2bfd852b31ea081bb7f920cc650b77db3e` first. Apply this patch second and
regenerate `docs/SOURCE_INTEGRITY.sha256`. Both patches were applied in sequence
and matched the tested source tree.

29 targeted desktop tests passed. Browser opens, Windows executable launches,
and Gemini responses used test doubles. Installed Windows apps and live video
generation still need a PC acceptance check. This update opens the tools.
Editor actions inside those tools are a separate integration.
