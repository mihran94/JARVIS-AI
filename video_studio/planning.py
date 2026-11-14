"""Build and validate an editable 30-second cinematic production plan."""
import json
import re

DURATION_MS = 30_000
_MAX_BRIEF = 4000
_VOICE_PREFIX = re.compile(
    r"^(?:video editor|cinematic reel|வீடியோ எடிட்டர்|சினிமாட்டிக் ரீல்)"
    r"(?:\s*[:：,–-]\s*|\s+)(?P<brief>\S.*)$", re.IGNORECASE | re.DOTALL
)
_SHOT_FIELDS = {
    "end_ms": 0,
    "tamil_voiceover": 300,
    "english_subtitle": 84,
    "visual": 350,
    "flow_prompt": 950,
    "edit_and_sound": 350,
}


def spoken_brief(text):
    """Recognize an explicit mode prefix without intercepting ordinary chat."""
    match = _VOICE_PREFIX.fullmatch(text.strip())
    return match["brief"] if match else None


def planning_messages(brief):
    brief = brief.strip()
    if not brief or len(brief) > _MAX_BRIEF:
        raise ValueError('Enter a video brief with 1–4000 characters.')
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
                "shots. Specify reference use, composition, camera movement, lighting and one main "
                "action per English Google Flow clip prompt. For an existing clip, write an edit "
                "prompt describing changes to that clip and what must be preserved. Distinguish "
                "generated clip length from its final timeline length; place trim and assembly "
                "directions in edit_and_sound. Keep this channel focused on documented "
                "human events. Label proposed historical reconstructions 'AI reenactment'. "
                "Flag historical claims that require verification in verification_notes and do "
                "not invent citations, sources or facts. For a missing topic, plan with explicit "
                "placeholders. Finish with the small M logo if requested. "
                "Return one JSON object with exactly title, verification_notes and shots. "
                "title is a short string and verification_notes is a string. shots is an array of "
                "4 to 8 objects, each with exactly end_ms (integer), tamil_voiceover, "
                "english_subtitle (no more than 84 characters), visual, flow_prompt, "
                "and edit_and_sound (all strings). Shot starts are implicit (0, then previous "
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
    """Normalize model output before displaying it or exporting an SRT file."""
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
    for shot in shots:
        if not isinstance(shot, dict) or set(shot) != set(_SHOT_FIELDS):
            raise ValueError('A shot is missing required fields.')
        end = shot["end_ms"]
        if type(end) is not int or not start + 1500 <= end <= DURATION_MS:
            raise ValueError('Shot times must increase in steps of at least 1.5 seconds.')
        fields = {
            name: _text(shot[name], maximum, optional=name in ("tamil_voiceover", "english_subtitle"))
            for name, maximum in _SHOT_FIELDS.items() if name != "end_ms"
        }
        if bool(fields["tamil_voiceover"]) != bool(fields["english_subtitle"]):
            raise ValueError('Each spoken shot needs both Tamil voiceover and an English caption.')
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
    }


def plan_json(plan):
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _timecode(milliseconds):
    seconds, remainder = divmod(milliseconds, 1000)
    return f"00:00:{seconds:02},{remainder:03}"


def flow_instructions(plan):
    lines = [plan["title"], "30 seconds · 1080 × 1920 · Google Flow",
             "Verification: " + (plan["verification_notes"] or "Review historical details.")]
    for number, shot in enumerate(plan["shots"], 1):
        start, end = _timecode(shot["start_ms"]), _timecode(shot["end_ms"])
        lines.extend([
            "", f"Shot {number}  |  {start} → {end}",
            "Visual: " + shot["visual"],
            "Flow prompt: " + shot["flow_prompt"],
            "Edit and sound: " + shot["edit_and_sound"],
        ])
        if shot["tamil_voiceover"]:
            lines.extend(["Tamil: " + shot["tamil_voiceover"],
                          "English: " + shot["english_subtitle"]])
    return "\n".join(lines)


def english_srt(plan):
    cues = []
    for shot in plan["shots"]:
        caption = shot["english_subtitle"]
        if caption:
            start, end = _timecode(shot["start_ms"]), _timecode(shot["end_ms"])
            cues.append(f"{len(cues) + 1}\n{start} --> {end}\n{caption}")
    return "\n\n".join(cues) + "\n"
