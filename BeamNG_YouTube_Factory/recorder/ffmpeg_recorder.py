"""Запасной вариант записи: захват окна BeamNG.drive средствами FFmpeg (gdigrab, только Windows).
Ограничение: gdigrab захватывает окно/рабочий стол; игру нужно запускать в оконном/безрамочном режиме.
Звук игры пишется только если указано устройство DirectShow (например «Stereo Mix»)."""
import subprocess
import sys
import time
from pathlib import Path

from core.logger import get_logger
from recorder.obs_recorder import RecorderError

log = get_logger("ffrec")


class FFmpegRecorder:
    name = "ffmpeg"

    def __init__(self, ffmpeg="ffmpeg", title="BeamNG.drive", audio_device="", fps=60, encoder="libx264"):
        self.ffmpeg, self.title, self.audio, self.fps, self.encoder = ffmpeg, title, audio_device, fps, encoder
        self.proc = None
        self.file: Path | None = None

    def connect(self):
        if not sys.platform.startswith("win"):
            raise RecorderError("FFmpeg-захват (gdigrab) работает только в Windows")

    def build_cmd(self, out: Path):
        cmd = [self.ffmpeg, "-y", "-f", "gdigrab", "-framerate", str(self.fps), "-draw_mouse", "0",
               "-i", f"title={self.title}"]
        if self.audio:
            cmd += ["-f", "dshow", "-i", f"audio={self.audio}"]
        cmd += ["-c:v", self.encoder, "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
        if self.audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        cmd += [str(out)]
        return cmd

    def start(self, out_dir: Path, name: str):
        out_dir.mkdir(parents=True, exist_ok=True)
        self.file = out_dir / f"{name}.mp4"
        self.proc = subprocess.Popen(self.build_cmd(self.file), stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(1.5)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(errors="ignore")[-400:]
            raise RecorderError(f"FFmpeg не смог начать захват окна «{self.title}»: {err}")

    def stop(self) -> Path:
        try:
            self.proc.stdin.write(b"q")
            self.proc.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        if not self.file or not self.file.exists() or self.file.stat().st_size == 0:
            raise RecorderError("FFmpeg не создал файл записи")
        return self.file

    def abort(self):
        if self.proc and self.proc.poll() is None:
            self.stop()
