"""Friendly, plain-English rendering of download failures."""

from __future__ import annotations

import re


def _match(message: str, *patterns: str) -> bool:
    lowered = message.lower()
    return any(p in lowered for p in patterns)


def friendly_error(exc: BaseException) -> tuple[str, str]:
    """Map an exception to ``(headline, reason)`` for normal users.

    Unknown errors fall back to a generic but honest message; the full
    detail stays available via ``--verbose``.
    """
    message = str(exc)

    if _match(message, "could not copy", "cookie database"):
        return ("Could not read your browser's cookies.",
                "Close the browser completely and retry, or choose a "
                "different browser where you are signed in. Recent Chrome "
                "versions protect their cookies; Firefox and Edge work "
                "reliably.")
    if _match(message, "age-restricted", "age restricted", "confirm your age",
              "age gate", "inappropriate"):
        return ("This content is age-restricted.",
                "Age-restricted content can only be accessed while signed in. "
                "Retry and choose to sign in with your browser's cookies - or "
                "run with --cookies-from-browser <browser>.")
    if _match(message, "not a bot"):
        return ("The site is rate limiting requests.",
                "Too many requests were sent in a short time. Wait a few "
                "minutes before trying again.")
    if _match(message, "private video", "members-only", "sign in to confirm",
              "login required", "account", "cookies"):
        return ("This content is private or requires sign-in.",
                "The video may be private, members-only, or the site is asking "
                "for verification. If you have access, retry and choose to "
                "sign in with your browser's cookies - or run with "
                "--cookies-from-browser <browser>.")
    if _match(message, "http error 5", "server error", "503", "500"):
        return ("The site had a server problem.",
                "The website reported an internal error. Try again later.")
    if _match(message, "removed", "unavailable", "not available", "deleted",
              "not exist", "404", "not found", "no video"):
        return ("The video is unavailable or private.",
                "Please verify the URL and try again - the content may have "
                "been removed or the link may be mistyped.")
    if _match(message, "rate limit", "too many requests", "429"):
        return ("The site is rate limiting requests.",
                "Too many requests were sent in a short time. Wait a few "
                "minutes before trying again.")
    if _match(message, "timed out", "timeout", "connection", "network",
              "temporary failure", "resolve", "unreachable"):
        return ("A network problem occurred.",
                "Check your internet connection and try again.")
    if _match(message, "no space", "disk full", "quota"):
        return ("Not enough disk space.",
                "Free up space on the target drive and try again.")
    if _match(message, "permission", "access is denied", "readonly", "read-only"):
        return ("Permission denied.",
                "The output folder cannot be written to. Choose a different "
                "folder or check folder permissions.")
    if _match(message, "unsupported url", "no suitable", "unable to extract",
              "does not pass filter"):
        return ("This URL is not supported.",
                "The site or link is not recognized as downloadable media. "
                "Double-check the URL.")
    if _match(message, "ffmpeg"):
        return ("The ffmpeg tool is missing.",
                "ffmpeg is required for high-quality downloads. Install it "
                "and make sure it is on your PATH (see README).")

    # Unknown: stay honest, remain readable. yt-dlp prefixes its errors
    # with "ERROR: "; drop it so the message does not stutter.
    short = re.sub(r"^ERROR:\s*", "", message, flags=re.IGNORECASE)
    short = re.sub(r"\s+", " ", short).strip()
    if len(short) > 220:
        short = short[:217] + "..."
    return ("Download failed.", short or "An unexpected error occurred.")


# Headlines for failures that a browser-cookie sign-in can fix.
AUTH_HEADLINES = (
    "This content is age-restricted.",
    "This content is private or requires sign-in.",
)


def is_auth_headline(headline: str) -> bool:
    """True when *headline* describes a sign-in-gated failure."""
    return headline in AUTH_HEADLINES


def missing_dependency_hint(exc: BaseException) -> str | None:
    """Return a hint when *exc* looks like a missing runtime dependency."""
    text = f"{type(exc).__name__}: {exc}"
    if "No module named" in text:
        return ("A required Python package is missing. Reinstall the tool "
                "with: pip install --upgrade simple-video-downloader")
    return None
