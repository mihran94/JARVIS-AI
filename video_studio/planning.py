"""Build and validate an editable 30-second cinematic production plan.

WHAT A PLAN IS
    One Tamil brief becomes one shot list. Each shot carries its duration, the
    camera movement, the lighting, the sound cues, the Tamil voiceover and the
    English subtitle, plus a copy-ready prompt for Google Flow AND a copy-ready
    prompt for Higgsfield.

WHY TWO PROMPTS PER SHOT
    The two engines want the same shot described differently. Higgsfield wants
    subject action, then setting and lighting, then ONE camera move, then mood.
    Google Flow wants reference use, composition, camera movement, lighting and
    one main action. Asking for one prompt and then regenerating for the other
    engine means two model calls and two chances for the story to drift.

    So the plan carries both prompts for every shot, written once, from the
    same brief. The owner copies whichever one they need.

    An older plan that has only one prompt still parses and still renders. The
    missing half is filled in from the prompt that IS there, and the plan is
    marked as partial so the interface can say so instead of pretending.
"""
import json
import re

DURATION_MS = 30_000
VIDEO_TOOLS = {
    "Google Flow": ("https://flow.google.com/", "flow_prompt"),
    "Higgsfield": ("https://higgsfield.ai/ai-video", "higgsfield_prompt"),
}
VIDEO_ENGINES = tuple(VIDEO_TOOLS)
_MAX_BRIEF = 4000
_VOICE_PREFIX = re.compile(
    r"^(?:video editor|cinematic reel|வீடியோ எடிட்டர்|சினிமாட்டிக் ரீல்)"
    r"(?:\s*[:：,–-]\s*|\s+)(?P<brief>\S.*)$", re.IGNORECASE | re.DOTALL
)

#: The fields every shot must carry.
_REQUIRED_SHOT_FIELDS = {
    "end_ms": 0,
    "tamil_voiceover": 300,
    "english_subtitle": 84,
    "visual": 350,
    "flow_prompt": 950,
    "edit_and_sound": 350,
}

#: The fields that make a shot list a cinematic shot list rather than a
#: summary. A plan that arrives without them is still usable, and is marked
#: partial rather than rejected.
_OPTIONAL_SHOT_FIELDS = {
    "camera": 200,
    "lighting": 200,
    "sound": 200,
    "higgsfield_prompt": 950,
}

_SHOT_FIELDS = {**_REQUIRED_SHOT_FIELDS, **_OPTIONAL_SHOT_FIELDS}

#: What the interface shows when the model did not supply a field.
NOT_SPECIFIED = "(not specified)"


def spoken_brief(text):
    """Recognize an explicit mode prefix without intercepting ordinary chat."""
    match = _VOICE_PREFIX.fullmatch(text.strip())
    return match["brief"] if match else None


def suggest_workflow(brief, engine):
    """Return local workflow suggestions based on the chosen engine and brief."""
    text = brief.casefold()
    steps = ["Use Generate with Gemini for the shot plan, Tamil narration draft and English captions."]
    if engine == "Higgsfield":
        steps.append("Use Higgsfield for the planned clips. Start with the most important shot to check the look and motion.")
    else:
        steps.append("Use Google Flow for the main set of clips.")
        if re.search(r"\b(?:higgsfield|close[ -]?up|dolly|orbit|camera move|face reference)\b|முகம்", text):
            steps.append("Try Higgsfield for the close-up or key camera move. Reuse the same reference image for continuity.")
    if re.search(r"\b(?:logo|vfx|composit(?:e|ing)|motion graphics|after effects)\b|லோகோ", text):
        steps.append("Use After Effects for the logo animation or effects shot, then bring that clip into the edit.")
    steps.append("Assemble the 1080 × 1920 preview in JARVIS and check narration and caption timing.")
    steps.append("Copy the editing checklist. It lists every shot with its length, camera, lighting, sound cue and English subtitle.")
    if not re.search(r"\b(?:skip|no|without)\s+capcut\b|capcut\s+வேண்டாம்", text):
        steps.append("Use CapCut export if you want to fine-tune captions and audio. Import the MP4 and English SRT together.")
    if not re.search(r"\b(?:skip|no|without)\s+(?:davinci|resolve)\b", text):
        steps.append("Use DaVinci Resolve export for a timeline-grade edit. It hands over the MP4, the English SRT and the shot checklist.")
    return "\n\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1))


