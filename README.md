# Simple Video Downloader

A simple, friendly command-line tool to download videos, playlists, and channels. No configuration, no accounts, no AI - just paste a URL.

Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Single video, playlist, and channel downloads from one simple URL prompt
- Interactive mode by default; direct one-shot usage from the command line
- Videos are always saved as **.mp4** (mp4-native streams preferred,
  others remuxed without re-encoding; audio-only saves **.mp3**)
- Quality menu with **Best** as the safe default (plus 1080p / 720p / 480p)
- Automatic resume of interrupted downloads and safe skip of existing files
- Live progress bars with size, speed, and ETA
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

## Installation

Requires [Python 3.10+](https://www.python.org/downloads/) and
[ffmpeg](https://ffmpeg.org) on your PATH (see below).

Install directly from this repository:

```bash
pip install git+https://github.com/mohammadhossein-asadi/simple-video-downloader.git
```

Or from a local clone:

```bash
git clone https://github.com/mohammadhossein-asadi/simple-video-downloader
cd simple-video-downloader
pip install .
```

The `video-downloader` command is then available in any terminal. To
update later, re-run the same `pip install` command.

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
Download folder [C:\Users\you\Downloads]:
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
video-downloader "https://example.com/video" --quality 720p --output D:\Videos

# Audio only (mp3)
video-downloader "https://example.com/video" --audio

# Age-restricted content: sign in via your browser's cookies
video-downloader "https://www.youtube.com/watch?v=VIDEO_ID" --cookies-from-browser chrome

# ...or with a cookies.txt file (Netscape format)
video-downloader "https://www.youtube.com/watch?v=VIDEO_ID" --cookies C:\path\cookies.txt
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

### Command-line options

```text
usage: video-downloader [-h] [-o DIR] [-q {best,1080p,720p,480p,audio}] [-a]
                        [--cookies-from-browser BROWSER] [--cookies FILE]
                        [--verbose] [-V]
                        [url]

Simple Video Downloader - download videos, playlists, and channels with one
URL.

positional arguments:
  url                   video, playlist, or channel URL

options:
  -h, --help            show this help message and exit
  -o, --output DIR      download directory (default: your Downloads folder)
  -q, --quality {best,1080p,720p,480p,audio}
                        quality preference (default: best)
  -a, --audio           audio only, saved as mp3 (shorthand for --quality
                        audio)
  --cookies-from-browser BROWSER
                        sign in with a browser's cookies, for age-restricted
                        or private content (chrome, firefox, edge, brave,
                        safari, chromium, opera, vivaldi, whale)
  --cookies FILE        sign in with a cookies.txt file (Netscape format), as
                        an alternative to --cookies-from-browser
  --verbose             show detailed error information
  -V, --version         show program's version number and exit

Run without arguments for interactive mode.
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

## Interrupted downloads

Partial downloads (`.part` files) are kept. Re-run the same command and
the download resumes where it stopped instead of starting over.

## Troubleshooting

| Message | What it means / what to do |
|---|---|
| *This content is private or requires sign-in* | The video is private or members-only, or the site wants verification. If you have access to it, retry with `--cookies-from-browser <browser>` (see *Restricted or private content* above). |
| *The video is unavailable or private* | The content was removed or the URL is mistyped. Verify the link. |
| *This content is age-restricted* | Age-restricted content needs a signed-in session. Retry with `--cookies-from-browser <browser>` for a browser where you are logged in. |
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
git clone https://github.com/mohammadhossein-asadi/simple-video-downloader
cd simple-video-downloader
python -m venv .venv
.venv\Scripts\activate        # Windows  (macOS/Linux: source .venv/bin/activate)
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
