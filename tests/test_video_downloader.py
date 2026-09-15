"""Tests for urlinfo, errors, engine options, output, and CLI flows."""

from __future__ import annotations

import io
import os

import pytest

from video_downloader import cli, engine, output, urlinfo
from video_downloader.errors import (friendly_error, is_auth_headline,
                                     missing_dependency_hint)


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://example.com/watch?v=abc",
    "http://example.com/video",
    "HTTPS://Example.Com/Video",
])
def test_valid_urls(url):
    assert urlinfo.is_valid_url(url) is True


@pytest.mark.parametrize("url", [
    "",
    "not a url",
    "example.com/video",
    "ftp://example.com/video",
    "file:///C:/video.mp4",
    "javascript:alert(1)",
])
def test_invalid_urls(url):
    assert urlinfo.is_valid_url(url) is False


def test_channel_heuristic():
    assert urlinfo.looks_like_channel("https://x.test/@handle") is True
    assert urlinfo.looks_like_channel("https://x.test/channel/abc") is True
    assert urlinfo.looks_like_channel("https://x.test/watch?v=1") is False


# --------------------------------------------------------------------------
# Classification of probe results
# --------------------------------------------------------------------------

def test_classify_single_video():
    result = {"_type": "video", "title": "Test",
              "webpage_url": "https://x.test/watch?v=1"}
    assert urlinfo.classify(result) == ("video", None)


def test_classify_playlist():
    result = {"_type": "playlist", "title": "My List",
              "webpage_url": "https://x.test/playlist?list=PL1",
              "entries": [{"title": "a"}, {"title": "b"}]}
    assert urlinfo.classify(result) == ("playlist", 2)


def test_classify_channel():
    result = {"_type": "playlist", "title": "Chan",
              "webpage_url": "https://x.test/@handle",
              "entries": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}
    assert urlinfo.classify(result) == ("channel", 3)


def test_classify_playlist_with_channel_metadata_stays_playlist():
    # Playlists carry channel_id in their metadata; only the URL shape
    # decides the kind, so this must stay a playlist.
    result = {"_type": "playlist", "title": "My List",
              "webpage_url": "https://www.youtube.com/playlist?list=PL1",
              "channel_id": "UCabc123",
              "entries": [{"title": "a"}, {"title": "b"}]}
    assert urlinfo.classify(result) == ("playlist", 2)


def test_classify_empty_playlist():
    result = {"_type": "playlist", "entries": [],
              "webpage_url": "https://x.test/playlist?list=PL1"}
    assert urlinfo.classify(result) == ("empty", 0)


def test_classify_paginated_entries_dict():
    result = {"_type": "playlist", "webpage_url": "https://x.test/playlist",
              "entries": {"1": {"title": "a"}, "2": {"title": "b"}}}
    assert urlinfo.classify(result) == ("playlist", 2)


def test_classify_none_and_none_entries():
    assert urlinfo.classify(None) == ("video", None)
    assert urlinfo.classify({"title": "x"}) == ("video", None)


def test_engine_classify_reexport():
    assert engine.classify({"_type": "video"}) == ("video", None)


# --------------------------------------------------------------------------
# Format selection / engine options
# --------------------------------------------------------------------------

def test_quality_format_mapping():
    assert engine.QUALITY_FORMATS["best"].startswith("bestvideo[ext=mp4]")
    assert "height<=1080" in engine.QUALITY_FORMATS["1080p"]
    assert "height<=720" in engine.QUALITY_FORMATS["720p"]
    assert "height<=480" in engine.QUALITY_FORMATS["480p"]
    assert engine.QUALITY_FORMATS["audio"] == "bestaudio/best"


def test_build_options_safe_defaults(tmp_path):
    opts = engine.build_options(tmp_path, "best")
    assert opts["nooverwrites"] is True
    assert opts["continuedl"] is True
    assert opts["noplaylist"] is False
    assert str(tmp_path) in opts["outtmpl"]["default"]
    assert opts["retries"] >= 3
    assert isinstance(opts["logger"], engine._QuietLogger)


