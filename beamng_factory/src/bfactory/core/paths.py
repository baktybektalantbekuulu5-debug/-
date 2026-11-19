"""Well-known filesystem locations of the application."""

from __future__ import annotations

from pathlib import Path

#: beamng_factory/ folder (the application root).
APP_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = APP_ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
PROJECTS_DIR = APP_ROOT / "projects"
LOGS_DIR = APP_ROOT / "logs"
TOOLS_DIR = APP_ROOT / "tools"
ASSETS_DIR = APP_ROOT / "assets"


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, PROJECTS_DIR, LOGS_DIR, TOOLS_DIR):
        d.mkdir(parents=True, exist_ok=True)
