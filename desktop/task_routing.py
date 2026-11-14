"""Recognize direct creative requests without starting tools or calling a model."""
import re

_ACTION = r"\b(?:make|create|build|generate|assemble|export|render|combine|stitch|draft|write|prepare|revise|update|pannu|sei|seiyu|tayaar)\b|பண்ணு|செய்|தயார்|உருவாக்கு|இணை|எழுது|மாற்று"
_QUESTION = re.compile(
    r"^(?:how|what|why|when|where|which|should|explain|compare|tell me|do not|don't)\b"
    r"|\b(?:can i|difference between|how to|without|vendam|never|not|publish|upload)\b|எப்படி|என்ன|வேண்டாம்",
    re.IGNORECASE,
)
_TARGETS = {
    "after_effects_timeline": r"\b(?:after effects|aftereffects)\b.*(?:\btimeline\b|டைம்லைன்)|(?:\btimeline\b|டைம்லைன்).*\b(?:after effects|aftereffects)\b",
    "mp4_preview": r"\bmp4\b|\b(?:join|combine|stitch|assemble)\b.*\bclips?\b|clips?.*இணை|கிளிப்களை.*இணை",
    "video_plan": r"\b(?:shot (?:plan|list)|video plan|cinematic reel|google flow prompts?|flow prompts?)\b|வீடியோ திட்டம்|சினிமாட்டிக் ரீல்",
    "fiverr_reply": r"\bfiverr\b.*(?:\b(?:reply|respond|message)\b|பதில்)|(?:\breply\b|பதில்).*\bfiverr\b",
    "fiverr_gig": r"\bfiverr\b.*\bgig\b|\bgig\b.*\bfiverr\b",
    "fiverr_delivery": r"\bfiverr\b.*\b(?:delivery|revision)\b",
    "website_draft": r"\b(?:website|homepage|landing page)\b|வெப்சைட்|இணையதளம்",
}


def match_task(text):
    """Return one supported task when the request contains an action and a target."""
    text = " ".join(text.casefold().split())
    if not text or _QUESTION.search(text) or not re.search(_ACTION, text):
        return None
    if re.search(r"\b(?:davinci|resolve|photoshop|canva|higgsfield)\b", text):
        return None
    if re.search(r"\bcapcut\b", text):
        if re.search(r"\b(?:for|to) capcut\b|\bcapcut\s*[-–]?க்கு", text) and re.search(r"\b(?:export|prepare)\b|தயார்", text):
            return "capcut_export"
        return None
    if re.search(r"\b(?:after effects|aftereffects)\b", text):
        if re.search(_TARGETS["after_effects_timeline"], text) and not re.search(r"\b(?:render|export|mp4)\b", text):
            return "after_effects_timeline"
        if re.search(r"\brender\b", text) and not re.search(_TARGETS["after_effects_timeline"], text):
            return "after_effects_render"
        return None
    matches = [task for task, pattern in _TARGETS.items() if task != "after_effects_timeline"
               and re.search(pattern, text)]
    return matches[0] if len(matches) == 1 else None
