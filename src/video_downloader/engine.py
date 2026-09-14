"""yt-dlp engine wrapper: probing, format selection, and downloading.

All interaction with the underlying downloader lives here so the rest of
the app never touches yt-dlp directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from video_downloader.errors import friendly_error
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
# MP4-native streams (h264/aac) are preferred first so files can be
# finalized as .mp4 without re-encoding; generic fallbacks keep other
# sites working.
QUALITY_FORMATS: dict[str, str] = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo*+bestaudio/best",
    "1080p": ("bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
              "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
    "720p": ("bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/"
             "bestvideo[height<=720]+bestaudio/best[height<=720]/best"),
    "480p": ("bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/"
             "bestvideo[height<=480]+bestaudio/best[height<=480]/best"),
    "audio": "bestaudio/best",
}


def build_options(outdir: Path, quality: str = "best",
                  progress_fn: ProgressFn | None = None,
                  quiet: bool = False,
                  number_prefix: str = "") -> dict[str, Any]:
    """Build a safe, minimal yt-dlp option dict.

    *number_prefix* (e.g. ``"03 - "``) is prepended to filenames for
    numbered playlist/channel downloads.
    """
    outdir = Path(outdir).expanduser()
    options: dict[str, Any] = {
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "outtmpl": {
            "default": str(outdir / f"{number_prefix}%(title)s.%(ext)s"),
            "chapter": str(outdir / (
                f"{number_prefix}%(title)s - %(section_number)02d.%(ext)s")),
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
    else:
        # Videos always land as a clean .mp4 container: mp4-native
        # streams are merged directly, anything else is remuxed without
        # re-encoding (no quality loss, needs ffmpeg).
        options["merge_output_format"] = "mp4"
        options["postprocessors"] = [{
            "key": "FFmpegVideoRemuxer",
            "preferedformat": "mp4",
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
        self.last_target_dir: Path | None = None

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
                 item_label: str = "",
                 number_prefix: str = "") -> list[dict]:
        """Download *url* into *outdir*; returns list of final file infos."""
        opts = build_options(outdir, quality, progress_fn,
                             number_prefix=number_prefix)
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
                           quality: str = "best",
                           numbered: bool = False) -> bool:
        """True when a matching media file for *title* exists in *outdir*.

        Audio-only runs look for audio files, video runs for video files,
        so downloading one does not shadow the other. With *numbered*,
        filenames like ``01 - Title.mp4`` are recognized too.
        """
        outdir = Path(outdir)
        if not outdir.is_dir():
            return False
        import re

        from yt_dlp.utils import sanitize_filename

        stem = sanitize_filename(title, restricted=False)
        extensions = self.AUDIO_EXTS if quality == "audio" else self.VIDEO_EXTS
        pattern = f"*{stem}.*" if numbered else f"{stem}.*"
        # Ignore yt-dlp pre-merge intermediates like "Title.f397.mp4":
        # they exist while the matching audio stream is still downloading.
        intermediate = re.compile(r"\.f\d+$")
        return any(path.suffix.lower() in extensions
                   and not intermediate.search(path.stem)
                   for path in outdir.glob(pattern))

    def category_folder(self, outdir: Path, info: dict, kind: str) -> Path:
        """Subfolder for a playlist/channel: ``<outdir>/<title>``.

        The title is filename-sanitized; unknown titles fall back to a
        generic ``Playlist`` / ``Channel`` folder name.
        """
        from yt_dlp.utils import sanitize_filename

        fallback = "Channel" if kind == "channel" else "Playlist"
        raw = str((info or {}).get("title") or "").strip()
        name = sanitize_filename(raw, restricted=False).strip(" .") if raw else ""
        if not name:
            name = fallback
        return Path(outdir) / name

    def run(self, url: str, outdir: Path, quality: str = "best",
            progress_fn: ProgressFn | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
        """Probe → pre-check existing files → download sequentially.

        Returns ``(downloaded, failed)`` where *failed* maps item titles
        to friendly failure headlines. For playlists and channels a
        failed item never stops the batch; for a single video the error
        propagates so the CLI can show the detailed message.
        """
        from yt_dlp.utils import DownloadError

        info = self.probe(url)
        kind, count = classify(info)
        items: list[tuple[str | None, str, int]] = []

        # Playlists and channels get their own categorized subfolder with
        # numbered filenames; single videos go straight into outdir.
        target = outdir
        numbered = False
        if kind in ("playlist", "channel"):
            target = self.category_folder(outdir, info, kind)
            numbered = True
        self.last_target_dir = target

        if kind == "video":
            title = str(info.get("title") or "")
            if title and self.already_downloaded(outdir, title, quality):
                return ([], [])
            items = [(None, url, 1)]
        elif kind == "empty":
            return ([], [])
        else:
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                return ([], [])
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # yt-dlp will surface a real error if it cannot write
            # Number by global playlist position (not queue position) so
            # prefixes stay stable across resumed/partial runs.
            for position, entry in enumerate(entries, start=1):
                entry_url = entry.get("url") or entry.get("webpage_url") or ""
                if not entry_url:
                    continue
                title = entry.get("title") or "Unknown title"
                if self.already_downloaded(target, title, quality,
                                           numbered=numbered):
                    continue
                items.append((title, entry_url, position))

        if not items:
            return ([], [])

        isolate = numbered  # playlists/channels: continue past failures
        downloaded: list[dict] = []
        failed: list[tuple[str, str]] = []
        for index, (title, item_url, position) in enumerate(items, start=1):
            if len(items) > 1:
                print(f"\n[{index}/{len(items)}]", flush=True)
            if progress_fn is not None:
                progress_fn("item", index, len(items), title or "")
            prefix = f"{position:02d} - " if numbered else ""
            try:
                downloaded.extend(self.download(item_url, target, quality,
                                                progress_fn,
                                                item_label=title or "",
                                                number_prefix=prefix))
            except DownloadError as exc:
                if not isolate:
                    raise
                headline, _reason = friendly_error(exc)
                failed.append((title or item_url, headline))
                if progress_fn is not None:
                    progress_fn("item_failed", index, len(items), title or "")
                continue
        return downloaded, failed


def classify(result: dict) -> tuple[str, int | None]:
    """Classify a probe result (re-exported for callers' convenience)."""
    from video_downloader.urlinfo import classify as _classify

    return _classify(result)
