from __future__ import annotations
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_settings(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config" / "settings.toml"
    with open(path, "rb") as f:
        s = tomllib.load(f)
    return s


def resolve(settings: dict, key: str) -> Path:
    """Resolve a [paths] entry relative to the project root."""
    p = Path(settings["paths"][key])
    return p if p.is_absolute() else ROOT / p
