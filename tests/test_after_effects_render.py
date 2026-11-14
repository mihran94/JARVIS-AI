from pathlib import Path

import pytest

from security.policy import Stopped
from video_studio.after_effects import after_effects_render


def test_aerender_stages_movie_and_preserves_destination_on_cancel(tmp_path, monkeypatch):
    renderer = tmp_path / "aerender.exe"
    project = tmp_path / "My project.aep"
    output = tmp_path / "Final movie.mov"
    for path in (renderer, project):
        path.touch()
    output.write_bytes(b"previous movie")

    def run(args, directory, check, *, windows_tree):
        assert args[:7] == [str(renderer), "-project", str(project), "-comp",
                            "Intro & credits", "-OMtemplate", "Lossless"]
        assert args[-2:] == ["-close", "DO_NOT_SAVE_CHANGES"]
        target = Path(args[args.index("-output") + 1])
        assert target.parent == Path(directory)
        assert windows_tree
        target.write_bytes(b"new movie")
        assert output.read_bytes() == b"previous movie"

    monkeypatch.setattr("video_studio.after_effects.run_media_command", run)

    def cancelled():
        raise Stopped("Cancelled")

    with pytest.raises(Stopped):
        after_effects_render(renderer, project, "Intro & credits", "Lossless", output, cancelled)
    assert output.read_bytes() == b"previous movie"
    assert after_effects_render(
        renderer, project, "Intro & credits", "Lossless", output, lambda: None,
    ) == output
    assert output.read_bytes() == b"new movie"
    assert not list(tmp_path.glob(".jarvis-aerender-*"))
