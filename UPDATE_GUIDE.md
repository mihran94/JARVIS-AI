# Jarvis-Blue Updates

## Available in this development package
Open the gear/settings drawer → Updates.
- Current source version: 0.1.0 (development baseline, not a published release).
- Notify Only (default): checks once 15 seconds after startup when a feed is configured; never downloads or installs automatically.
- Off: disables the startup check; manual checks remain available.
- Save: stores the HTTPS feed address and preference through config_manager.
- Check for Updates: loads version and release notes from the configured feed.
- Download: downloads a newer source release, checks SHA-256 and validates archive paths and size.
- Install & Restart: asks to stop tasks, starts an independent updater, waits for Jarvis to exit, backs up replaced files, installs, and starts main.py with the same Python interpreter.
- Update History: shows successful installs and restores.
- Restore Previous Version: restores the last backup and restarts, preserving current user settings and data.

No feed is preconfigured because the project's publication repository/URL has not been established in this task. The UI displays this explicitly. This package cannot find future releases until a real feed is configured and a newer compatible release is published. Private repositories requiring authentication are not supported yet; do not paste tokens into URLs.

## Publishing future source updates
The release maintainer runs `python tools/prepare_source_release.py 0.2.0 https://YOUR-HOST/Jarvis-Blue-0.2.0.zip` only when preparing an authorized release. Replace the version and URL with the actual release values. Review the generated archive and edit latest.json release notes. Publish the ZIP at its declared URL and publish latest.json at a stable HTTPS address. Set that stable address in Settings → Updates. Never publish config/api_keys.json, user memory, logs or environments.

Manifest fields: `format` = `jarvis-blue-source-v1`, numeric `version` = `major.minor.patch`, `url` = HTTPS ZIP URL, `sha256` = SHA-256 of that ZIP, `notes` = plain text. ZIP entries must start directly with main.py, ui.py, core/, etc., without a wrapping project folder. Release only trusted project code/plugins. Preserve upstream attribution and license.

## Limits and recovery
This is a source updater, not a Windows EXE/MSI installer. Packaged-app installation is refused. Existing dependencies must satisfy the release; the updater never runs pip or setup.py. Releases requiring dependency changes or data migrations need a separate reviewed installer/migration flow. File removal is not supported: releases overlay managed code, and deleted upstream files need an explicit future migration. A file-copy error triggers rollback, but abrupt power loss and a successful copy followed by an application startup failure are not automatically recovered. Use Restore Previous Version if the UI opens. If it cannot open, after closing Jarvis run `python -c "from pathlib import Path; from core.updater import restore; restore(Path.cwd())"` from the app directory; then run main.py. Diagnostics: .updates/updater.log.

Settings, JSON databases, secrets and the virtual environment are not included in update backups. Existing custom plugins with the same filename as a release plugin can be overwritten and are included in that update's backup. Do not run multiple instances or move the app directory while updating. Enough disk space is required for download, staging and backup. A backup can be restored once; the next update replaces it.

HTTPS plus SHA-256 detects download corruption; it is not an independent publisher signature. Trust and secure the feed's hosting account. Signed manifests, unattended installation, dependency migration, installer support, startup health checks and periodic checks are future work.

## Validation for this change
Six isolated updater tests pass: install/restore with private-data preservation, checksum rejection, unsafe/private-path rejection, simulated copy failure rollback, manifest/version validation and symlink rejection. All Python source parses. No real feed was contacted, no release was published and no build was run. PyQt6 is unavailable in this environment, so dialog rendering, app shutdown/restart, Windows process waiting and the Windows GUI still require target-machine testing.
