"""Draft seller and website work from a user-provided brief."""
import json
import re


EDITOPRO_REPLY = "Editopro reply (Tamil + English)"

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
    EDITOPRO_REPLY: (
        'Summarize the customer request in Tamil, then draft an English reply for Editopro on Fiverr. '
        'In the summary, identify any missing details needed to quote or start. '
        'In the reply, ask only for those details and keep communication and payment on Fiverr. '
        'Make no unconfirmed promises about pricing, delivery dates, or completed work. '
        'Return plain JSON with exactly two string fields: "tamil_summary" and "english_reply". '
        'Do not include Markdown fences.'
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
    r"editopro reply|editopro பதில்|fiverr|வெப்சைட் அப்டேட்)\s*[,：:]\s*(?P<brief>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)
_VOICE_TASKS = {
    "fiverr gig": "Fiverr gig",
    "fiverr client reply": "Fiverr client reply",
    "fiverr delivery": "Fiverr delivery or revision",
    "fiverr": "Fiverr client reply",
    "editopro reply": EDITOPRO_REPLY,
    "editopro பதில்": EDITOPRO_REPLY,
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



def parse_editopro_reply(text):
    """Validate the two fields before enabling the reply-only copy action."""
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), re.IGNORECASE | re.DOTALL)
    try:
        data = json.loads(fenced[1] if fenced else text)
    except ValueError:
        raise ValueError("The response did not contain a structured Editopro draft. Try again.") from None
    fields = ("tamil_summary", "english_reply")
    if (not isinstance(data, dict) or set(data) != set(fields)
            or any(not isinstance(data[field], str) or not data[field].strip()
                   for field in fields)):
        raise ValueError("The response omitted the Tamil summary or English reply. Try again.")
    return data["tamil_summary"].strip(), data["english_reply"].strip()
