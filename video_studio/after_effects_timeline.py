"""Generate a fixed After Effects script from a shot plan and selected media."""
import json
from pathlib import Path

from video_studio.planning import DURATION_MS
from video_studio.preview import AUDIO_EXTENSIONS, CLIP_EXTENSIONS, local_media_path


def timeline_script(plan, clips, narration=None):
    if len(clips) != len(plan["shots"]):
        raise ValueError("Select one clip per shot.")
    data = {
        "title": "JARVIS – " + plan["title"],
        "duration": DURATION_MS / 1000,
        "shots": [
            {"path": local_media_path(path, CLIP_EXTENSIONS).as_posix(),
             "start": shot["start_ms"] / 1000, "end": shot["end_ms"] / 1000,
             "caption": shot["english_subtitle"]}
            for path, shot in zip(clips, plan["shots"])
        ],
        "narration": local_media_path(narration, AUDIO_EXTENSIONS).as_posix() if narration else None,
    }
    return "(function (data) {\n" + _TIMELINE + "\n}(" + json.dumps(data, ensure_ascii=True) + "));\n"


def timeline_executable(path):
    executable = Path(path).resolve(strict=True)
    if not executable.is_file() or executable.name.casefold() != "afterfx.exe":
        raise ValueError("Select Adobe's installed AfterFX.exe.")
    return executable


_TIMELINE = """
    var imported = [];
    var comp = null;

    function importMedia(path) {
        var file = new File(path);
        if (!file.exists) throw new Error("Media is missing: " + path);
        var options = new ImportOptions(file);
        options.sequence = false;
        var item = app.project.importFile(options);
        imported.push(item);
        return item;
    }

    app.beginUndoGroup("Build JARVIS timeline");
    try {
        var index, shot, footage, layer, scale, caption, source, style;
        comp = app.project.items.addComp(data.title, 1080, 1920, 1, data.duration, 30);
        for (index = 0; index < data.shots.length; index++) {
            shot = data.shots[index];
            footage = importMedia(shot.path);
            if (!footage.hasVideo || footage.duration <= 0) {
                throw new Error("Shot " + (index + 1) + " must contain playable video.");
            }
            layer = comp.layers.add(footage);
            layer.name = "Shot " + (index + 1);
            layer.startTime = shot.start;
            layer.inPoint = shot.start;
            layer.outPoint = Math.min(shot.end, shot.start + footage.duration);
            scale = Math.min(1080 / footage.width, 1920 / footage.height) * 100;
            layer.property("ADBE Transform Group").property("ADBE Scale").setValue([scale, scale]);
            if (data.narration && layer.hasAudio) {
                layer.property("ADBE Audio Group").property("ADBE Audio Levels").setValue([-14, -14]);
            }
        }
        for (index = 0; index < data.shots.length; index++) {
            shot = data.shots[index];
            if (!shot.caption) continue;
            caption = comp.layers.addBoxText([900, 165]);
            caption.name = "English caption " + (index + 1);
            caption.inPoint = shot.start;
            caption.outPoint = shot.end;
            caption.property("ADBE Transform Group").property("ADBE Position").setValue([90, 1560]);
            source = caption.property("ADBE Text Properties").property("ADBE Text Document");
            style = source.value;
            style.text = shot.caption;
            style.fontSize = 52;
            style.justification = ParagraphJustification.CENTER_JUSTIFY;
            style.applyFill = true;
            style.fillColor = [1, 1, 1];
            style.applyStroke = true;
            style.strokeColor = [0, 0, 0];
            style.strokeWidth = 3;
            source.setValue(style);
        }
        if (data.narration) {
            footage = importMedia(data.narration);
            if (!footage.hasAudio || footage.duration <= 0) throw new Error("Narration needs playable audio.");
            layer = comp.layers.add(footage);
            layer.name = "Tamil narration";
            layer.startTime = 0;
            layer.inPoint = 0;
            layer.outPoint = Math.min(data.duration, footage.duration);
        }
        comp.openInViewer();
    } catch (error) {
        if (comp) comp.remove();
        for (var cleanup = imported.length - 1; cleanup >= 0; cleanup--) imported[cleanup].remove();
        alert("JARVIS timeline could not be created. " + error.toString());
    } finally {
        app.endUndoGroup();
    }
"""