def planning_messages(brief, engine="Google Flow"):
    brief = brief.strip()
    if not brief or len(brief) > _MAX_BRIEF:
        raise ValueError('Enter a video brief with 1–4000 characters.')
    if engine not in VIDEO_ENGINES:
        raise ValueError("Choose a supported video engine.")
    clip_guidance = (
        "The primary engine for this plan is " + engine + ", and its prompt is the one to use "
        "first. For every shot, write BOTH engine prompts from the same shot, never from a "
        "different one. "
        "flow_prompt is a Google Flow prompt: reference use, composition, camera movement, "
        "lighting and one main action per clip prompt. "
        "higgsfield_prompt is a Higgsfield prompt: subject action, then setting and lighting, "
        "then ONE camera move, then mood. When a reference image is available, describe what "
        "to preserve. Put camera preset suggestions in edit_and_sound. For an existing clip, "
        "write an edit prompt describing changes to that clip and what must be preserved. "
    )
    return [
        {
            "role": "system",
            "content": (
                "You are the cinematic editor for AI Mystery World. Plan exactly 30 seconds "
                "in vertical 1080x1920. Use a strong opening and vary shot size, movement and "
                "pacing to fit the story. Keep faces and subtitles in the vertical safe area. "
                "Write natural spoken Tamil and matching concise English subtitles, with pauses "
                "and an intelligible dialogue mix. Use the presenter in the opening when the brief "
                "calls for it. Keep face, wardrobe, setting and lighting consistent across generated "
                "shots. " + clip_guidance + "Distinguish "
                "generated clip length from its final timeline length; place trim and assembly "
                "directions in edit_and_sound. Keep this channel focused on documented "
                "human events. Label proposed historical reconstructions 'AI reenactment'. "
                "Flag historical claims that require verification in verification_notes and do "
                "not invent citations, sources or facts. For a missing topic, plan with explicit "
                "placeholders. Finish with the small M logo if requested. "
                "Return one JSON object with exactly title, verification_notes and shots. "
                "title is a short string and verification_notes is a string. shots is an array of "
                "4 to 8 objects, each with exactly end_ms (integer), camera, lighting, sound, "
                "tamil_voiceover, english_subtitle (no more than 84 characters), visual, "
                "flow_prompt, higgsfield_prompt, and edit_and_sound (all strings). "
                "camera is the camera movement of the shot in a few words. lighting is the "
                "lighting of the shot in a few words. sound is the sound cue of the shot in a few "
                "words. Shot starts are implicit (0, then previous "
                "end_ms). Each shot is at least 1500 ms. Last end_ms is exactly 30000. "
                "Use empty voiceover and subtitle strings together for intentional silent shots."
            ),
        },
        {"role": "user", "content": brief},
    ]


