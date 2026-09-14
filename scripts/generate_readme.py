#!/usr/bin/env python3
"""Generate README.md from structured project information.

The README is reproducible: run ``python scripts/generate_readme.py``
after any change that affects the CLI, features, or docs so the
documentation can never drift from the implementation. The ``--help``
section is captured from the real argument parser.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from video_downloader import __version__  # noqa: E402
from video_downloader.cli import build_parser  # noqa: E402

PROJECT = {
    "name": "Simple Video Downloader",
    "package": "simple-video-downloader",
    "version": __version__,
    "repo": "https://github.com/mohammadhossein-asadi/simple-video-downloader",
    "description": ("A simple, friendly command-line tool to download videos, "
                    "playlists, and channels. No configuration, no accounts, "
                    "no AI - just paste a URL."),
}


def cli_help() -> str:
    """Capture the actual --help text from the real parser."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        try:
            build_parser().parse_args(["--help"])
        except SystemExit:
            pass
    return buffer.getvalue().strip()


README_TEMPLATE = """# {name}

{description}

Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Single video, playlist, and channel downloads from one simple URL prompt
- Interactive mode by default; direct one-shot usage from the command line
- Quality menu with **Best** as the safe default (plus 1080p / 720p / 480p)
- Audio-only downloads saved as mp3
- Automatic resume of interrupted downloads and safe skip of existing files
- Live progress bars with size, speed, and ETA
- Sequential playlist/channel downloads with a final summary
  (downloaded / skipped / failed) - one broken video never stops the batch
- Plain-English error messages; full detail only with `--verbose`
- Cross-platform: Windows, macOS, and Linux

## Requirements

- Python **3.10+**
- [ffmpeg](https://ffmpeg.org) on your PATH (used to merge the best video +
  audio streams and to convert audio-only downloads)

### Installing ffmpeg

- **Windows:** `winget install ffmpeg` (or download from ffmpeg.org and add
  the `bin` folder to your PATH)
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg` (or your distribution's equivalent)

## Installation

```bash
pip install {package}
```

Or from a clone of this repository:

```bash
pip install .
```

## Usage

### Interactive mode (recommended)

Run the tool without arguments:

```bash
video-downloader
```

```
╭──────────────────────────────────────╮
│        Simple Video Downloader       │
╰──────────────────────────────────────╯

Enter video, playlist, or channel URL: https://example.com/playlist
Playlist: Example Playlist (12 videos)

  1. Best available quality (default)
  2. 1080p
  3. 720p
  4. 480p
  5. Audio only (mp3)
Select [1-5] (Enter = best):
Download folder [C:\\Users\\you\\Downloads]:
```

Press Enter at any prompt to accept the default. That is the whole flow.

### Command-line mode

```bash
# Best quality into your Downloads folder
video-downloader "https://www.youtube.com/watch?v=VIDEO_ID"

# A whole playlist
video-downloader "https://www.youtube.com/playlist?list=PLAYLIST_ID"

# A channel
video-downloader "https://www.youtube.com/@SomeChannel"

# 720p into a specific folder
video-downloader "https://example.com/video" --quality 720p --output D:\\Videos

# Audio only (mp3)
video-downloader "https://example.com/video" --audio
```

### Command-line options

```text
{help_text}
```

## Quality selection

| Choice | What you get |
|---|---|
| Best *(default)* | Highest available video + audio quality |
| 1080p / 720p / 480p | Capped at that height, best quality at or below it |
| Audio only | Best audio stream, converted to mp3 (needs ffmpeg) |

You are never asked about codecs, containers, or stream formats.

## Output directory

- Default: your operating system's standard **Downloads** folder
- Override per run with `--output DIR` (or answer the folder prompt)
- The folder is created automatically if it does not exist

## Playlists and channels

The tool detects what kind of URL you pasted and shows the item count.
Items are downloaded one at a time with overall progress:

```text
Playlist: Example Playlist (12 videos)

[3/12]
Downloading: Example Video #3
[██████████████░░░░░░░░░░░░░░] 71.0%  245.0 MB
```

If an individual video fails, the run continues and a summary is printed
at the end:

```text
Playlist completed.
  ✓ Downloaded: 10
  ↷ Skipped:    1
  ✗ Failed:     1
    - Some Unavailable Video
```

Simply re-run the same command afterwards: files that already downloaded
are skipped, so only the missing items are fetched.

## Interrupted downloads

Partial downloads (`.part` files) are kept. Re-run the same command and
the download resumes where it stopped instead of starting over.

## Troubleshooting

| Message | What it means / what to do |
|---|---|
| *This content is private or requires sign-in* | The video is private, members-only, or the site requires a login. Such content cannot be downloaded. |
| *The video is unavailable or private* | The content was removed or the URL is mistyped. Verify the link. |
| *This content is age-restricted* | Age-restricted content needs an account and cannot be fetched anonymously. |
| *The site is rate limiting requests* | Too many requests in a short time. Wait a few minutes and retry. |
| *A network problem occurred* | Check your internet connection and retry. |
| *The ffmpeg tool is missing* | Install ffmpeg (see Requirements) and make sure `ffmpeg -version` works in a terminal. |
| *Not enough disk space* | Free up space on the target drive. |
| *Permission denied* | Pick a folder you are allowed to write to. |
| *This URL is not supported* | The site is not a recognized media source. Double-check the URL. |

Run any failing command again with `--verbose` to see the full technical
error, which helps when filing an issue.

## Development

```bash
git clone {repo}
cd simple-video-downloader
python -m venv .venv
.venv\\Scripts\\activate        # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
pytest
```

The test suite covers URL validation, URL classification, quality/format
selection, safe default options, friendly error mapping, output
rendering, default-directory resolution, CLI parsing, and the interactive
and direct download flows (via a fake downloader - no network needed).

### Regenerating the README

`README.md` is generated - do not edit it by hand:

```bash
python scripts/generate_readme.py
```

## Project structure

```text
simple-video-downloader/
├── src/video_downloader/
│   ├── __init__.py     # package version
│   ├── __main__.py     # python -m video_downloader
│   ├── cli.py          # argument parsing + interactive flow
│   ├── engine.py       # yt-dlp wrapper: options, probe, download
│   ├── urlinfo.py      # URL validation + classification
│   ├── errors.py       # friendly error messages
│   └── output.py       # banner, prompts, progress, summary
├── tests/              # pytest suite
├── scripts/
│   └── generate_readme.py
├── pyproject.toml
├── LICENSE
└── README.md
```

## Legal / copyright notice

This tool is intended for content you are legally permitted to download,
such as your own uploads, public-domain or openly licensed media, or
content whose license allows downloading. You are responsible for
complying with:

- Copyright law in your jurisdiction
- The terms of service of the platform you download from
- The license of the content itself
- Any other applicable local regulations

The authors do not encourage or support downloading copyrighted material
without permission.

## License

[MIT](LICENSE) © 2026 mohammadhossein-asadi
"""


def main() -> int:
    readme = ROOT / "README.md"
    help_text = cli_help()
    content = README_TEMPLATE.format(name=PROJECT["name"],
                                     description=PROJECT["description"],
                                     package=PROJECT["package"],
                                     repo=PROJECT["repo"],
                                     help_text=help_text)
    readme.write_text(content, encoding="utf-8")
    print(f"Wrote {readme} ({len(content):,} chars, CLI help embedded).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
