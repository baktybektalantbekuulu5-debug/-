"""Record a screen region (the game window) with FFmpeg."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from ..system.windows import Rect

log = logging.getLogger(__name__)
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def encoder_args(encoder: str) -> list[str]:
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "18", "-qp_p", "20"]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "20"]
    return ["-c:v", encoder]


def build_command(ffmpeg: str, rect: Rect, out: Path, *, fps: int, encoder: str,
                  grabber: str = "gdigrab") -> list[str]:
    if grabber == "ddagrab":
        src = ["-f", "lavfi", "-i",
               f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=0:"
               f"offset_x={rect.x}:offset_y={rect.y}:video_size={rect.w}x{rect.h}",
               "-vf", "hwdownload,format=bgra"]
    else:
        src = ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0",
               "-offset_x", str(rect.x), "-offset_y", str(rect.y),
               "-video_size", f"{rect.w}x{rect.h}", "-i", "desktop"]
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *src,
            *encoder_args(encoder), "-pix_fmt", "yuv420p", str(out)]


class FFmpegRecorder:
    """Start/stop recording; stop() sends 'q' so the MP4 is finalised properly."""

    def __init__(self, ffmpeg: str, *, fps: int = 60, encoder: str = "libx264",
                 grabber: str = "gdigrab"):
        self.ffmpeg, self.fps, self.encoder, self.grabber = ffmpeg, fps, encoder, grabber
        self.proc: subprocess.Popen | None = None
        self.out: Path | None = None
        self.started_at = 0.0

    def start(self, rect: Rect, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_command(self.ffmpeg, rect, out, fps=self.fps, encoder=self.encoder,
                            grabber=self.grabber)
        log.debug("ffmpeg: %s", " ".join(cmd))
        self.out = out
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=_NO_WINDOW)
        self.started_at = time.monotonic()
        time.sleep(0.5)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(errors="ignore") if self.proc.stderr else ""
            raise RuntimeError(f"FFmpeg не запустился: {err.strip()[:500]}")

    def stop(self, timeout: float = 20) -> Path | None:
        if not self.proc:
            return None
        try:
            if self.proc.poll() is None and self.proc.stdin:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
            self.proc.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        err = self.proc.stderr.read().decode(errors="ignore") if self.proc.stderr else ""
        if err.strip():
            log.debug("ffmpeg stderr: %s", err.strip()[:2000])
        self.proc = None
        return self.out
