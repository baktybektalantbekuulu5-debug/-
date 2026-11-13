"""Рендер: кадрирование (OpenCV) → FFmpeg (кодирование), сведение звука (FFmpeg)."""
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from core.logger import get_logger
from editor.analysis import crop_track, interp
from editor.planner import Segment

log = get_logger("render")
FADE = 0.12


class FrameSource:
    """Последовательное чтение кадров с дробным индексом (смешивание соседних кадров для слоу-мо)."""

    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"не удалось открыть {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.ai = -10 ** 9
        self.a = self.b = None

    def seek(self, idx):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, idx))
        ok, self.a = self.cap.read()
        ok2, self.b = self.cap.read()
        self.ai = max(0, idx)
        if not ok:
            raise RuntimeError("конец видео")
        if not ok2:
            self.b = self.a

    def get(self, f):
        i0 = int(math.floor(f))
        frac = f - i0
        if i0 < self.ai or i0 - self.ai > 45:
            self.seek(i0)
        while self.ai < i0:
            self.a = self.b
            ok, nxt = self.cap.read()
            self.b = nxt if ok else self.a
            self.ai += 1
        if frac < 0.03 or self.b is None or self.b is self.a:
            return self.a
        return cv2.addWeighted(self.a, 1 - frac, self.b, frac, 0)

    def close(self):
        self.cap.release()


