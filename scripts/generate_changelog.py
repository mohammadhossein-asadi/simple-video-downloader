#!/usr/bin/env python3
"""Generate CHANGELOG.md from the git tag/commit history.

Reproducible documentation: re-run after tagging a new version and the
changelog reflects the real repository state. The release workflow uses
``--notes-for VERSION`` to produce the notes for a single release.

The mapping is commit-prefix based, matching the repository's
conventional style (feat: / fix: / docs: / chore:).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPO_URL = "https://github.com/mohammadhossein-asadi/simple-video-downloader"

GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Features", ("feat:",)),
    ("Fixes", ("fix:",)),
    ("Documentation", ("docs:",)),
    ("Chores", ("chore:",)),
]


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def versions() -> list[tuple[str, str, set[str]]]:
    """Return ``(tag, date, commit_hashes)`` oldest to newest.

    ``commit_hashes`` is every non-merge commit reachable from the tag;
    per-version sections are derived by set difference. Each tag is
    resolved to its commit with ``rev-parse tag^{commit}``, which works
    for annotated and lightweight tags alike.
    """
    lines = _git(
        "tag", "--sort=creatordate",
        "--format=%(refname:short)%09%(creatordate:short)",
    ).splitlines()
    result: list[tuple[str, str, set[str]]] = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 2:
            continue
        tag, date = fields
        commit = _git("rev-parse", f"{tag}^{{commit}}")
        hashes = set(_git("rev-list", commit, "--no-merges").split())
        result.append((tag, date, hashes))
    return result


def subjects(hashes: set[str]) -> dict[str, str]:
    """Map commit hash -> subject line."""
    if not hashes:
        return {}
    out: dict[str, str] = {}
    for line in _git("log", "--no-walk", "--format=%H%x09%s",
                     *sorted(hashes)).splitlines():
        commit_hash, subject = line.split("\t", 1)
        out[commit_hash] = subject
    return out


def classify(subject: str) -> str:
    for group, prefixes in GROUPS:
        if any(subject.startswith(prefix) for prefix in prefixes):
            return group
    return "Other changes"


def version_sections(tag: str, date: str, hashes: list[str]) -> list[str]:
    """Render one version block (without the ``## `` heading)."""
    lines: list[str] = []
    grouped: dict[str, list[str]] = {}
    for commit_hash in hashes:
        subject = subjects({commit_hash}).get(commit_hash, "")
        if not subject:
            continue
        grouped.setdefault(classify(subject), []).append(
            f"- {subject} (`{commit_hash[:7]}`)")
    for group, _prefixes in GROUPS:
        entries = grouped.pop(group, [])
        if entries:
            lines.append(f"### {group}")
            lines.extend(entries)
            lines.append("")
    for group, entries in grouped.items():  # any unlisted group names
        lines.append(f"### {group}")
        lines.extend(entries)
        lines.append("")
    if not lines:
        lines = ["_Maintenance release._", ""]
    _ = tag  # tag equals the heading rendered by the caller
    return lines


def generate() -> str:
    """Render the full CHANGELOG.md content."""
    out = ["# Changelog", "",
           "All notable changes, generated from the commit history by "
           "`scripts/generate_changelog.py`. Do not edit by hand.", ""]
    history = versions()
    previous: set[str] = set()
    for tag, date, all_hashes in history:
        own = sorted(all_hashes - previous)
        previous |= all_hashes
        out.append(f"## {tag} - {date}")
        out.append("")
        out.extend(version_sections(tag, date, own))
    return "\n".join(out).rstrip() + "\n"


def notes_for(version: str) -> str:
    """Render only the sections for *version* (release notes body)."""
    history = versions()
    previous: set[str] = set()
    for tag, date, all_hashes in history:
        own = sorted(all_hashes - previous)
        previous |= all_hashes
        if tag == version:
            return "\n".join(version_sections(tag, date, own)).rstrip() + "\n"
    raise SystemExit(f"error: tag {version!r} not found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes-for", metavar="VERSION", dest="notes_for",
                        help="print release notes for one version, e.g. v1.4.0")
    args = parser.parse_args()

    if args.notes_for:
        print(notes_for(args.notes_for), end="")
        return 0

    target = ROOT / "CHANGELOG.md"
    content = generate()
    target.write_text(content, encoding="utf-8")
    print(f"Wrote {target} ({len(content):,} chars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
