"""Проверка наличия необходимых программ, пакетов и игровых ресурсов."""
import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""
    critical: bool = False

    def __str__(self):
        mark = "OK " if self.ok else ("ОШИБКА" if self.critical else "ВНИМАНИЕ")
        s = f"[{mark}] {self.name}: {self.detail}"
        if not self.ok and self.fix:
            s += f"\n         → {self.fix}"
        return s


def _version(cmd):
    try:
        out = subprocess.run([cmd, "-version"], capture_output=True, text=True, timeout=10)
        return out.stdout.splitlines()[0] if out.returncode == 0 and out.stdout else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_all(settings, need_game=True, need_recorder=True, deep=False) -> list[Check]:
    res: list[Check] = []
    ff, fp = settings.get("paths.ffmpeg", "ffmpeg"), settings.get("paths.ffprobe", "ffprobe")
    for exe, label in ((ff, "FFmpeg"), (fp, "FFprobe")):
        v = _version(exe)
        res.append(Check(label, bool(v), v or f"не найден ({exe})",
                         "Установите FFmpeg (winget install Gyan.FFmpeg) или укажите путь в Настройках", True))
    for mod, pip, crit in (("cv2", "opencv-python", True), ("numpy", "numpy", True), ("PySide6", "PySide6", False),
                           ("beamngpy", "beamngpy", need_game), ("obsws_python", "obsws-python", False),
                           ("requests", "requests", False)):
        try:
            m = importlib.import_module(mod)
            res.append(Check(f"Python-пакет {pip}", True, getattr(m, "__version__", "установлен")))
        except ImportError:
            res.append(Check(f"Python-пакет {pip}", False, "не установлен", f"pip install {pip}", crit))
    res.append(Check("Python", sys.version_info >= (3, 10), sys.version.split()[0], "Нужен Python 3.10+ (рекомендуется 3.11)", True))
    home = settings.get("paths.beamng_home")
    if need_game:
        if not home:
            res.append(Check("BeamNG.drive (папка игры)", False, "путь не задан",
                             "Настройки → BeamNG: укажите папку с BeamNG.drive.exe (например C:\\Program Files (x86)\\Steam\\steamapps\\common\\BeamNG.drive)", False))
        else:
            p = Path(home)
            ok = p.exists() and (p / "content").exists()
            res.append(Check("BeamNG.drive (папка игры)", ok, str(p) if ok else f"{p} не содержит content/",
                             "Проверьте путь в Настройках", True))
    if need_recorder:
        if settings.get("obs.enabled", True) and deep:
            try:
                import contextlib
                import io
                import logging
                import obsws_python as obs
                logging.getLogger("obsws_python").disabled = True
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    cl = obs.ReqClient(host=settings.get("obs.host"), port=int(settings.get("obs.port")),
                                       password=settings.secret("obs.password", "OBS_PASSWORD"), timeout=3)
                with contextlib.redirect_stderr(io.StringIO()):
                    v = cl.get_version()
                res.append(Check("OBS Studio WebSocket", True, f"OBS {v.obs_version}"))
            except Exception as e:  # noqa: BLE001
                res.append(Check("OBS Studio WebSocket", False, str(e)[:120],
                                 "Запустите OBS → Инструменты → Настройки WebSocket-сервера → включить, задать пароль", False))
    free = shutil.disk_usage(settings.output_dir).free / 1e9
    res.append(Check("Свободное место", free > 5, f"{free:.1f} ГБ", "Освободите диск: запись 1080p60 занимает ~1–3 ГБ/мин", False))
    return res


def critical_failures(checks):
    return [c for c in checks if not c.ok and c.critical]
