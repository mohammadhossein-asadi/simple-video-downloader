"""Command-line interface and interactive flow."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from video_downloader import __version__
from video_downloader import config as settings_store
from video_downloader import engine, output, urlinfo
from video_downloader.errors import (friendly_error, is_auth_headline,
                                     is_network_error,
                                     missing_dependency_hint)

PROXY_TIP = ("Tip: if you use a VPN or proxy, run again with "
             "--proxy HOST:PORT so downloads use the same route "
             "(see README).")

QUALITY_LABELS = {
    "best": "Best available quality",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
    "audio": "Audio only (mp3)",
}

QUALITY_CHOICES = list(QUALITY_LABELS)

BROWSERS = ("chrome", "firefox", "edge", "brave", "safari", "chromium",
            "opera", "vivaldi", "whale")


def available_heights(info: dict) -> list[int]:
    """Sorted video heights (p) from a probe result."""
    heights = set()
    for fmt in (info or {}).get("formats") or []:
        height = fmt.get("height")
        if isinstance(height, int) and height > 0 and fmt.get("vcodec") != "none":
            heights.add(height)
    return sorted(heights)


def format_list_table(info: dict) -> list[str]:
    """Render the ``--list`` quality preview for a probed item."""
    rows = [f"Title: {output.truncate(str(info.get('title') or '?'))}"]
    if (info or {}).get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        rows.append(f"Items: {len(entries)}")
        rows.append("(qualities are shown per video when downloading)")
        return rows
    heights = available_heights(info)
    if heights:
        rows.append("Available qualities: "
                    + ", ".join(f"{h}p" for h in reversed(heights)))
    else:
        rows.append("Available qualities: unknown (no formats listed)")
    return rows


def _annotate_quality_menu(available: list[int]) -> list[tuple[str, str]]:
    """Quality menu labels annotated with real heights when known."""
    labels = dict(QUALITY_LABELS)
    for value in ("1080p", "720p", "480p"):
        height = int(value.rstrip("p"))
        marks = [h for h in available if h <= height]
        if available and marks:
            labels[value] = f"{value} (best available: {max(marks)}p)"
        elif available:
            labels[value] = f"{value} (not available)"
    return list(labels.items())


def _apply_saved_settings(args: argparse.Namespace) -> None:
    """Fill unset options from the saved settings file (opt-in).

    CLI flags always win: only options still at their default are
    replaced. ``--no-config`` skips the file entirely.
    """
    if getattr(args, "no_config", False):
        return
    saved = settings_store.load_config(settings_store.config_path())
    if saved.get("quality") in QUALITY_LABELS and args.quality == "best" \
            and not args.audio:
        args.quality = saved["quality"]
    if saved.get("output") and not args.output:
        args.output = saved["output"]
    if saved.get("proxy") and not getattr(args, "proxy", None):
        args.proxy = saved["proxy"]


def _maybe_save_settings(args: argparse.Namespace, quality: str) -> None:
    """Offer to remember this run's settings (interactive terminals only)."""
    if not output.is_interactive() or getattr(args, "no_config", False):
        return
    if not output.ask("Remember these settings for future runs?",
                      default=False):
        return
    path = settings_store.save_config(settings_store.config_path(), {
        "quality": quality,
        "output": str(_outdir_from(args)),
        "proxy": getattr(args, "proxy", None) or "",
    })
    output.line(f"Settings saved to {path}")


def is_termux() -> bool:
    """True when running inside Termux on Android."""
    if "TERMUX_VERSION" in os.environ:
        return True
    return "com.termux" in sys.prefix or "com.termux" in str(Path.home())


def termux_storage_ready() -> bool:
    """True when ``termux-setup-storage`` has been run at least once."""
    return (Path.home() / "storage").is_dir()


