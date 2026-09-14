"""yt-dlp engine wrapper: probing, format selection, and downloading.

All interaction with the underlying downloader lives here so the rest of
the app never touches yt-dlp directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from video_downloader.output import download_progress, truncate

ProgressFn = Callable[..., None]


class _QuietLogger:
    """Swallow yt-dlp's own console output; we render messages ourselves."""

    def debug(self, msg: str) -> None:  # noqa: D102
        pass

    def warning(self, msg: str) -> None:  # noqa: D102
        pass

    def error(self, msg: str) -> None:  # noqa: D102
        pass

# Maps user-facing quality choices to yt-dlp format selectors.
QUALITY_FORMATS: dict[str, str] = {
    "best": "bestvideo*+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "audio": "bestaudio/best",
}


def build_options(outdir: Path, quality: str = "best",
                  progress_fn: ProgressFn | None = None,
                  quiet: bool = False) -> dict[str, Any]:
    """Build a safe, minimal yt-dlp option dict."""
    outdir = Path(outdir).expanduser()
    options: dict[str, Any] = {
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "outtmpl": {
            "default": str(outdir / "%(title)s.%(ext)s"),
            "chapter": str(outdir / "%(title)s - %(section_number)02d.%(ext)s"),
        },
        "noplaylist": False,
        "nooverwrites": True,
        "continuedl": True,           # resume .part files
        "retries": 3,
        "concurrent_fragment_downloads": 4,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,           # we render our own progress
        "windowsfilenames": True,     # safest filename rules everywhere
        "restrictfilenames": False,
        "trim_file_name": 120,        # avoid pathological filename lengths
        "progress_hooks": [],
        "postprocessor_hooks": [],
        "ignoreerrors": False,
        "logger": _QuietLogger(),
    }
    if quality == "audio":
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }]
    if progress_fn is not None:
        options["progress_hooks"] = [_make_hook(progress_fn)]
    if quiet:
        options["progress_hooks"] = []
        options["postprocessor_hooks"] = []
    return options


def _make_hook(progress_fn: ProgressFn) -> Callable[[dict], None]:
    """Adapt a yt-dlp progress hook to our ProgressFn signature."""

    def hook(data: dict) -> None:
        status = data.get("status")
        if status == "finished":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            progress_fn("done", total or 0, total)
        elif status in ("downloading",):
            transferred = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            progress_fn("downloading", transferred, total)
        # "error" and others are handled through exceptions post-run.

    return hook


class Downloader:
    """Thin wrapper around a yt-dlp YoutubeDL instance."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        from yt_dlp import YoutubeDL  # imported lazily; yt-dlp is a hard dep

        self._ydl_cls = YoutubeDL
        self._options = options or {}

    def probe(self, url: str) -> dict:
        """Return flat metadata for *url* without downloading.

        Raises whatever yt-dlp raises on invalid/private/unsupported URLs.
        """
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "logger": _QuietLogger(),
        }
        with self._ydl_cls(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info if isinstance(info, dict) else {}

    def download(self, url: str, outdir: Path, quality: str = "best",
                 progress_fn: ProgressFn | None = None,
                 item_label: str = "") -> list[dict]:
        """Download *url* into *outdir*; returns list of final file infos."""
        opts = build_options(outdir, quality, progress_fn)
        downloaded: list[dict] = []
        with self._ydl_cls(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if isinstance(info, dict):
                if info.get("_type") == "playlist":
                    for entry in info.get("entries") or []:
                        if entry:
                            downloaded.append(entry)
                else:
                    downloaded.append(info)
        return downloaded

    AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac"}
    VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v"}

    def already_downloaded(self, outdir: Path, title: str,
                           quality: str = "best") -> bool:
        """True when a matching media file for *title* exists in *outdir*.

        Audio-only runs look for audio files, video runs for video files,
        so downloading one does not shadow the other.
        """
        outdir = Path(outdir)
        if not outdir.is_dir():
            return False
        from yt_dlp.utils import sanitize_filename

        stem = sanitize_filename(title, restricted=False)
        extensions = self.AUDIO_EXTS if quality == "audio" else self.VIDEO_EXTS
        return any(path.suffix.lower() in extensions
                   for path in outdir.glob(f"{stem}.*"))

    def run(self, url: str, outdir: Path, quality: str = "best",
            progress_fn: ProgressFn | None = None) -> list[dict]:
        """Probe → pre-check existing files → download sequentially."""
        from yt_dlp.utils import DownloadError

        info = self.probe(url)
        kind, count = classify(info)
        items: list[tuple[str | None, str]] = []

        if kind == "video":
            title = str(info.get("title") or "")
            if title and self.already_downloaded(outdir, title, quality):
                return []
            items = [(None, url)]
        elif kind == "empty":
            return []
        else:
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                return []
            for entry in entries:
                entry_url = entry.get("url") or entry.get("webpage_url") or ""
                if not entry_url:
                    continue
                title = entry.get("title") or "Unknown title"
                if self.already_downloaded(outdir, title, quality):
                    continue
                items.append((title, entry_url))

        if not items:
            return []

        downloaded: list[dict] = []
        for index, (title, item_url) in enumerate(items, start=1):
            if len(items) > 1:
                print(f"\n[{index}/{len(items)}]", flush=True)
            if progress_fn is not None:
                progress_fn("item", index, len(items), title or "")
            try:
                downloaded.extend(self.download(item_url, outdir, quality,
                                                progress_fn, item_label=title or ""))
            except DownloadError as exc:
                raise
        return downloaded


def classify(result: dict) -> tuple[str, int | None]:
    """Classify a probe result (re-exported for callers' convenience)."""
    from video_downloader.urlinfo import classify as _classify

    return _classify(result)
