"""URL validation and light-weight classification helpers."""

import re

# Scheme is required: we only download from http(s) sources.
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

# Segments that mark a channel page across common sites.
_CHANNEL_SEGMENTS = ("/channel/", "/c/", "/user/", "/@")


def is_valid_url(url: str) -> bool:
    """True when *url* looks like an http(s) web URL."""
    if not isinstance(url, str):
        return False
    return bool(_URL_RE.match(url.strip()))


def looks_like_channel(url: str) -> bool:
    """Heuristic: True when the URL path suggests a channel page."""
    if not is_valid_url(url):
        return False
    path = url.split("://", 1)[1]
    return any(seg in path for seg in _CHANNEL_SEGMENTS)


def classify(result: dict) -> tuple[str, int | None]:
    """Classify a yt-dlp flat-extract result.

    Returns ``(kind, item_count)`` where *kind* is one of
    ``"video"``, ``"playlist"``, ``"channel"`` or ``"empty"`` and
    *item_count* is the number of entries when known (else ``None``).
    """
    if not isinstance(result, dict):
        return ("video", None)

    raw_entries = result.get("entries")
    if isinstance(raw_entries, dict):
        # yt-dlp sometimes returns a paginated dict instead of a list.
        entries = list(raw_entries.values())
    elif isinstance(raw_entries, (list, tuple)):
        entries = list(raw_entries)
    else:
        entries = None

    webpage_url = str(result.get("webpage_url") or "")
    is_channel = bool(result.get("channel_id")) or looks_like_channel(webpage_url)

    if entries is None:
        return ("video", None)

    if not entries:
        return ("empty", 0)

    count = sum(1 for entry in entries if entry)
    kind = "channel" if is_channel else "playlist"
    return (kind, count)