def default_download_dir() -> Path:
    """The user's standard Downloads folder, created if missing.

    On Termux this is the phone's shared Downloads folder (once storage
    access has been granted via ``termux-setup-storage``); without it,
    an app-private ``~/Downloads`` is used.
    """
    home = Path.home()
    if is_termux():
        shared = home / "storage" / "downloads"
        if shared.is_dir():
            return shared
    for name in ("Downloads", "downloads"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    downloads = home / "Downloads"
    try:
        downloads.mkdir(parents=True, exist_ok=True)
    except OSError:
        return home
    return downloads


def build_parser() -> argparse.ArgumentParser:
    """The full argument parser (also embedded in the generated README)."""
    parser = argparse.ArgumentParser(
        prog="video-downloader",
        description="Simple Video Downloader - download videos, playlists, "
                    "and channels with one URL.",
        epilog="Run without arguments for interactive mode.",
    )
    parser.add_argument("url", nargs="?", help="video, playlist, or channel URL")
    parser.add_argument("-o", "--output", metavar="DIR",
                        help="download directory (default: your Downloads folder)")
    parser.add_argument("-q", "--quality", choices=QUALITY_CHOICES, default="best",
                        help="quality preference (default: best)")
    parser.add_argument("-a", "--audio", action="store_true",
                        help="audio only, saved as mp3 (shorthand for --quality audio)")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER",
                        dest="cookies", default=None,
                        choices=BROWSERS,
                        help="sign in with a browser's cookies, for "
                             "age-restricted or private content "
                             f"({', '.join(BROWSERS)})")
    parser.add_argument("--cookies", metavar="FILE", dest="cookies_file",
                        default=None,
                        help="sign in with a cookies.txt file (Netscape "
                             "format), as an alternative to "
                             "--cookies-from-browser")
    parser.add_argument("--proxy", metavar="PROXY", default=None,
                        help="route downloads through a proxy, e.g. "
                             "127.0.0.1:8080 or socks5://127.0.0.1:1080")
    parser.add_argument("--subs", metavar="LANGS", default=None,
                        help="download subtitles, e.g. en,fa (saved next "
                             "to the video)")
    parser.add_argument("--list", action="store_true", dest="list_only",
                        help="show the available qualities for the URL "
                             "and exit without downloading")
    parser.add_argument("--no-config", action="store_true", dest="no_config",
                        help="ignore the saved settings file for this run")
    parser.add_argument("--verbose", action="store_true",
                        help="show detailed error information")
    parser.add_argument("-V", "--version", action="version",
                        version=f"video-downloader {__version__}")
    return parser


def _outdir_from(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).expanduser()
    return default_download_dir()


def _quality_from(args: argparse.Namespace) -> str:
    return "audio" if args.audio else args.quality


def _fail(headline: str, reason: str, verbose: bool = False,
          exc: BaseException | None = None) -> int:
    output.line()
    output.line(f"{output._FAIL} Download failed")
    output.line()
    output.line("Reason:")
    output.line(headline)
    output.line()
    output.line(reason)
    output.line()
    if verbose and exc is not None:
        import traceback
        traceback.print_exc()
    else:
        output.line("Tip: run again with --verbose for technical details.")
    return 1


def _probe_or_fail(downloader: engine.Downloader, url: str,
                   verbose: bool,
                   args: argparse.Namespace | None = None) -> tuple[dict | None, int]:
    """Probe the URL; on failure print a friendly error and return (None, 1).

    When *args* is given and the failure looks like a sign-in gate, offer
    a browser-cookie retry (interactive terminals only).
    """
    try:
        info = downloader.probe(url)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # yt-dlp raises plain DownloadError subclasses
        hint = missing_dependency_hint(exc)
        headline, reason = friendly_error(exc)
        if hint:
            reason = hint
        if args is not None and is_auth_headline(headline):
            info2, offered = _offer_cookie_signin(downloader, url, args)
            if info2 is not None:
                return info2, 0
            if offered:
                return None, 1  # failure details already shown
        if (is_network_error(headline)
                and not getattr(args, "proxy", None)):
            reason = f"{reason}\n{PROXY_TIP}"
        return None, _fail(headline, reason, verbose=verbose, exc=exc)
    if not info:
        return None, _fail("The video is unavailable or private.",
                           "Please verify the URL and try again.")
    return info, 0


def _offer_cookie_signin(downloader: engine.Downloader, url: str,
                         args: argparse.Namespace) -> tuple[dict | None, bool]:
    """Offer a browser-cookie sign-in retry for gated content.

    Returns ``(info, offered)``: *info* is not None when the retry probe
    succeeded (and ``args.cookies`` is remembered for the run); *offered*
    is False when no offer was possible or the user declined.
    """
    if (not output.is_interactive() or getattr(args, "cookies", None)
            or getattr(args, "cookies_file", None)):
        return None, False
    if not output.ask("Sign in with your browser's cookies and retry?",
                      default=True):
        return None, False
    browser = output.prompt("Which browser are you signed in with",
                            default="chrome")
    if browser not in BROWSERS:
        browser = "chrome"
    info, _err = _probe_with_cookies(downloader, url, browser)
    if info is None:
        return None, True
    args.cookies = browser
    return info, True


