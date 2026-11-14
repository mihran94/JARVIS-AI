import json

import pytest

from video_studio.after_effects_timeline import timeline_script


def test_timeline_script_keeps_manual_media_and_caption_as_data(tmp_path):
    clip = tmp_path / "Shot 01.mov"
    narration = tmp_path / "Tamil voice.wav"
    clip.touch()
    narration.touch()
    caption = '"}); app.project.close(); //'
    plan = {"title": "தமிழ்", "shots": [
        {"start_ms": 0, "end_ms": 1250, "english_subtitle": caption},
    ]}
    script = timeline_script(plan, [clip], narration)
    code, payload = script.rsplit("\n}(", 1)
    data = json.loads(payload.removesuffix("));\n"))
    assert data["shots"] == [{"path": clip.as_posix(), "start": 0, "end": 1.25, "caption": caption}]
    assert data["narration"] == narration.as_posix()
    assert data["duration"] == 30
    assert "app.project.close" not in code
    assert "addComp(data.title, 1080, 1920" in code
    with pytest.raises(ValueError, match="one clip per shot"):
        timeline_script(plan, [])
