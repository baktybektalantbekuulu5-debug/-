"""Запись через OBS Studio (obs-websocket 5.x, пакет obsws-python)."""
import os
import shutil
import time
from pathlib import Path

from core.logger import get_logger

log = get_logger("obs")


class RecorderError(Exception):
    pass


class OBSRecorder:
    name = "obs"

    def __init__(self, host="localhost", port=4455, password="", scene_name="", timeout=5,
                 set_video=False, resolution="1080p", fps=60):
        self.host, self.port, self.password = host, int(port), password
        self.scene_name, self.timeout = scene_name, timeout
        self.set_video, self.resolution, self.fps = set_video, resolution, fps
        self.cl = None
        self._start_wall = 0.0
        self._file = None

    # --------------------------------------------------------------- связь
    def connect(self):
        try:
            import obsws_python as obs
        except ImportError:
            raise RecorderError("не установлен пакет obsws-python (pip install obsws-python)")
        try:
            self.cl = obs.ReqClient(host=self.host, port=self.port, password=self.password, timeout=self.timeout)
            ver = self.cl.get_version()
        except Exception as e:  # noqa: BLE001
            raise RecorderError(f"не удалось подключиться к OBS ({self.host}:{self.port}): {e}. "
                                f"Запустите OBS и включите Инструменты → Настройки WebSocket-сервера.")
        log.info("OBS %s, obs-websocket %s", ver.obs_version, ver.obs_web_socket_version)
        if self.scene_name:
            self.cl.set_current_program_scene(self.scene_name)
        if self.set_video:
            self._apply_video()
        return ver

    def _apply_video(self):
        w, h = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "2160p": (3840, 2160)}[self.resolution]
        try:
            self.cl.set_video_settings(self.fps, 1, w, h, w, h)
            log.info("OBS: видео %dx%d @ %d fps", w, h, self.fps)
        except Exception as e:  # noqa: BLE001
            log.warning("не удалось изменить видеонастройки OBS (идёт запись?): %s", e)

    def quality_report(self) -> dict:
        v = self.cl.get_video_settings()
        st = self.cl.get_stats()
        return {"base": (v.base_width, v.base_height), "out": (v.output_width, v.output_height),
                "fps": v.fps_numerator / max(1, v.fps_denominator),
                "dropped_render_frames": st.render_skipped_frames, "dropped_output_frames": st.output_skipped_frames,
                "cpu": round(st.cpu_usage, 1)}

    # ---------------------------------------------------------------- запись
    def start(self, out_dir: Path, name: str):
        if not self.cl:
            self.connect()
        st = self.cl.get_record_status()
        if st.output_active:
            raise RecorderError("OBS уже ведёт запись — остановите её вручную")
        self.cl.start_record()
        t0 = time.monotonic()
        for _ in range(50):
            if self.cl.get_record_status().output_active:
                break
            time.sleep(0.1)
        else:
            raise RecorderError("OBS не начал запись (проверьте источник «Захват игры» и папку записи)")
        self._start_wall = time.monotonic()
        log.info("OBS: запись начата (задержка %.2f с)", self._start_wall - t0)
        self._out_dir, self._name = Path(out_dir), name

    def stop(self) -> Path:
        resp = self.cl.stop_record()
        src = Path(getattr(resp, "output_path", "") or "")
        # ждём финализации файла
        last = -1
        for _ in range(100):
            if src.exists():
                sz = src.stat().st_size
                if sz == last and sz > 0:
                    break
                last = sz
            time.sleep(0.3)
        if not src.exists():
            raise RecorderError(f"OBS не вернул файл записи ({src})")
        dst = self._out_dir / f"{self._name}{src.suffix or '.mkv'}"
        self._out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)  # копируем, оригинал OBS остаётся на месте
        log.info("запись сохранена: %s (%.1f МБ)", dst, dst.stat().st_size / 1e6)
        try:
            q = self.quality_report()
            if q["dropped_output_frames"] or q["dropped_render_frames"]:
                log.warning("OBS пропустил кадры: %s", q)
        except Exception:  # noqa: BLE001
            pass
        return dst

    def abort(self):
        try:
            self.cl.stop_record()
        except Exception:  # noqa: BLE001
            pass
