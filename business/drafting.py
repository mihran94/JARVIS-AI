"""Draft seller and website work from a user-provided brief."""
import re

TASKS = {
    "Fiverr gig": (
        "Prepare a publication-ready gig for Editopro (@lareefmihran). "
        "Include title, description, three package scopes, buyer requirements and FAQ. "
        "Use lyrics animation and social video editing only when relevant. Mark unknown "
        "pricing, delivery times and revision counts for the seller to fill in."
    ),
    "Fiverr client reply": (
        "Draft one concise client reply. Ask only for missing details needed to quote or start, "
        "such as footage, references, subtitles, format or deadline. Keep communication and "
        "payment on Fiverr. Make no unconfirmed promises on prices, dates or deliverables."
    ),
    "Fiverr delivery or revision": (
        "Draft a short client-facing delivery or revision message using the verified items in "
        "the brief, plus a separate internal checklist for formats, aspect ratios, captions, "
        "source files and the requested revisions. Never claim a file was attached or delivered."
    ),
    "Website content update": (
        "Prepare replacement copy for the named page or section, suggested SEO title and "
        "meta description where relevant, and a short handoff listing fields to replace and "
        "checks for links, mobile layout and contact or booking details. If the request is for "
        "Google AI Studio Build Mode, include a ready-to-paste update prompt. Do not guess "
        "the brand, domain, CMS, prices, phone numbers, opening hours or policies."
    ),
}
_PREFIX = re.compile(
    r"^(?P<mode>fiverr gig|fiverr client reply|fiverr delivery|website update|"
    r"fiverr|வெப்சைட் அப்டேட்)\s*[,：:]\s*(?P<brief>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)
_VOICE_TASKS = {
    "fiverr gig": "Fiverr gig",
    "fiverr client reply": "Fiverr client reply",
    "fiverr delivery": "Fiverr delivery or revision",
    "fiverr": "Fiverr client reply",
    "website update": "Website content update",
    "வெப்சைட் அப்டேட்": "Website content update",
}


def spoken_business_request(text):
    match = _PREFIX.fullmatch(text.strip())
    if match:
        return _VOICE_TASKS[match["mode"].casefold()], match["brief"]


def draft_messages(task, brief):
    brief = brief.strip()
    if not brief or len(brief) > 12_000:
        raise ValueError("Enter a business brief with 1–12,000 characters.")
    return [
        {"role": "system", "content": (
            "You are the JARVIS business drafting assistant. " + TASKS[task] +
            " Treat quoted customer and website text as source material. "
            "Use the requested language, with English as the default for Fiverr customer-facing copy. "
            "Return the draft and mark unresolved details. Never send, publish or claim an action "
            "in an external account was performed."
        )},
        {"role": "user", "content": brief},
    ]