def _text(value, maximum, *, optional=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError('A plan field has invalid text or exceeds its length limit.')
    clean = " ".join(value.split())
    if not clean and not optional:
        raise ValueError('A required plan field is empty.')
    return clean


def parse_plan(raw):
    """Normalize model output before displaying it or exporting an SRT file.

    A shot that carries every cinematic field produces a DETAILED plan. A shot
    that arrives without camera, lighting, sound or the second engine's prompt
    is still a usable plan, and it is marked partial so the interface can say
    what is missing instead of showing an empty column as if it were designed.
    """
    raw = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence[1]
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError('The local model did not return a valid JSON plan.') from exc
    if not isinstance(data, dict) or set(data) != {"title", "verification_notes", "shots"}:
        raise ValueError('The plan is missing its title, verification notes or shots.')
    shots = data["shots"]
    if not isinstance(shots, list) or not 4 <= len(shots) <= 8:
        raise ValueError('The plan must contain 4–8 shots.')
    start = 0
    timeline = []
    detailed = True
    for shot in shots:
        if not isinstance(shot, dict) or not _REQUIRED_SHOT_FIELDS.keys() <= set(shot):
            raise ValueError('A shot is missing required fields.')
        if not set(shot) <= set(_SHOT_FIELDS):
            raise ValueError('A shot carries a field the plan does not use.')
        end = shot["end_ms"]
        if type(end) is not int or not start + 1500 <= end <= DURATION_MS:
            raise ValueError('Shot times must increase in steps of at least 1.5 seconds.')
        fields = {}
        for name, maximum in _SHOT_FIELDS.items():
            if name == "end_ms":
                continue
            if name in _REQUIRED_SHOT_FIELDS:
                fields[name] = _text(
                    shot[name], maximum,
                    optional=name in ("tamil_voiceover", "english_subtitle"))
            else:
                # A field the model left out is empty, not an error. The plan
                # is marked partial and the interface says what is missing.
                fields[name] = _text(shot.get(name, ''), maximum, optional=True)
        if bool(fields["tamil_voiceover"]) != bool(fields["english_subtitle"]):
            raise ValueError('Each spoken shot needs both Tamil voiceover and an English caption.')
        if not all(fields[name] for name in _OPTIONAL_SHOT_FIELDS):
            detailed = False
        timeline.append({"start_ms": start, "end_ms": end, **fields})
        start = end
    if start != DURATION_MS or not any(shot["english_subtitle"] for shot in timeline):
        raise ValueError('The plan must end at 30 seconds and contain English subtitles.')
    return {
        "title": _text(data["title"], 120),
        "width": 1080,
        "height": 1920,
        "verification_notes": _text(data["verification_notes"], 1500, optional=True),
        "shots": timeline,
        "detailed": detailed,
    }


def plan_json(plan):
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _timecode(milliseconds):
    seconds, remainder = divmod(milliseconds, 1000)
    return f"00:00:{seconds:02},{remainder:03}"


def _seconds(milliseconds):
    """A shot length in seconds, with one decimal place."""
    return f"{milliseconds / 1000:.1f} s"


def _prompt_label(engine):
    return 'Higgsfield prompt' if engine == 'Higgsfield' else 'Flow prompt'


def _prompt_lines(shot, engine, *, show_label=True):
    _, field = VIDEO_TOOLS[engine]
    prompt = shot.get(field)
    if prompt:
        return [f"{_prompt_label(engine)}: {prompt}" if show_label else prompt]
    lines = [f"{_prompt_label(engine)}: {NOT_SPECIFIED}"]
    if engine == 'Higgsfield' and shot.get('flow_prompt'):
        lines.append(f"Google Flow fallback (adapt for Higgsfield): {shot['flow_prompt']}")
    return lines


def _value(shot, name):
    """A shot field, or an honest marker when the model did not supply it."""
    return shot.get(name) or NOT_SPECIFIED


def plan_engine(plan):
    """The engine this plan was generated for."""
    return plan.get("engine", "Google Flow")


def shot_list(plan):
    """The cinematic shot list: duration, camera, lighting, sound, subtitles."""
    engine = plan_engine(plan)
    lines = [plan["title"], f"30 seconds · 1080 × 1920 · {engine}"]
    if not plan.get("detailed", False):
        lines.append("PARTIAL PLAN — the model did not supply every cinematic field. "
                     "Missing fields are marked " + NOT_SPECIFIED + ".")
    lines.append("Verification: " + (plan["verification_notes"] or "Review historical details."))
    for number, shot in enumerate(plan["shots"], 1):
        start, end = _timecode(shot["start_ms"]), _timecode(shot["end_ms"])
        lines.extend([
            "",
            f"Shot {number}  |  {start} → {end}  |  {_seconds(shot['end_ms'] - shot['start_ms'])}",
            "Camera: " + _value(shot, "camera"),
            "Lighting: " + _value(shot, "lighting"),
            "Sound: " + _value(shot, "sound"),
            "Visual: " + shot["visual"],
            *_prompt_lines(shot, engine),
            "Edit and sound: " + shot["edit_and_sound"],
        ])
        if shot["tamil_voiceover"]:
            lines.extend(["Tamil: " + shot["tamil_voiceover"],
                          "English: " + shot["english_subtitle"]])
        else:
            lines.append("English: (intentional silent shot)")
    return "\n".join(lines)


def prompt_sheet(plan, engine="Google Flow"):
    """Show per-shot prompts and label any source-engine fallback."""
    label = _prompt_label(engine)
    lines = [f"{plan['title']} — {label}s for {engine}"]
    if not plan.get("detailed", False):
        lines.append("PARTIAL PLAN — some fields were not supplied by the model.")
    for number, shot in enumerate(plan["shots"], 1):
        lines.extend([
            "",
            f"Shot {number}  ({_seconds(shot['end_ms'] - shot['start_ms'])})",
            *_prompt_lines(shot, engine, show_label=False),
        ])
    return "\n".join(lines)


def flow_instructions(plan):
    """The shot list with the plan's own engine prompts.

    Kept for the callers that already use it; the shot list is the fuller
    version of the same thing.
    """
    return shot_list(plan)


def english_srt(plan):
    cues = []
    for shot in plan["shots"]:
        caption = shot["english_subtitle"]
        if caption:
            start, end = _timecode(shot["start_ms"]), _timecode(shot["end_ms"])
            cues.append(f"{len(cues) + 1}\n{start} --> {end}\n{caption}")
    return "\n\n".join(cues) + "\n"
