# Changelog

All notable changes, generated from the commit history by `scripts/generate_changelog.py`. Do not edit by hand.

## v1.0.0 - 2026-09-15

### Features
- feat: build simple video downloader (`c264e47`)

## v1.0.1 - 2026-09-15

### Fixes
- fix: wire live progress display and harden output on Windows consoles (`46142d3`)
- fix: force UTF-8 output so non-Latin titles render correctly (`68d3f09`)

## v1.1.0 - 2026-09-15

### Features
- feat: browser-cookie sign-in for age-restricted and private content (`79a90bb`)
- feat: save videos as mp4 and organize playlists into numbered folders (`eae2b24`)

### Documentation
- docs: fix installation instructions to install from this repository (`94d45e2`)

## v1.2.0 - 2026-09-15

### Features
- feat: Termux (Android) support and platform documentation (`efbdda9`)

## v1.3.0 - 2026-09-15

### Features
- feat: add --proxy option for VPN and proxy routing (`89b9761`)

## v1.4.0 - 2026-09-15

### Features
- feat: v1.4.0 - speed/ETA, download archive, subs, preview, config, CI (`fb1c477`)

### Fixes
- fix: use tomli backport on Python 3.10 for the settings file (`e9459cb`)
- fix: don't count archive-skipped playlist items as downloads (`f5f4509`)
