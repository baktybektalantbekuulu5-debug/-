"""AI Environment: что установлено в игре, точки старта, подготовка сцены."""
import math
import re
from pathlib import Path

from core.logger import get_logger
from ai_director.catalog import Catalog

log = get_logger("env")


class GameContent:
    """Сканирует установленную BeamNG.drive: машины и карты (папки или zip в content/)."""

    def __init__(self, home: str | None):
        self.home = Path(home) if home else None
        self.cars: set[str] | None = None
        self.levels: set[str] | None = None
        self.version = ""
        if self.home and self.home.exists():
            self.cars = self._scan(self.home / "content" / "vehicles")
            self.levels = self._scan(self.home / "content" / "levels")
            vf = self.home / "version.txt"
            if vf.exists():
                self.version = vf.read_text(errors="ignore").strip()[:40]

    @staticmethod
    def _scan(d: Path):
        if not d.exists():
            return None
        out = set()
        for p in d.iterdir():
            out.add(p.stem if p.suffix.lower() == ".zip" else p.name)
        return out

    @property
    def known(self):
        return self.cars is not None and self.levels is not None


def resolve_start(catalog: Catalog, scene) -> tuple[tuple, float, str]:
    """(pos, yaw, source) для сцены. start_override > карта из каталога/калибровки."""
    sp = scene.start_override
    m = catalog.map(scene.map)
    if not sp and m:
        sp = m.get("spawn")
    if not sp:
        raise RuntimeError(f"Для карты «{scene.map}» нет точки старта. Запишите её: python tools/record_spawn.py {scene.map}")
    d = sp["dir"]
    yaw = math.atan2(d[1], d[0])
    return tuple(sp["pos"]), yaw, ("проверено" if sp.get("verified") else "не проверено — возможна неточность")
