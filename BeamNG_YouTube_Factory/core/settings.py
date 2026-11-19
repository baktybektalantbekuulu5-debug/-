"""Настройки: default_config.json + user_config.json (переопределения пользователя)."""
import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    def __init__(self, user_path: Path | None = None, default_path: Path | None = None):
        self.default_path = default_path or CONFIG_DIR / "default_config.json"
        self.user_path = user_path or CONFIG_DIR / "user_config.json"
        self.data: dict = {}
        self.load()

    def load(self):
        base = json.loads(self.default_path.read_text(encoding="utf-8"))
        over = {}
        if self.user_path.exists():
            try:
                over = json.loads(self.user_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                over = {}
        self.data = _merge(base, over)

    def save(self):
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, path: str, default=None):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, path: str, value):
        parts = path.split(".")
        cur = self.data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value

    def secret(self, path: str, env: str) -> str:
        """Ключ из конфига, иначе из переменной окружения."""
        return self.get(path) or os.environ.get(env, "")

    @property
    def output_dir(self) -> Path:
        p = Path(self.get("paths.output_dir") or ROOT / "output")
        if not p.is_absolute():
            p = ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p
