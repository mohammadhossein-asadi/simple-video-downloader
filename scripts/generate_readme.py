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

[![CI](https://github.com/mohammadhossein-asadi/simple-video-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammadhossein-asadi/simple-video-downloader/actions/workflows/ci.yml)

{description}

Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Single video, playlist, and channel downloads from one simple URL prompt
- Interactive mode by default; direct one-shot usage from the command line
- Videos are always saved as **.mp4** (mp4-native streams preferred,
  others remuxed without re-encoding; audio-only saves **.mp3**)
- Quality menu with **Best** as the safe default (plus 1080p / 720p / 480p)
- Automatic resume of interrupted downloads and safe skip of existing files
- Live progress bars with size, speed, and ETA
- Optional subtitle downloads (`--subs en,fa`) saved next to the video
- `--list` preview: see the available qualities before downloading
- Playlists and channels remember finished items in a hidden archive
  file, so re-runs never fetch the same video twice
- Optional one-keypress "remember these settings" (quality, folder,
  proxy) with `--no-config` to ignore them for a run
- Playlists and channels are organized into their own subfolder
  (`Downloads/<Playlist Title>/`) with numbered files (`01 - Title.mp4`)
  numbered by playlist position, stable across resumed runs
- A failed item never stops the batch: the summary reports
  downloaded / failed items and re-running retries only the failures
- Age-restricted or private content: sign in through your own browser's
  cookies (`--cookies-from-browser chrome` or the interactive offer)
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
- **Termux (Android):** `pkg install ffmpeg`

## Platform support

Works on **Windows**, **macOS**, **Linux**, and **Termux on Android**.
The same commands and options behave identically everywhere, and the
default download folder follows each platform's convention:

| Platform | Default download folder |
|---|---|
| Windows | `C:\\Users\\you\\Downloads` |
| macOS | `/Users/you/Downloads` |
| Linux | `/home/you/Downloads` |
| Termux (Android) | The phone's shared `Downloads` folder after running `termux-setup-storage` once; otherwise the app-private `~/Downloads` |

## Installation

Requires [Python 3.10+](https://www.python.org/downloads/) and
[ffmpeg](https://ffmpeg.org) on your PATH (see below).

Install directly from this repository:

```bash
pip install git+https://github.com/mohammadhossein-asadi/simple-video-downloader.git
```

Or from a local clone:

```bash
git clone {repo}
cd simple-video-downloader
pip install .
```

The `video-downloader` command is then available in any terminal. To
update later, re-run the same `pip install` command.

### Termux (Android) install

Install [Termux from F-Droid](https://f-droid.org/en/packages/com.termux/)
(the GitHub build is also fine; the Play Store build is outdated), then:

```bash
pkg update
pkg install python ffmpeg
termux-setup-storage        # allow the permission popup
pip install git+https://github.com/mohammadhossein-asadi/simple-video-downloader.git
```

`termux-setup-storage` links the phone's shared storage into Termux so
videos land in the normal **Downloads** folder you see in any file
manager app. If `pip` refuses to install, use a small virtual
environment instead:

```bash
python -m venv ~/video-downloader-env
~/video-downloader-env/bin/pip install git+https://github.com/mohammadhossein-asadi/simple-video-downloader.git
~/video-downloader-env/bin/video-downloader
```

Everything else - the interactive menu, quality choices, playlists,
channels, and the mp4 output - works exactly as on the desktop.

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

# Age-restricted content: sign in via your browser's cookies
video-downloader "https://www.youtube.com/watch?v=VIDEO_ID" --cookies-from-browser chrome

# ...or with a cookies.txt file (Netscape format)
video-downloader "https://www.youtube.com/watch?v=VIDEO_ID" --cookies C:\\path\\cookies.txt

# Route through a VPN/proxy (local or remote)
video-downloader "URL" --proxy 127.0.0.1:8080
video-downloader "URL" --proxy socks5://127.0.0.1:1080

# Subtitles saved next to the video
video-downloader "URL" --subs en,fa

# Preview the available qualities without downloading
video-downloader "URL" --list
```

### Restricted or private content

Some videos (typically age-restricted ones) can only be accessed while
signed in. The tool never stores credentials: it borrows the login
cookies already saved in your own browser, on your machine, for the
download only.

```bash
# Explicitly, in one command:
video-downloader "URL" --cookies-from-browser chrome

# Or interactively: when a download fails because the content requires
# sign-in, the tool offers to retry using your browser's cookies.
```

Supported browsers: `chrome`, `firefox`, `edge`, `brave`, `safari`,
`chromium`, `opera`, `vivaldi`, `whale`. Use the browser where you are
logged in to the site. Cookies stay on your computer and are never
sent anywhere except to the site hosting the video.

If reading the browser's cookie store fails, export a cookies file with
a browser extension (search for "Get cookies.txt") and pass it instead:

```bash
video-downloader "URL" --cookies cookies.txt
```

> **Chrome/Edge note:** while the browser is running, its cookie
> database can be locked or unreadable. Close it completely and retry,
> or use the cookies-file method above.

### Using a VPN or proxy

On networks where some sites are blocked, route the download through
your VPN's or proxy's local port with `--proxy`. The flag accepts a
bare `HOST:PORT` (treated as HTTP) or a full URL with a scheme:

```bash
video-downloader "URL" --proxy 127.0.0.1:8080          # HTTP proxy
video-downloader "URL" --proxy socks5://127.0.0.1:1080 # SOCKS5 (v2ray, Tor, ...)
video-downloader "URL" --proxy http://user:pass@proxy.example.com:3128
```

Without an explicit `--proxy`, the tool follows your system's standard
proxy environment variables (`HTTP_PROXY` / `HTTPS_PROXY`), so a global
VPN in TUN mode or a system-wide proxy needs no flag at all. When a
download fails because the site cannot be reached, the error output
suggests `--proxy` automatically.

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
[██████████████░░░░░░░░░░░░░░] 71.0%  245.0 MB  4.2 MB/s  ETA 00:18
```

Files are saved into a folder named after the playlist or channel, with
numbers matching each item's position in the list:

```text
Downloads/
└── Top Trending Videos of the Week/
    ├── 01 - First Video Title.mp4
    ├── 02 - Second Video Title.mp4
    └── 03 - Third Video Title.mp4
```

If an individual video fails, the run continues and a summary is printed
at the end:

```text
Playlist completed.
  ✓ Downloaded: 10
  ✗ Failed:     1
    - Some Unavailable Video
```

Simply re-run the same command afterwards: finished files are skipped,
so only the missing items are fetched - numbering stays stable.

## Subtitles

Pass `--subs` with a comma-separated language list to save subtitles
next to the video (same folder and numbering rules):

```bash
video-downloader "URL" --subs en,fa
```

If the site provides no manual subtitle for a language, automatically
generated ones are used as a fallback.

## Previewing qualities

`--list` shows what a URL offers without downloading anything:

```text
$ video-downloader "URL" --list
Title: Example Video
Available qualities: 1080p, 720p, 480p, 360p
```

In interactive mode the quality menu is annotated with the real
available heights when they are known.

## Remembered settings

After a successful interactive run the tool may ask *"Remember these
settings for future runs?"* - answering yes stores quality, output
folder, and proxy in a small file (`%%APPDATA%%\\video-downloader\\config.toml`
on Windows, `~/.config/video-downloader/config.toml` elsewhere). The
file is only ever created by explicit consent. Command-line flags
always override saved settings, and `--no-config` ignores the file for
one run.

## Interrupted downloads

Partial downloads (`.part` files) are kept. Re-run the same command and
the download resumes where it stopped instead of starting over.
Finished playlist/channel items are also recorded in a hidden
`.downloaded-archive` file inside their folder, so later runs skip them
even if the files were renamed or moved.

## Troubleshooting

| Message | What it means / what to do |
|---|---|
| *This content is private or requires sign-in* | The video is private or members-only, or the site wants verification. If you have access to it, retry with `--cookies-from-browser <browser>` (see *Restricted or private content* above). |
| *The video is unavailable or private* | The content was removed or the URL is mistyped. Verify the link. |
| *This content is age-restricted* | Age-restricted content needs a signed-in session. Retry with `--cookies-from-browser <browser>` for a browser where you are logged in. |
| *The site is rate limiting requests* | Too many requests in a short time. Wait a few minutes and retry. |
| *A network problem occurred* | Check your internet connection and retry. If you use a VPN or proxy, also pass `--proxy HOST:PORT` (see *Using a VPN or proxy*). |
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