def test_build_options_videos_are_mp4(tmp_path):
    opts = engine.build_options(tmp_path, "best")
    assert opts["merge_output_format"] == "mp4"
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert keys == ["FFmpegVideoRemuxer"]
    assert "[ext=mp4]" in opts["format"] and "[ext=m4a]" in opts["format"]


def test_build_options_audio_has_no_mp4_merger(tmp_path):
    opts = engine.build_options(tmp_path, "audio")
    assert "merge_output_format" not in opts
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert keys == ["FFmpegExtractAudio"]


def test_build_options_number_prefix(tmp_path):
    opts = engine.build_options(tmp_path, "best", number_prefix="03 - ")
    assert opts["outtmpl"]["default"].endswith("03 - %(title)s.%(ext)s")


def test_build_options_audio_postprocessor(tmp_path):
    opts = engine.build_options(tmp_path, "audio")
    assert opts["format"] == "bestaudio/best"
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert "FFmpegExtractAudio" in keys


def test_build_options_quiet_disables_hooks(tmp_path):
    opts = engine.build_options(tmp_path, "best",
                                progress_fn=lambda *a: None, quiet=True)
    assert opts["progress_hooks"] == []


def test_build_options_without_cookies_has_no_cookie_option(tmp_path):
    opts = engine.build_options(tmp_path, "best")
    assert "cookiesfrombrowser" not in opts


def test_build_options_cookies_from_browser(tmp_path):
    opts = engine.build_options(tmp_path, "best",
                                cookies_from_browser="firefox")
    assert opts["cookiesfrombrowser"] == ("firefox", None, None, None)


def test_build_options_cookies_file_takes_precedence(tmp_path):
    file_opts = engine.build_options(tmp_path, "best",
                                     cookies_file="cookies.txt")
    assert file_opts["cookiefile"] == "cookies.txt"
    both = engine.build_options(tmp_path, "best",
                                cookies_from_browser="firefox",
                                cookies_file="cookies.txt")
    assert both["cookiefile"] == "cookies.txt"
    assert "cookiesfrombrowser" not in both


def test_progress_hook_adapts_to_progress_fn():
    seen = []
    hook = engine._make_hook(lambda status, t, total: seen.append((status, t, total)))
    hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 200})
    hook({"status": "finished", "total_bytes": 200})
    assert seen == [("downloading", 100, 200), ("done", 200, 200)]


# --------------------------------------------------------------------------
# Friendly errors
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    ("Private video. Sign in if you've been granted access",
     "This content is private or requires sign-in."),
    ("Video unavailable", "The video is unavailable or private."),
    ("This video is not available. Watch on the latest version of YouTube",
     "The video is unavailable or private."),
    ("HTTP Error 429: Too Many Requests", "The site is rate limiting requests."),
    ("URLError: timed out", "A network problem occurred."),
    ("unsupported URL: https://x.test", "This URL is not supported."),
    ("[Errno 28] No space left on device", "Not enough disk space."),
    ("PermissionError: access is denied", "Permission denied."),
    ("ffmpeg is not installed", "The ffmpeg tool is missing."),
    ("HTTP Error 503: Service Unavailable", "The site had a server problem."),
])
def test_friendly_error_mapping(message, expected):
    headline, reason = friendly_error(RuntimeError(message))
    assert headline == expected
    assert reason  # always explain something useful


def test_friendly_error_age_restriction():
    headline, reason = friendly_error(RuntimeError("This video is age restricted"))
    assert "age-restricted" in headline.lower()
    assert "cookies" in reason.lower()  # points to the sign-in remedy


def test_auth_headline_detection():
    assert is_auth_headline("This content is age-restricted.") is True
    assert is_auth_headline("This content is private or requires sign-in.") is True
    assert is_auth_headline("A network problem occurred.") is False
    assert is_auth_headline("Download failed.") is False


def test_friendly_error_cookie_database_locked():
    headline, reason = friendly_error(RuntimeError(
        "ERROR: Could not copy Chrome cookie database. See "
        "https://github.com/yt-dlp/yt-dlp/issues/7271"))
    assert headline == "Could not read your browser's cookies."
    assert "Close the browser completely" in reason


