"""Application settings stored in config/settings.toml.

The file is created automatically by the PC check (doctor) with values it
detected on this computer; the user never has to edit it by hand.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import paths


class GameSettings(BaseModel):
    home: str = ""                 # BeamNG.drive install folder
    user_folder: str = ""          # optional custom userpath
    host: str = "localhost"
    port: int = 25252
    tech_enabled: bool = False
    default_level: str = "west_coast_usa"


class CaptureSettings(BaseModel):
    ffmpeg: str = ""               # path to ffmpeg.exe
    encoder: str = "libx264"       # h264_nvenc / h264_amf / h264_qsv / libx264
    fps: int = 60
    grabber: str = "gdigrab"


class LLMSettings(BaseModel):
    enabled: bool = False
    api_key: str = ""


class Settings(BaseModel):
    game: GameSettings = Field(default_factory=GameSettings)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


def load(path: Path = paths.SETTINGS_FILE) -> Settings:
    if not path.is_file():
        return Settings()
    with path.open("rb") as f:
        return Settings.model_validate(tomllib.load(f))


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def save(settings: Settings, path: Path = paths.SETTINGS_FILE) -> None:
    """Write settings as TOML (flat tables of scalars only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, table in settings.model_dump().items():
        lines.append(f"[{section}]")
        lines += [f"{k} = {_toml_value(v)}" for k, v in table.items()]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
