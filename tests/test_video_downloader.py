"""Tests for urlinfo, errors, engine options, output, and CLI flows."""

from __future__ import annotations

import io

import pytest

from video_downloader import cli, engine, output, urlinfo
from video_downloader.errors import friendly_error, missing_dependency_hint


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
    assert engine.QUALITY_FORMATS["best"] == "bestvideo*+bestaudio/best"
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
    assert "postprocessors" not in opts
    assert isinstance(opts["logger"], engine._QuietLogger)


def test_build_options_audio_postprocessor(tmp_path):
    opts = engine.build_options(tmp_path, "audio")
    assert opts["format"] == "bestaudio/best"
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert "FFmpegExtractAudio" in keys


def test_build_options_quiet_disables_hooks(tmp_path):
    opts = engine.build_options(tmp_path, "best",
                                progress_fn=lambda *a: None, quiet=True)
    assert opts["progress_hooks"] == []


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
    headline, _ = friendly_error(RuntimeError("This video is age restricted"))
    assert "age-restricted" in headline.lower()


def test_friendly_error_unknown_is_generic_and_truncated():
    headline, reason = friendly_error(RuntimeError("x" * 300))
    assert headline == "Download failed."
    assert reason.endswith("...")
    assert len(reason) <= 220


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
    assert "1.0.0" in capsys.readouterr().out


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


# --------------------------------------------------------------------------
# Download flows with a fake engine
# --------------------------------------------------------------------------

class FakeDownloader(engine.Downloader):
    """Test double standing in for the yt-dlp wrapper."""

    probe_info: dict | None = None
    probe_error: Exception | None = None
    run_results: list | None = None

    def __init__(self, *args, **kwargs):
        pass

    def probe(self, url):
        if self.probe_error is not None:
            raise self.probe_error
        return dict(self.probe_info or {})

    def run(self, url, outdir, quality="best", progress_fn=None):
        return list(self.run_results or [])


@pytest.fixture()
def fake_engine(monkeypatch):
    monkeypatch.setattr(engine, "Downloader", FakeDownloader)
    # Reset class-level state so tests cannot leak into each other.
    FakeDownloader.probe_info = None
    FakeDownloader.probe_error = None
    FakeDownloader.run_results = None
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


def test_interactive_flow_invalid_url(fake_engine, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not a url\n"))
    assert cli.main([]) == 1
    assert "valid URL" in capsys.readouterr().out


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
    assert dl.run("https://x.test/watch?v=1", tmp_path, "best") == []
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
                      item_label=""):
        return [{"title": "Hello Video"}]

    monkeypatch.setattr(dl, "download", fake_download, raising=False)
    result = dl.run("https://x.test/watch?v=1", tmp_path, "best")
    assert result == [{"title": "Hello Video"}]