def test_friendly_error_strips_ytdlp_error_prefix():
    headline, reason = friendly_error(RuntimeError(
        "ERROR: something unusual happened"))
    assert headline == "Download failed."
    assert reason.startswith("something unusual happened")
    assert not reason.startswith("ERROR:")


def test_friendly_error_unknown_is_generic_and_truncated():
    headline, reason = friendly_error(RuntimeError("x" * 300))
    assert headline == "Download failed."
    assert reason.endswith("...")
    assert len(reason) <= 220


def test_normalize_proxy():
    assert engine.normalize_proxy("127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert engine.normalize_proxy("socks5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert engine.normalize_proxy("  http://p.local:3128 ") == "http://p.local:3128"
    assert engine.normalize_proxy(None) is None
    assert engine.normalize_proxy("") is None
    assert engine.normalize_proxy("   ") is None


def test_parser_accepts_proxy():
    args = cli.build_parser().parse_args(
        ["--proxy", "127.0.0.1:8080", "https://x.test/v"])
    assert args.proxy == "127.0.0.1:8080"


def test_build_options_proxy(tmp_path):
    opts = engine.build_options(tmp_path, "best", proxy="http://127.0.0.1:8080")
    assert opts["proxy"] == "http://127.0.0.1:8080"
    assert "proxy" not in engine.build_options(tmp_path, "best")


def test_downloader_probe_uses_normalized_proxy():
    dl = engine.Downloader(proxy="127.0.0.1:8080")
    captured: dict = {}

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            captured.update(self.__dict__.get("_opts", {}))
            return {"_type": "video", "title": "t",
                    "webpage_url": "https://x.test/v"}

    def fake_ydl_cls(opts):
        instance = FakeYDL(opts)
        instance._opts = opts
        return instance

    dl._ydl_cls = fake_ydl_cls
    dl.probe("https://x.test/v")
    assert captured.get("proxy") == "http://127.0.0.1:8080"


def test_network_failure_hints_at_proxy(fake_engine, capsys, tmp_path,
                                        monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_error = RuntimeError("URLError: timed out")

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 1
    out = capsys.readouterr().out
    assert "--proxy HOST:PORT" in out


def test_network_failure_without_hint_when_proxy_given(fake_engine, capsys,
                                                       tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_error = RuntimeError("URLError: timed out")

    args = cli.build_parser().parse_args(
        ["--proxy", "127.0.0.1:8080", "https://x.test/watch?v=1"])
    assert cli.run_download(args) == 1
    assert "--proxy HOST:PORT" not in capsys.readouterr().out


def test_missing_dependency_hint():
    exc = ModuleNotFoundError("No module named 'yt_dlp'")
    hint = missing_dependency_hint(exc)
    assert hint is not None and "pip install" in hint
    assert missing_dependency_hint(ValueError("other")) is None


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def test_progress_line_renders_bar_and_percent():
    text = output.progress_line(87.0, "My Video", "4.2 MB/s", "00:18")
    assert "87.0%" in text
    assert "█" in text and "░" in text
    assert "My Video" in text and "4.2 MB/s" in text and "ETA 00:18" in text


def test_progress_line_bounds():
    assert output.progress_line(0).count("█") == 0
    assert output.progress_line(100).count("█") == 50
    assert output.progress_line(100).count("░") == 0
    assert output.progress_line(150).count("█") == 50  # clamped


def test_progress_line_unknown_size():
    assert output.progress_line(None, "Song") == "Downloading: Song"
    assert output.download_progress("Song", 10, None) == "Downloading: Song"


def test_download_progress_percent():
    text = output.download_progress("Song", 1000, 2000)
    assert "50.0%" in text


def test_truncate():
    assert output.truncate("short", 10) == "short"
    long = "x" * 100
    cut = output.truncate(long, 20)
    assert len(cut) == 20 and cut.endswith("...")


def test_summary_prints_counts_and_failures(capsys):
    output.summary(18, 2, 1, ["Bad Video"])
    out = capsys.readouterr().out
    assert "Downloaded: 18" in out
    assert "Skipped:    2" in out
    assert "Failed:     1" in out
    assert "- Bad Video" in out


def test_summary_hides_zero_skip_and_fail(capsys):
    output.summary(1, 0, 0, [])
    out = capsys.readouterr().out
    assert "Skipped" not in out and "Failed" not in out


def test_banner(capsys):
    output.show_banner()
    assert "Simple Video Downloader" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Default download directory
# --------------------------------------------------------------------------

def test_default_download_dir_prefers_os_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    assert cli.default_download_dir() == tmp_path / "Downloads"


def test_termux_detection():
    assert cli.is_termux() is ("TERMUX_VERSION" in os.environ)


def test_termux_uses_shared_storage_downloads(tmp_path, monkeypatch):
    """With storage granted, Termux targets the phone's shared Downloads."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    storage = tmp_path / "storage" / "downloads"
    storage.mkdir(parents=True)
    assert cli.default_download_dir() == storage


def test_termux_falls_back_without_storage_permission(tmp_path, monkeypatch):
    """Without termux-setup-storage, an app-private ~/Downloads is used."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    assert cli.default_download_dir() == tmp_path / "Downloads"


def test_termux_storage_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    assert cli.termux_storage_ready() is False
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    (tmp_path / "storage").mkdir()
    assert cli.termux_storage_ready() is True


def test_default_download_dir_creates_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    result = cli.default_download_dir()
    assert (tmp_path / "Downloads").is_dir()
    assert result == tmp_path / "Downloads"


# --------------------------------------------------------------------------
# CLI argument parsing
# --------------------------------------------------------------------------

def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.url is None
    assert args.output is None
    assert args.quality == "best"
    assert args.audio is False
    assert args.verbose is False
    assert args.cookies is None


def test_parser_accepts_url_output_quality():
    args = cli.build_parser().parse_args(
        ["https://x.test/v", "-o", "out", "-q", "720p"])
    assert args.url == "https://x.test/v"
    assert args.output == "out"
    assert args.quality == "720p"


def test_audio_flag_is_shorthand_for_quality_audio():
    args = cli.build_parser().parse_args(["-a", "https://x.test/v"])
    assert cli._quality_from(args) == "audio"


def test_quality_from_without_audio():
    args = cli.build_parser().parse_args(["-q", "480p", "https://x.test/v"])
    assert cli._quality_from(args) == "480p"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
    assert "1.3.0" in capsys.readouterr().out


def test_help_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Simple Video Downloader" in out
    assert "--quality" in out


def test_rejects_invalid_quality():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["-q", "8k", "https://x.test/v"])


def test_parser_accepts_cookies_from_browser():
    args = cli.build_parser().parse_args(
        ["--cookies-from-browser", "firefox", "https://x.test/v"])
    assert args.cookies == "firefox"


def test_parser_accepts_cookies_file():
    args = cli.build_parser().parse_args(
        ["--cookies", "C:\\tmp\\cookies.txt", "https://x.test/v"])
    assert args.cookies_file == "C:\\tmp\\cookies.txt"


def test_cookies_file_probes_with_sign_in(fake_engine, capsys, tmp_path,
                                          monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = _video_info()
    fake_engine.run_results = [{"title": "Hello Video"}]

    args = cli.build_parser().parse_args(
        ["--cookies", "cookies.txt", "https://x.test/watch?v=1"])
    assert cli.run_download(args) == 0

    out = capsys.readouterr().out
    assert "cookies from cookies.txt" in out
    assert "Downloaded: 1" in out


def test_parser_rejects_unknown_browser():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["--cookies-from-browser", "netscape", "https://x.test/v"])


# --------------------------------------------------------------------------
# Download flows with a fake engine
# --------------------------------------------------------------------------

class FakeDownloader(engine.Downloader):
    """Test double standing in for the yt-dlp wrapper."""

    probe_info: dict | None = None
    probe_error: Exception | None = None
    run_results: list | None = None
    run_failures: list | None = None

    def __init__(self, *args, **kwargs):
        pass

    def probe(self, url):
        if self.probe_error is not None:
            raise self.probe_error
        return dict(self.probe_info or {})

    def run(self, url, outdir, quality="best", progress_fn=None):
        return (list(self.run_results or []),
                list(self.run_failures or []))


@pytest.fixture()
def fake_engine(monkeypatch):
    monkeypatch.setattr(engine, "Downloader", FakeDownloader)
    # Reset class-level state so tests cannot leak into each other.
    FakeDownloader.probe_info = None
    FakeDownloader.probe_error = None
    FakeDownloader.run_results = None
    FakeDownloader.run_failures = None
    return FakeDownloader


def _video_info() -> dict:
    return {"_type": "video", "title": "Hello Video",
            "webpage_url": "https://x.test/watch?v=1"}


def test_direct_download_success(fake_engine, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    fake_engine.probe_info = _video_info()
    fake_engine.run_results = [{"title": "Hello Video"}]

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 0

    out = capsys.readouterr().out
    assert "Video: Hello Video" in out
    assert "Downloaded: 1" in out
    assert "Saved to:" in out


def test_direct_download_rejects_invalid_url(fake_engine, capsys):
    args = cli.build_parser().parse_args(["not-a-url"])
    assert cli.run_download(args) == 1
    assert "valid URL" in capsys.readouterr().out


def test_direct_download_probe_failure_is_friendly(fake_engine, capsys, tmp_path,
                                                   monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_error = RuntimeError("ERROR: Video unavailable")

    args = cli.build_parser().parse_args(["https://x.test/watch?v=404"])
    assert cli.run_download(args) == 1

    out = capsys.readouterr().out
    assert "Download failed" in out
    assert "unavailable or private" in out
    assert "Traceback" not in out  # clean output without --verbose


def test_direct_download_verbose_shows_traceback(fake_engine, capsys, tmp_path,
                                                 monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_error = RuntimeError("ERROR: Video unavailable")

    args = cli.build_parser().parse_args(
        ["--verbose", "https://x.test/watch?v=404"])
    assert cli.run_download(args) == 1
    assert "Traceback" in capsys.readouterr().err


def test_direct_download_empty_playlist(fake_engine, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = {"_type": "playlist", "title": "Empty",
                              "webpage_url": "https://x.test/playlist",
                              "entries": []}

    args = cli.build_parser().parse_args(["https://x.test/playlist"])
    assert cli.run_download(args) == 0
    assert "Nothing to download" in capsys.readouterr().out


def test_direct_download_all_already_present(fake_engine, capsys, tmp_path,
                                             monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = _video_info()
    fake_engine.run_results = []

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 0
    assert "Already downloaded" in capsys.readouterr().out


def test_interrupted_download_returns_130(fake_engine, capsys, tmp_path,
                                          monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(output, "ask", lambda *a, **k: True)
    fake_engine.probe_info = _video_info()

    class Interrupted(FakeDownloader):
        def run(self, url, outdir, quality="best", progress_fn=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(engine, "Downloader", Interrupted)

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 130
    assert "Download interrupted." in capsys.readouterr().out


def test_interactive_flow_happy_path(fake_engine, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    fake_engine.probe_info = _video_info()
    fake_engine.run_results = [{"title": "Hello Video"}]
    monkeypatch.setattr("sys.stdin",
                        io.StringIO("https://x.test/watch?v=1\n1\n\n"))

    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Simple Video Downloader" in out      # banner shown
    assert "Video: Hello Video" in out
    assert "Saved to:" in out


def test_direct_download_reports_failed_playlist_items(fake_engine, capsys,
                                                       tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = {"_type": "playlist", "title": "My List",
                              "webpage_url": "https://x.test/playlist",
                              "entries": [{"title": "a"}, {"title": "b"}]}
    fake_engine.run_results = [{"title": "a"}]
    fake_engine.run_failures = [("b", "A network problem occurred.")]

    args = cli.build_parser().parse_args(["https://x.test/playlist"])
    assert cli.run_download(args) == 1

    out = capsys.readouterr().out
    assert "Downloaded: 1" in out
    assert "Failed:     1" in out
    assert "- b" in out
    assert "retry only the failed" in out


def test_interactive_flow_invalid_url(fake_engine, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not a url\n"))
    assert cli.main([]) == 1
    assert "valid URL" in capsys.readouterr().out


def test_age_restricted_download_offers_browser_sign_in(fake_engine, capsys,
                                                        tmp_path, monkeypatch):
    """An age-gated failure offers a cookie sign-in and then succeeds."""
    from yt_dlp.utils import DownloadError

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = _video_info()

    class AgeGated(FakeDownloader):
        run_calls = 0

        def run(self, url, outdir, quality="best", progress_fn=None):
            AgeGated.run_calls += 1
            if AgeGated.run_calls == 1:
                raise DownloadError("ERROR: Sign in to confirm your age")
            return ([{"title": "Hello Video"}], [])

    monkeypatch.setattr(engine, "Downloader", AgeGated)
    # Pretend we are on a real terminal with a user answering yes/chrome.
    monkeypatch.setattr(output, "is_interactive", lambda: True)
    asked: list[str] = []

    def fake_ask(message, **kwargs):
        asked.append(message)
        return True

    monkeypatch.setattr(output, "ask", fake_ask)
    monkeypatch.setattr(output, "prompt",
                        lambda *a, **k: "chrome")

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 0

    out = capsys.readouterr().out
    assert any("Sign in with your browser's cookies" in m for m in asked)
    assert "Signing in with your chrome cookies" in out
    assert "Signed in - access granted" in out
    assert "Downloaded: 1" in out


def test_age_restricted_failure_stays_clean_when_not_interactive(fake_engine,
                                                                 capsys,
                                                                 tmp_path,
                                                                 monkeypatch):
    """No retry offer (and no crash) when there is no terminal to ask."""
    from yt_dlp.utils import DownloadError

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = _video_info()

    class AgeGated(FakeDownloader):
        def run(self, url, outdir, quality="best", progress_fn=None):
            raise DownloadError("ERROR: Sign in to confirm your age")

    monkeypatch.setattr(engine, "Downloader", AgeGated)
    monkeypatch.setattr(output, "is_interactive", lambda: False)

    args = cli.build_parser().parse_args(["https://x.test/watch?v=1"])
    assert cli.run_download(args) == 1
    out = capsys.readouterr().out
    assert "age-restricted" in out.lower()
    assert "cookies-from-browser" in out   # remedy is documented


def test_cookies_flag_probes_with_sign_in(fake_engine, capsys, tmp_path,
                                          monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_info = _video_info()
    fake_engine.run_results = [{"title": "Hello Video"}]

    args = cli.build_parser().parse_args(
        ["--cookies-from-browser", "firefox", "https://x.test/watch?v=1"])
    assert cli.run_download(args) == 0

    out = capsys.readouterr().out
    assert "Signing in with your firefox cookies" in out
    assert "Downloaded: 1" in out


def test_interactive_flow_probe_failure(fake_engine, capsys, tmp_path,
                                        monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake_engine.probe_error = RuntimeError("unsupported URL")
    monkeypatch.setattr("sys.stdin", io.StringIO("https://x.test/thing\n"))

    assert cli.main([]) == 1
    out = capsys.readouterr().out
    assert "Download failed" in out
    assert "Traceback" not in out


def test_keyboard_interrupt_at_prompt_is_clean(capsys, monkeypatch):
    def raising_input(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(output, "prompt", raising_input)
    assert cli.main([]) == 130
    assert "Cancelled." in capsys.readouterr().out


# --------------------------------------------------------------------------
# Filename / existing-file handling (uses real yt-dlp sanitizer)
# --------------------------------------------------------------------------

def test_already_downloaded_true(tmp_path):
    (tmp_path / "My Video.mp4").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)  # no yt-dlp init needed
    assert dl.already_downloaded(tmp_path, "My Video") is True


def test_already_downloaded_false_for_other_titles(tmp_path):
    (tmp_path / "My Video.mp4").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "Other Video") is False


def test_already_downloaded_missing_dir(tmp_path):
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path / "nope", "My Video") is False


def test_already_downloaded_audio_does_not_shadow_video(tmp_path):
    (tmp_path / "My Video.webm").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "My Video", "best") is True
    assert dl.already_downloaded(tmp_path, "My Video", "audio") is False


def test_already_downloaded_video_does_not_shadow_audio(tmp_path):
    (tmp_path / "My Video.mp3").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "My Video", "audio") is True
    assert dl.already_downloaded(tmp_path, "My Video", "best") is False


def test_already_downloaded_ignores_partial_files(tmp_path):
    (tmp_path / "My Video.f401.mp4.part").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "My Video", "best") is False


def test_already_downloaded_ignores_pre_merge_intermediates(tmp_path):
    # "Title.f397.mp4" is a video-only intermediate awaiting its audio
    # stream; it must not count as a finished download.
    (tmp_path / "My Video.f397.mp4").write_bytes(b"x")
    (tmp_path / "My Video.f140.m4a").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "My Video", "best") is False
    assert dl.already_downloaded(tmp_path, "My Video", "best",
                                 numbered=True) is False
    (tmp_path / "My Video.mp4").write_bytes(b"x")
    assert dl.already_downloaded(tmp_path, "My Video", "best") is True


def test_already_downloaded_recognizes_numbered_files(tmp_path):
    (tmp_path / "01 - My Video.mp4").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.already_downloaded(tmp_path, "My Video", "best",
                                 numbered=True) is True
    assert dl.already_downloaded(tmp_path, "My Video", "best") is False


def test_category_folder_sanitizes_title(tmp_path):
    dl = engine.Downloader.__new__(engine.Downloader)
    folder = dl.category_folder(tmp_path, {"title": "My: Cool <List>?"},
                                "playlist")
    assert folder.parent == tmp_path
    assert "My" in folder.name
    assert ":" not in folder.name and "<" not in folder.name and "?" not in folder.name


def test_category_folder_fallback_names(tmp_path):
    dl = engine.Downloader.__new__(engine.Downloader)
    assert dl.category_folder(tmp_path, {}, "channel") == tmp_path / "Channel"
    assert dl.category_folder(tmp_path, {"title": "   "}, "playlist") == \
        tmp_path / "Playlist"


def test_run_routes_playlist_into_numbered_subfolder(tmp_path, monkeypatch):
    dl = engine.Downloader.__new__(engine.Downloader)
    dl.last_target_dir = None
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "playlist", "title": "My List",
        "webpage_url": "https://x.test/playlist?list=PL1",
        "entries": [{"title": "a", "url": "https://x.test/1"},
                    {"title": "b", "url": "https://x.test/2"}]},
        raising=False)
    recorded: list[tuple, ] = []

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        recorded.append((outdir, number_prefix))
        return [{"title": item_label}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    results, failed = dl.run("https://x.test/playlist?list=PL1", tmp_path, "best")

    target = tmp_path / "My List"
    assert dl.last_target_dir == target
    assert target.is_dir()
    assert recorded == [(target, "01 - "), (target, "02 - ")]
    assert len(results) == 2
    assert failed == []


def test_run_playlist_continues_past_failed_items(tmp_path, monkeypatch):
    from yt_dlp.utils import DownloadError

    dl = engine.Downloader.__new__(engine.Downloader)
    dl.last_target_dir = None
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "playlist", "title": "My List",
        "webpage_url": "https://x.test/playlist?list=PL1",
        "entries": [{"title": "good one", "url": "https://x.test/1"},
                    {"title": "bad one", "url": "https://x.test/2"},
                    {"title": "last one", "url": "https://x.test/3"}]},
        raising=False)

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        if item_label == "bad one":
            raise DownloadError("HTTP Error 429: Too Many Requests")
        return [{"title": item_label}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    results, failed = dl.run("https://x.test/playlist?list=PL1", tmp_path, "best")

    assert len(results) == 2                    # good one + last one
    assert failed == [("bad one", "The site is rate limiting requests.")]


def test_run_numbers_follow_playlist_positions_after_resume(tmp_path,
                                                             monkeypatch):
    # Item 1 is already downloaded; the remaining items must keep their
    # global playlist numbers (02, 03), not renumber from 01.
    dl = engine.Downloader.__new__(engine.Downloader)
    dl.last_target_dir = None
    target = tmp_path / "My List"
    target.mkdir()
    (target / "01 - first.mp4").write_bytes(b"x")
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "playlist", "title": "My List",
        "webpage_url": "https://x.test/playlist?list=PL1",
        "entries": [{"title": "first", "url": "https://x.test/1"},
                    {"title": "second", "url": "https://x.test/2"},
                    {"title": "third", "url": "https://x.test/3"}]},
        raising=False)
    recorded: list[str] = []

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        recorded.append(number_prefix)
        return [{"title": item_label}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    dl.run("https://x.test/playlist?list=PL1", tmp_path, "best")

    assert recorded == ["02 - ", "03 - "]


def test_run_single_video_failure_propagates(tmp_path, monkeypatch):
    from yt_dlp.utils import DownloadError

    dl = engine.Downloader.__new__(engine.Downloader)
    dl.last_target_dir = None
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "video", "title": "Hello Video",
        "webpage_url": "https://x.test/watch?v=1"}, raising=False)

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        raise DownloadError("HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    with pytest.raises(DownloadError):
        dl.run("https://x.test/watch?v=1", tmp_path, "best")


def test_run_single_video_stays_in_top_folder(tmp_path, monkeypatch):
    dl = engine.Downloader.__new__(engine.Downloader)
    dl.last_target_dir = None
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "video", "title": "Hello Video",
        "webpage_url": "https://x.test/watch?v=1"}, raising=False)
    recorded: list[tuple, ] = []

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        recorded.append((outdir, number_prefix))
        return [{"title": "Hello Video"}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    dl.run("https://x.test/watch?v=1", tmp_path, "best")

    assert recorded == [(tmp_path, "")]


def test_run_skips_existing_single_video(tmp_path, monkeypatch):
    (tmp_path / "Hello Video.mp4").write_bytes(b"x")
    dl = engine.Downloader.__new__(engine.Downloader)
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "video", "title": "Hello Video",
        "webpage_url": "https://x.test/watch?v=1"}, raising=False)
    calls = {"download": 0}

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label=""):
        calls["download"] += 1
        return [{"title": "Hello Video"}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    assert dl.run("https://x.test/watch?v=1", tmp_path, "best") == ([], [])
    assert calls["download"] == 0


def test_progress_reporter_throttles_to_ten_percent_steps(capsys):
    reporter = cli._ProgressReporter("My Video")
    reporter("downloading", 50, 1000)     # 5%  -> no line
    assert capsys.readouterr().out == ""
    reporter("downloading", 100, 1000)    # 10% -> one line
    first = capsys.readouterr().out
    assert "10.0%" in first
    reporter("downloading", 150, 1000)    # 15% -> same bucket, no line
    assert capsys.readouterr().out == ""
    reporter("downloading", 990, 1000)    # 99% -> one line
    assert "99.0%" in capsys.readouterr().out


def test_progress_reporter_item_resets_and_done_prints_once(capsys):
    reporter = cli._ProgressReporter("First")
    reporter("done", 100, 100)
    assert "Finished: First" in capsys.readouterr().out
    reporter("done", 100, 100)            # not printed twice
    assert capsys.readouterr().out == ""
    reporter("item", 2, 5, "Second Video")
    reporter("done", 10, 10)
    assert "Finished: Second Video" in capsys.readouterr().out


def test_run_downloads_when_file_absent(tmp_path, monkeypatch):
    dl = engine.Downloader.__new__(engine.Downloader)
    monkeypatch.setattr(dl, "probe", lambda url: {
        "_type": "video", "title": "Hello Video",
        "webpage_url": "https://x.test/watch?v=1"}, raising=False)

    def fake_download(url, outdir, quality="best", progress_fn=None,
                      item_label="", number_prefix=""):
        return [{"title": "Hello Video"}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    results, failed = dl.run("https://x.test/watch?v=1", tmp_path, "best")
    assert results == [{"title": "Hello Video"}]
    assert failed == []
