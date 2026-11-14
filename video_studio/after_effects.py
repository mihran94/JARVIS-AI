"""Render one explicitly selected After Effects composition using Adobe aerender."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from video_studio.preview import run_media_command


def after_effects_render(executable, project, composition, template, output, check_cancelled):
    executable, project = (Path(path).resolve(strict=True) for path in (executable, project))
    output = Path(output).resolve()
    composition, template = composition.strip(), template.strip()
    if executable.name.casefold() != "aerender.exe" or not executable.is_file():
        raise ValueError("Choose Adobe's aerender.exe from the After Effects Support Files folder.")
    if project.suffix.lower() != ".aep" or not project.is_file():
        raise ValueError("Choose an After Effects .aep project.")
    if not composition or not template:
        raise ValueError("Enter the exact composition and After Effects output module template names.")
    if output.suffix.lower() not in {".mp4", ".mov", ".avi"} or any(c in output.name for c in "[]"):
        raise ValueError("Choose one MP4, MOV or AVI file matching the output module template.")
    # Render outside the destination filename so a cancelled render preserves an existing file.
    with TemporaryDirectory(prefix=".jarvis-aerender-", dir=output.parent) as directory:
        staged = Path(directory) / ("render" + output.suffix)
        run_media_command(
            [str(executable), "-project", str(project), "-comp", composition,
             "-OMtemplate", template, "-output", str(staged),
             "-close", "DO_NOT_SAVE_CHANGES"],
            directory, check_cancelled, windows_tree=True,
        )
        if not staged.is_file() or not staged.stat().st_size:
            raise ValueError("After Effects produced no movie. Check the template and output extension.")
        check_cancelled()
        os.replace(staged, output)
    return output