def atempo_chain(speed: float) -> str:
    parts = []
    s = speed
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    if abs(s - 1.0) > 1e-3:
        parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def compose_frame(frame, out_w, out_h, mode, cx, zoom=1.0, crop="smart"):
    h, w = frame.shape[:2]
    if mode == "horizontal":
        if zoom > 1.001:
            cw, ch = w / zoom, h / zoom
            x0, y0 = (w - cw) / 2, (h - ch) / 2
            frame = frame[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]
        return cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4 if out_w > w else cv2.INTER_AREA)
    # вертикальный 9:16
    if crop == "smart":
        ch = h / zoom
        cw = ch * out_w / out_h
        cw = min(cw, w)
        x0 = min(max(cx * w - cw / 2, 0), w - cw)
        y0 = (h - ch) / 2
        part = frame[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]
        return cv2.resize(part, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
    # blur-pad: размытый фон + кадр по ширине
    small = cv2.resize(frame, (out_w // 8, out_h // 8), interpolation=cv2.INTER_AREA)
    s_h, s_w = small.shape[:2]
    bg_h = out_h // 8
    scale = bg_h / h
    bg = cv2.resize(frame, (int(w * scale), bg_h), interpolation=cv2.INTER_AREA)
    xs = max(0, (bg.shape[1] - s_w) // 2)
    bg = bg[:, xs:xs + s_w]
    bg = cv2.GaussianBlur(bg, (0, 0), 6)
    bg = cv2.resize((bg * 0.55).astype(np.uint8), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    fw = out_w
    fh = int(h * fw / w)
    if zoom > 1.001:
        cw, chh = w / zoom, h / zoom
        frame = frame[int((h - chh) / 2):int((h + chh) / 2), int((w - cw) / 2):int((w + cw) / 2)]
        fh = int(frame.shape[0] * fw / frame.shape[1])
    fg = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA)
    y = (out_h - fh) // 2
    bg[y:y + fh, 0:fw] = fg
    return bg


def punch_zoom(t_out, impact_times, strength=0.10):
    z = 0.0
    for te in impact_times:
        d = t_out - te
        if -0.04 <= d < 0.5:
            z = max(z, strength * (1.0 if d < 0.05 else math.exp(-(d - 0.05) / 0.15)))
    return 1.0 + z


def render_video(segments: list[Segment], out_path: Path, ffmpeg: str, mode: str, crop: str, fps: int,
                 profiles: dict, impact_times: list[float], crf=18, preset="medium",
                 cancel=None, progress=None):
    out_w, out_h = (1080, 1920) if mode == "vertical" else (1920, 1080)
    cmd = [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
           "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    total_frames = sum(int(round(s.out_len * fps)) for s in segments)
    done, t_out = 0, 0.0
    sources: dict[str, FrameSource] = {}
    fade_n = max(1, int(round(FADE * fps)))
    try:
        for si, seg in enumerate(segments):
            src = sources.get(seg.src) or sources.setdefault(seg.src, FrameSource(seg.src))
            track = crop_track(profiles.get(seg.src, []), seg.start, seg.end) if (mode == "vertical" and crop == "smart") else [(0, 0.5)]
            n = int(round(seg.out_len * fps))
            for k in range(n):
                if cancel is not None and k % 30 == 0:
                    cancel.check()
                ts = seg.start + k / fps * seg.speed
                fr = src.get(min(ts * src.fps, max(0, src.n - 1)))
                cx = interp(track, ts)
                z = punch_zoom(t_out + k / fps, impact_times)
                img = compose_frame(fr, out_w, out_h, mode, cx, z, crop)
                # переход «через чёрный»
                edge = min(k, n - 1 - k)
                if edge < fade_n:
                    img = (img * ((edge + 1) / (fade_n + 1))).astype(np.uint8)
                try:
                    proc.stdin.write(img.tobytes())
                except BrokenPipeError:
                    raise RuntimeError("FFmpeg завершился: " + proc.stderr.read().decode(errors="ignore")[-400:])
                done += 1
                if progress and done % 15 == 0:
                    progress(done / max(1, total_frames))
            t_out += seg.out_len
        proc.stdin.close()
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError("FFmpeg: " + proc.stderr.read().decode(errors="ignore")[-400:])
    except BaseException:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        for s in sources.values():
            s.close()


def has_audio(path, ffprobe="ffprobe") -> bool:
    r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def build_audio(segments, ffmpeg, ffprobe, out_wav: Path, music: Path | None, sfx: list[tuple[float, Path]],
                game_vol=1.0, music_vol=0.35, sfx_vol=0.9):
    total = sum(s.out_len for s in segments)
    inputs, idx = [], {}
    n_in = 0
    flt = []
    for k, s in enumerate(segments):
        if has_audio(s.src, ffprobe):
            if s.src not in idx:
                idx[s.src] = n_in
                n_in += 1
                inputs += ["-i", str(s.src)]
            chain = [f"[{idx[s.src]}:a]atrim=start={s.start:.4f}:end={s.end:.4f}", "asetpts=PTS-STARTPTS"]
            tempo = atempo_chain(s.speed)
            if tempo:
                chain.append(tempo)
            chain += [f"afade=t=in:st=0:d={FADE}", f"afade=t=out:st={max(0, s.out_len - FADE):.4f}:d={FADE}",
                      "aresample=48000", "aformat=channel_layouts=stereo"]
            flt.append(",".join(chain) + f"[a{k}]")
        else:
            flt.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{s.out_len:.4f},asetpts=PTS-STARTPTS[a{k}]")
    n = len(segments)
    flt.append("".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1,volume={game_vol}[game]")
    mix_in = []
    if music:
        mi = n_in
        n_in += 1
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        flt.append("[game]asplit=2[g1][g2]")
        flt.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                   f"volume={music_vol},afade=t=in:st=0:d=1,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        flt.append("[mus][g1]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]")
        mix_in = ["[g2]", "[duck]"]
    else:
        mix_in = ["[game]"]
    for j, (t, path) in enumerate(sfx):
        si = n_in
        n_in += 1
        inputs += ["-i", str(path)]
        ms = int(max(0, t) * 1000)
        flt.append(f"[{si}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume={sfx_vol}[s{j}]")
        mix_in.append(f"[s{j}]")
    flt.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    cmd = [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(flt), "-map", "[aout]", "-t", f"{total:.3f}",
           "-ar", "48000", "-ac", "2", str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("сведение звука: " + r.stderr[-600:])


def mux(video: Path, audio: Path, out: Path, ffmpeg: str):
    r = subprocess.run([ffmpeg, "-y", "-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("сборка MP4: " + r.stderr[-400:])