def _probe_with_cookie_file(downloader: engine.Downloader, url: str,
                            cookies_file: str) -> tuple[dict | None, str | None]:
    """Probe *url* using a cookies.txt file; mirrors the browser variant."""
    output.line(f"\nUsing cookies from {cookies_file}...")
    downloader.cookies_file = cookies_file
    try:
        info = downloader.probe(url)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        headline, reason = friendly_error(exc)
        output.line(f"{output._FAIL} Could not access the content with "
                    "these cookies.")
        output.line()
        output.line(reason)
        return None, headline
    if not info:
        output.line(f"{output._FAIL} Could not access the content with "
                    "these cookies.")
        return None, "The video is unavailable or private."
    output.line(f"{output._OK} Signed in - access granted.")
    return info, None


def _probe_with_cookies(downloader: engine.Downloader, url: str,
                        browser: str) -> tuple[dict | None, str | None]:
    """Probe *url* using *browser* cookies.

    Returns ``(info, None)`` on success or ``(None, friendly_headline)``
    on a clean failure.
    """
    output.line(f"\nSigning in with your {browser} cookies...")
    downloader.cookies_from_browser = browser
    try:
        info = downloader.probe(url)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        headline, reason = friendly_error(exc)
        output.line(f"{output._FAIL} Could not access the content with "
                    f"{browser} cookies.")
        output.line()
        output.line(reason)
        return None, headline
    if not info:
        output.line(f"{output._FAIL} Could not access the content with "
                    f"{browser} cookies.")
        return None, "The video is unavailable or private."
    output.line(f"{output._OK} Signed in - access granted.")
    return info, None


