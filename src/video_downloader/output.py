"""Console presentation: banner, prompts, progress, and summary.

Progress printing is deliberately simple: a single line per status
update, ending with a newline so callers can write plain lines after
it. That keeps output stable under pipes and pytest (and any terminal).
"""

from __future__ import annotations

import sys


def _safe_reconfigure() -> None:
    """Force UTF-8 output and never crash on unencodable characters.

    Modern terminals (including Windows Terminal) expect UTF-8; without
    this, piped output on Windows degrades non-Latin titles to '????'.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


_safe_reconfigure()


def _can_encode(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# Colors when stdout is a TTY, plain otherwise.
USE_COLOR = sys.stdout.isatty()

# Degrade symbols to ASCII when the console encoding cannot represent them.
_UNICODE_OK = _can_encode("✓█╭─│")

_OK = "✓" if _UNICODE_OK else "+"
_FAIL = "✗" if _UNICODE_OK else "x"
_SKIP = "↷" if _UNICODE_OK else ">"
BAR_FULL = "█" if _UNICODE_OK else "#"
BAR_EMPTY = "░" if _UNICODE_OK else "-"

_GREEN = "\033[32m" if USE_COLOR else ""
_RESET = "\033[0m" if USE_COLOR else ""


def show_banner() -> None:
    """Print the boxed application banner."""
    title = "Simple Video Downloader"
    width = len(title) + 8
    shown = f"{_GREEN}{title}{_RESET}" if USE_COLOR else title
    if _UNICODE_OK:
        top, bottom, side = "╭", "╰", "│"
        rule = "─"
    else:
        top, bottom, side = "+", "+", "|"
        rule = "-"
    print(top + rule * width + "╮" if _UNICODE_OK else top + rule * width + "+")
    print(side + " " * 4 + shown + " " * 4 + side)
    print(bottom + rule * width + ("╯" if _UNICODE_OK else "+"))


def line(text: str = "") -> None:
    """Print a plain line."""
    print(text)


def truncate(text: str, width: int = 48) -> str:
    """Shorten long titles for tidy output."""
    text = str(text).strip()
    return text if len(text) <= width else text[: width - 3] + "..."


def _fmt_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return "unknown size"
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return "unknown size"


def _fmt_speed(speed: float | None) -> str:
    """Human-readable speed, e.g. ``4.2 MB/s``."""
    if not speed or speed <= 0:
        return ""
    return f"{_fmt_size(int(speed))}/s"


def _fmt_eta(seconds: float | None) -> str:
    """Human-readable countdown, e.g. ``00:18`` or ``1:02:30``."""
    if not seconds or seconds <= 0:
        return ""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_line(percent: float | None, title: str = "",
                  size: str = "", speed: str = "", eta: str = "") -> str:
    """Render one progress line: bar, percent, size, speed, ETA."""
    if percent is None:
        prefix = "Downloading: " + truncate(title) if title else "Downloading..."
        return prefix
    filled = int(percent / 2)
    filled = max(0, min(50, filled))
    bar = BAR_FULL * filled + BAR_EMPTY * (50 - filled)
    parts = [f"[{bar}] {percent:5.1f}%"]
    if title:
        parts.append(truncate(title))
    if size:
        parts.append(size)
    if speed:
        parts.append(speed)
    if eta:
        parts.append(f"ETA {eta}")
    return "  ".join(parts)


def download_progress(title: str, transferred: int, total: int | None,
                      speed: float | None = None,
                      eta: float | None = None) -> str:
    """Build a progress line from byte counts (+ optional speed/ETA)."""
    if not total:
        return progress_line(None, title)
    percent = min(100.0, transferred * 100.0 / total)
    return progress_line(percent, title, _fmt_size(transferred),
                         _fmt_speed(speed) or "", _fmt_eta(eta) or "")


def is_interactive() -> bool:
    """True when both stdin and stdout are a real terminal."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def prompt(text: str, default: str | None = None) -> str:
    """Prompt the user; returns the default on empty input."""
    suffix = f" [{default}]" if default is not None else ""
    try:
        answer = input(f"{text}{suffix}: ").strip()
    except EOFError:
        raise SystemExit(1)
    return answer or (default or "")


def ask(message: str, default: bool = True) -> bool:
    """Ask a yes/no question with a default."""
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"{message} [{hint}] ").strip().lower()
    except EOFError:
        raise SystemExit(1)
    if not raw:
        return default
    return raw in ("y", "yes")


def choose(options: list[tuple[str, str]], default: str) -> str:
    """Show a numbered menu; returns the chosen value (default on Enter)."""
    for index, (value, label) in enumerate(options, start=1):
        marker = f" (default)" if value == default else ""
        print(f"  {index}. {label}{marker}")
    raw = input(f"Select [1-{len(options)}] (Enter = {default}): ").strip()
    if not raw:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1][0]
    return default


def summary(downloaded: int, skipped: int, failed: int, failed_names: list[str]) -> None:
    """Print the end-of-run summary block."""
    print()
    print(f"{_GREEN}Playlist completed.{_RESET}" if downloaded + skipped + failed > 1
          else f"{_GREEN}Done.{_RESET}")
    print(f"  {_OK} Downloaded: {downloaded}")
    if skipped:
        print(f"  {_SKIP} Skipped:    {skipped}")
    if failed:
        print(f"  {_FAIL} Failed:     {failed}")
        for name in failed_names:
            print(f"    - {truncate(name)}")
