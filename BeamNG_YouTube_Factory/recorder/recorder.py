"""Фабрика рекордера + проверка качества записанного файла."""
import json
import subprocess
from pathlib import Path

from core.logger import get_logger
from recorder.ffmpeg_recorder import FFmpegRecorder
from recorder.obs_recorder import OBSRecorder, RecorderError

log = get_logger("recorder")


def probe(path, ffprobe="ffprobe") -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RecorderError(f"ffprobe не смог прочитать {path}: {out.stderr[-200:]}")
    j = json.loads(out.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        raise RecorderError("в файле нет видеопотока")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {"width": int(v["width"]), "height": int(v["height"]), "fps": round(fps, 2),
            "duration": float(j["format"].get("duration", 0)), "has_audio": a is not None,
            "size_mb": round(int(j["format"].get("size", 0)) / 1e6, 1)}


def check_quality(info: dict, want_resolution: str, want_fps: int) -> list[str]:
    h = {"720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}[want_resolution]
    warns = []
    if info["height"] < h:
        warns.append(f"Разрешение записи {info['width']}x{info['height']} ниже заказанного {want_resolution}.")
    if info["fps"] and info["fps"] < want_fps - 2:
        warns.append(f"Частота кадров записи {info['fps']} ниже заказанной {want_fps} (ПК не успевает или OBS настроен на другое значение).")
    if not info["has_audio"]:
        warns.append("В записи нет звука игры: проверьте источник «Захват звука» в OBS.")
    return warns


def make_recorder(settings, resolution, fps):
    backend = settings.get("recorder.backend", "auto")
    if backend in ("auto", "obs") and settings.get("obs.enabled", True):
        rec = OBSRecorder(settings.get("obs.host"), settings.get("obs.port"), settings.secret("obs.password", "OBS_PASSWORD"),
                          settings.get("obs.scene_name"), set_video=settings.get("obs.set_video_settings"),
                          resolution=resolution, fps=fps)
        try:
            rec.connect()
            return rec
        except RecorderError as e:
            if backend == "obs":
                raise
            log.warning("OBS недоступен (%s). Пробую запасной захват FFmpeg.", e)
    rec = FFmpegRecorder(settings.get("paths.ffmpeg"), settings.get("recorder.ffmpeg_window_title"),
                         settings.get("recorder.ffmpeg_audio_device"), fps, settings.get("recorder.ffmpeg_encoder"))
    rec.connect()
    return rec
