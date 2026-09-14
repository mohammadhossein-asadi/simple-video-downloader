"""Command-line interface and interactive flow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_downloader import __version__
from video_downloader import engine, output, urlinfo
from video_downloader.errors import friendly_error, missing_dependency_hint

QUALITY_LABELS = {
    "best": "Best available quality",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
    "audio": "Audio only (mp3)",
}

QUALITY_CHOICES = list(QUALITY_LABELS)


def default_download_dir() -> Path:
    """The user's standard Downloads folder, created if missing."""
    home = Path.home()
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
                   verbose: bool) -> tuple[dict | None, int]:
    """Probe the URL; on failure print a friendly error and return (None, 1)."""
    try:
        info = downloader.probe(url)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # yt-dlp raises plain DownloadError subclasses
        hint = missing_dependency_hint(exc)
        headline, reason = friendly_error(exc)
        if hint:
            reason = hint
        return None, _fail(headline, reason, verbose=verbose, exc=exc)
    if not info:
        return None, _fail("The video is unavailable or private.",
                           "Please verify the URL and try again.")
    return info, 0


class _ProgressReporter:
    """Throttled progress printing: one line per ~10% step, no spam."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._last_bucket = 0  # first line appears at >= 10%
        self._done_printed = False

    def __call__(self, status: str, current: int, total: int | None,
                 label: str | None = None) -> None:
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
        if not total:
            return  # unknown size: skip noisy intermediate lines
        percent = current * 100.0 / total
        bucket = int(percent // 10)
        if bucket > self._last_bucket:
            self._last_bucket = bucket
            output.line(output.download_progress(self.title, current, total))


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

    outdir = _outdir_from(args)
    quality = _quality_from(args)
    downloader = engine.Downloader()

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail("Cannot create the download folder.",
                     f"Permission denied while creating: {outdir}", exc=exc,
                     verbose=args.verbose)

    info, code = _probe_or_fail(downloader, url, args.verbose)
    if info is None:
        return code

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
        results = downloader.run(url, outdir, quality, progress_fn=reporter)
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
        return _fail(headline, reason, verbose=args.verbose, exc=exc)

    if not results:
        output.line(f"{output._OK} Already downloaded: nothing new to fetch.")
        return 0

    downloaded = len(results)
    output.summary(downloaded, 0, 0, [])
    output.line(f"Saved to: {outdir}")
    return 0


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
    )

    downloader = engine.Downloader()
    info, code = _probe_or_fail(downloader, url, verbose=False)
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

    options = list(QUALITY_LABELS.items())
    quality = output.choose(options, default="best")
    args.quality = quality

    target = output.prompt("Download folder", default=str(default_download_dir()))
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
    return run_download(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
