"""Opt-in settings file, remembered only when the user asks for it.

The file is never created automatically: it is written when the user
accepts the "remember these settings?" prompt (or saves them via the
API below). CLI flags always take precedence over saved values, and
``--no-config`` ignores the file entirely for one run.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

KNOWN_KEYS = ("quality", "output", "proxy")


def config_path() -> Path:
    """Platform-appropriate location of the settings file."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "video-downloader" / "config.toml"


def load_config(path: Path) -> dict:
    """Read known settings from *path*; missing/corrupt files yield {}."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in KNOWN_KEYS
            if isinstance(data.get(key), str) and data[key]}


def _toml_str(value: str) -> str:
    """Escape *value* as a TOML basic string (backslashes included)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_config(path: Path, settings: dict) -> Path:
    """Write the known, non-empty keys of *settings* to *path*."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key} = {_toml_str(str(settings[key]))}"
             for key in KNOWN_KEYS if settings.get(key)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
