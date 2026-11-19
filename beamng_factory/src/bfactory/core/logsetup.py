"""Logging to console and to a rotating file in logs/."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths


def setup(name: str = "bfactory", level: int = logging.INFO) -> logging.Logger:
    paths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        fh = RotatingFileHandler(paths.LOGS_DIR / f"{name}.log", maxBytes=5_000_000,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        ch.setLevel(level)
        root.addHandler(fh)
        root.addHandler(ch)
        root.setLevel(logging.DEBUG)
        # beamngpy is very chatty on DEBUG; keep it in the file only.
        logging.getLogger("beamngpy").setLevel(logging.INFO)
    return logging.getLogger(name)
