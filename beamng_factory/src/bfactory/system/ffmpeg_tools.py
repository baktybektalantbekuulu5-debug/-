"""Locate/download FFmpeg and probe which encoders and screen grabbers work."""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from ..core import paths

log = logging.getLogger(__name__)
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
FFMPEG_ZIP_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                  "ffmpeg-master-latest-win64-gpl.zip")
HW_ENCODERS = ("h264_nvenc", "h264_amf", "h264_qsv")


def run(args: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW, encoding="utf-8", errors="ignore")


def _has_device(ffmpeg: str, name: str) -> bool:
    try:
        out = run([ffmpeg, "-hide_banner", "-devices"]).stdout
        out += run([ffmpeg, "-hide_banner", "-filters"]).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f" {name} " in out


def _candidates() -> list[str]:
    c: list[str] = []
    local = paths.TOOLS_DIR / "ffmpeg" / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if local.is_file():
        c.append(str(local))
    if w := shutil.which("ffmpeg"):
        c.append(w)
    try:
        import imageio_ffmpeg
        c.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 - optional dependency
        pass
    return c


def download_ffmpeg() -> str | None:
    """Download a full Windows FFmpeg build into tools/ffmpeg."""
    if sys.platform != "win32":
        return None
    log.info("Скачиваю FFmpeg (около 150 МБ)...")
    try:
        with urllib.request.urlopen(FFMPEG_ZIP_URL, timeout=600) as r:
            data = r.read()
        target = paths.TOOLS_DIR / "ffmpeg"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.namelist():
                parts = Path(member).parts
                if len(parts) < 3 or parts[1] != "bin" or member.endswith("/"):
                    continue
                out = target / "bin" / parts[-1]
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(member))
        exe = target / "bin" / "ffmpeg.exe"
        return str(exe) if exe.is_file() else None
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось скачать FFmpeg: %s", e)
        return None


def find_ffmpeg(allow_download: bool = True) -> str | None:
    """Return an FFmpeg that can grab the Windows desktop (gdigrab)."""
    cands = _candidates()
    for c in cands:
        if sys.platform != "win32" or _has_device(c, "gdigrab"):
            return c
    if allow_download and (d := download_ffmpeg()):
        return d
    return cands[0] if cands else None


def working_encoders(ffmpeg: str) -> list[str]:
    """Hardware encoders that actually encode on this GPU, plus libx264."""
    ok: list[str] = []
    for enc in HW_ENCODERS:
        try:
            r = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                     "testsrc2=size=1280x720:rate=30", "-frames:v", "30", "-c:v", enc,
                     "-f", "null", "-"], timeout=60)
            if r.returncode == 0:
                ok.append(enc)
        except (OSError, subprocess.SubprocessError):
            pass
    ok.append("libx264")
    return ok


def supports_ddagrab(ffmpeg: str) -> bool:
    return _has_device(ffmpeg, "ddagrab")


def probe_duration(ffmpeg: str, video: Path) -> float | None:
    """Duration in seconds using ffmpeg itself (ffprobe may be absent)."""
    try:
        r = run([ffmpeg, "-hide_banner", "-i", str(video), "-f", "null", "-"], timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    import re
    times = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not times:
        return None
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def frame_brightness(ffmpeg: str, video: Path, at_s: float) -> float | None:
    """Mean brightness 0..255 of one frame (detects black captures)."""
    from PIL import Image, ImageStat
    png = video.with_suffix(f".t{int(at_s)}.png")
    try:
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_s:.2f}",
             "-i", str(video), "-frames:v", "1", str(png)], timeout=60)
        with Image.open(png) as im:
            return float(ImageStat.Stat(im.convert("L")).mean[0])
    except Exception:  # noqa: BLE001
        return None
