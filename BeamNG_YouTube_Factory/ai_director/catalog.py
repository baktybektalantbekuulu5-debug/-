"""Каталог машин и карт + подбор по тексту. Проверка по установленной игре."""
import json
import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"


def _load(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


class Catalog:
    def __init__(self, cars_data=None, maps_data=None):
        cars_data = cars_data or _load("cars.json")
        maps_data = maps_data or _load("maps.json")
        self.cars = cars_data["cars"]
        self.colors = cars_data["colors"]
        self.maps = maps_data["maps"]
        self._user_maps_path = CONFIG / "user_maps.json"
        if self._user_maps_path.exists():  # пользовательские/откалиброванные точки
            try:
                for um in json.loads(self._user_maps_path.read_text(encoding="utf-8")).get("maps", []):
                    self._merge_map(um)
            except Exception:
                pass

    def _merge_map(self, um):
        for m in self.maps:
            if m["level"] == um["level"]:
                m.update(um)
                return
        self.maps.append(um)

    def save_user_spawn(self, level, spawn: dict):
        data = {"maps": []}
        if self._user_maps_path.exists():
            data = json.loads(self._user_maps_path.read_text(encoding="utf-8"))
        data["maps"] = [m for m in data["maps"] if m["level"] != level]
        data["maps"].append({"level": level, "spawn": spawn})
        self._user_maps_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._merge_map({"level": level, "spawn": spawn})

    def car(self, model):
        return next((c for c in self.cars if c["model"] == model), None)

    def map(self, level):
        return next((m for m in self.maps if m["level"] == level), None)

    def find_car(self, text: str):
        """Возвращает (car, matched_alias). Самый длинный алиас побеждает."""
        t = text.lower()
        best = None
        for c in self.cars:
            for a in c["aliases"] + c.get("brands", []) + [c["model"]]:
                if a.lower() in t and (best is None or len(a) > len(best[1])):
                    best = (c, a)
        return best

    def find_cars_all(self, text: str):
        """Все упомянутые машины в порядке появления: [(pos, car, alias)]."""
        t = text.lower()
        found = {}
        for c in self.cars:
            for a in c["aliases"] + c.get("brands", []) + [c["model"]]:
                for m in re.finditer(re.escape(a.lower()), t):
                    prev = found.get(c["model"])
                    if prev is None or m.start() < prev[0]:
                        found[c["model"]] = (m.start(), c, a)
        return sorted(found.values(), key=lambda x: x[0])

    def find_map(self, text: str):
        t = text.lower()
        best, score = None, 0
        for m in self.maps:
            s = 0
            for a in m["aliases"]:
                if a in t:
                    s += len(a)
            if m["level"] in t or m["name"].lower() in t:
                s += 20
            if s > score:
                best, score = m, s
        return best

    def color_rgba(self, name: str):
        if not name:
            return None
        n = name.lower()
        for k, v in self.colors.items():
            if n.startswith(k) or k in n:
                return tuple(v)
        return None

    def find_color(self, text: str):
        t = text.lower()
        for k in self.colors:
            if re.search(r"\b" + re.escape(k), t):
                return k
        return ""

    def maps_with_spawn(self):
        return [m for m in self.maps if m.get("spawn")]
