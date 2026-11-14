"""Validate read-only update metadata from JARVIS's fixed GitHub Releases API.

The release checker does not download, stage, install, or execute anything.
"""
import json
import re
from urllib.parse import unquote, urlsplit

RELEASES_API_URL = "https://api.github.com/repos/mihran94/JARVIS-AI/releases?per_page=5"
RELEASES_PAGE_URL = "https://github.com/mihran94/JARVIS-AI/releases"
MAX_METADATA_BYTES = 131_072
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+\-]{0,99}\Z")
_PREFIX = "/mihran94/JARVIS-AI/releases/tag/"


class ReleaseMetadataError(ValueError):
    """Metadata is too large or not an acceptable GitHub release listing."""


def parse_releases(payload):
    """Return the most recent published release, or None if no release exists.

    Treat network data as untrusted. Never return arbitrary click-through URLs.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_METADATA_BYTES:
        raise ReleaseMetadataError("Invalid or oversized release metadata.")
    try:
        entries = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        raise ReleaseMetadataError("Invalid GitHub release response.") from None
    if not isinstance(entries, list) or len(entries) > 5:
        raise ReleaseMetadataError("Unexpected GitHub release listing.")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReleaseMetadataError("Unexpected GitHub release entry.")
        if entry.get("draft"):
            continue
        tag, url = entry.get("tag_name"), entry.get("html_url")
        if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
            raise ReleaseMetadataError("Invalid release tag.")
        if not isinstance(url, str):
            raise ReleaseMetadataError("Invalid release link.")
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "github.com"
                or parts.query or parts.fragment or not parts.path.startswith(_PREFIX)
                or unquote(parts.path[len(_PREFIX):]) != tag):
            raise ReleaseMetadataError("Untrusted release link.")
        return {"tag": tag, "url": url, "prerelease": entry.get("prerelease") is True}
    return None