class _ProgressReporter:
    """Throttled progress printing: one line per ~10% step, no spam."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._last_bucket = 0  # first line appears at >= 10%
        self._done_printed = False

    def __call__(self, status: str, current: int, total: int | None,
                 label: str | None = None, speed: float | None = None,
                 eta: float | None = None) -> None:
        if status == "item":
            if label:
                self.title = label
            self._last_bucket = 0
            self._done_printed = False
            return
        if status == "done":
            if not self._done_printed:
                output.line(f"{output._OK} Finished: "
                            f"{output.truncate(self.title)}")
                self._done_printed = True
            return
        if status == "item_failed":
            output.line(f"{output._FAIL} Failed: "
                        f"{output.truncate(label or self.title)}")
            return
        if not total:
            return  # unknown size: skip noisy intermediate lines
        percent = current * 100.0 / total
        bucket = int(percent // 10)
        if bucket > self._last_bucket:
            self._last_bucket = bucket
            output.line(output.download_progress(self.title, current, total,
                                                 speed, eta))


def run_download(args: argparse.Namespace, announce: bool = True) -> int:
    """Direct (non-interactive) download flow for a parsed URL.

    Set *announce* to ``False`` when the URL was already described to
    the user (interactive flow) to avoid printing it twice.
    """
    url = args.url.strip()
    if not urlinfo.is_valid_url(url):
        output.line(f"{output._FAIL} That does not look like a valid URL.")
        output.line("Expected something like: https://www.example.com/watch?v=...")
        return 1

    if args.cookies or args.cookies_file or args.proxy or args.subs:
        downloader = engine.Downloader(cookies_from_browser=args.cookies,
                                       cookies_file=args.cookies_file,
                                       proxy=args.proxy,
                                       subs=args.subs)
    else:
        downloader = engine.Downloader()

    if args.cookies_file:
        info, err = _probe_with_cookie_file(downloader, url, args.cookies_file)
        if info is None:
            return 1
    elif args.cookies:
        info, err = _probe_with_cookies(downloader, url, args.cookies)
        if info is None:
            return 1
    else:
        info, code = _probe_or_fail(downloader, url, args.verbose, args=args)
        if info is None:
            return code

    if args.list_only:
        output.line()
        for row in format_list_table(info):
            output.line(row)
        return 0

    return _download_probed(args, downloader, url, info, announce=announce)


def _download_probed(args: argparse.Namespace, downloader: engine.Downloader,
                     url: str, info: dict, announce: bool = True) -> int:
    """Finish a direct download whose probe already succeeded."""
    outdir = _outdir_from(args)
    quality = _quality_from(args)

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail("Cannot create the download folder.",
                     f"Permission denied while creating: {outdir}", exc=exc,
                     verbose=args.verbose)

    kind, count = urlinfo.classify(info)
    title = output.truncate(str(info.get("title") or url))

    if kind == "empty":
        output.line(f"{output._SKIP} Nothing to download: the playlist or "
                    "channel is empty.")
        return 0

    if announce:
        if kind == "video":
            output.line(f"Video: {title}")
        else:
            label = "Channel" if kind == "channel" else "Playlist"
            size = f" ({count} videos)" if count else ""
            output.line(f"{label}: {title}{size}")

    try:
        reporter = _ProgressReporter(title)
        results, failures = downloader.run(url, outdir, quality,
                                           progress_fn=reporter)
    except KeyboardInterrupt:
        output.line()
        output.line("Download interrupted.")
        if output.ask("Resume download next time by re-running the same command?",
                      default=True):
            output.line("Partial files were kept - re-run the same command to resume.")
        return 130
    except Exception as exc:
        hint = missing_dependency_hint(exc)
        headline, reason = friendly_error(exc)
        if hint:
            reason = hint
        if (is_network_error(headline)
                and not getattr(args, "proxy", None)):
            reason = f"{reason}\n{PROXY_TIP}"
        # Age-restricted / private content can often be fetched once the
        # user signs in through their own browser's cookies.
        if is_auth_headline(headline):
            info2, offered = _offer_cookie_signin(downloader, url, args)
            if info2 is not None:
                return _download_probed(args, downloader, url, info2,
                                        announce=True)
            if offered:
                return 1  # failure details already shown
        return _fail(headline, reason, verbose=args.verbose, exc=exc)

    if not results and not failures:
        output.line(f"{output._OK} Already downloaded: nothing new to fetch.")
        return 0

    downloaded = len(results)
    failed_names = [name for name, _headline in failures]
    output.summary(downloaded, 0, len(failures), failed_names)
    if failures:
        output.line()
        output.line("Tip: re-run the same command to retry only the failed "
                    "items.")
    saved_to = getattr(downloader, "last_target_dir", None) or outdir
    output.line(f"Saved to: {saved_to}")
    _maybe_save_settings(args, quality)
    return 1 if failures else 0


def interactive() -> int:
    """The primary experience: ask for a URL, then download."""
    output.show_banner()
    url = output.prompt("Enter video, playlist, or channel URL")
    if not urlinfo.is_valid_url(url):
        output.line(f"{output._FAIL} That does not look like a valid URL.")
        output.line("Expected something like: https://www.example.com/watch?v=...")
        return 1

    args = argparse.Namespace(
        url=url, output=None, quality="best", audio=False, verbose=False,
        cookies=None, cookies_file=None, proxy=None,
        subs=None, no_config=False, list_only=False,
    )
    _apply_saved_settings(args)

    downloader = engine.Downloader()
    info, code = _probe_or_fail(downloader, url, verbose=False, args=args)
    if info is None:
        return code

    kind, count = urlinfo.classify(info)
    title = output.truncate(str(info.get("title") or url))

    if kind == "empty":
        output.line(f"{output._SKIP} Nothing to download: the playlist or "
                    "channel is empty.")
        return 0

    if kind == "video":
        output.line(f"Video: {title}")
    else:
        label = "Channel" if kind == "channel" else "Playlist"
        size = f" ({count} videos)" if count else ""
        output.line(f"{label}: {title}{size}")

    options = _annotate_quality_menu(available_heights(info))
    quality = output.choose(options, default=args.quality)
    args.quality = quality

    if is_termux() and not termux_storage_ready():
        output.line("Tip: run 'termux-setup-storage' once so downloads can "
                    "reach your phone's shared Downloads folder.")

    target = output.prompt("Download folder",
                           default=str(args.output or default_download_dir()))
    args.output = target

    return run_download(args, announce=False)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the console script."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.url is None:
        try:
            return interactive()
        except KeyboardInterrupt:
            output.line()
            output.line("Cancelled.")
            return 130
    _apply_saved_settings(args)
    return run_download(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
