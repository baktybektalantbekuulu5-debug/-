"""Анализ записанного видео средствами OpenCV: энергия движения и положение «интересной» области."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frames: int

    @property
    def duration(self):
        return self.frames / self.fps if self.fps else 0.0


def video_info(path) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV не смог открыть видео: {path}")
    info = VideoInfo(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                     cap.get(cv2.CAP_PROP_FPS) or 30.0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    return info


@dataclass
class MotionSample:
    t: float
    energy: float      # доля изменившихся пикселей (0..1) - сильное движение камеры/сцены
    cx: float          # центр «локального» движения по X (0..1)
    cam_moving: bool   # камера движется вместе с машиной (весь кадр меняется)


def motion_profile(path, sample_fps: float = 4.0, cancel=None) -> list[MotionSample]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV не смог открыть видео: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / sample_fps)))
    out, prev, i = [], None, 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            g = cv2.GaussianBlur(g, (5, 5), 0)
            if prev is not None:
                diff = cv2.absdiff(g, prev)
                mask = (diff > 18).astype(np.uint8)
                frac = float(mask.mean())
                if mask.sum() > 8:
                    cols = mask.sum(axis=0).astype(np.float64)
                    cx = float((cols * np.arange(160)).sum() / cols.sum() / 159.0)
                else:
                    cx = 0.5
                out.append(MotionSample(i / fps, frac, cx, frac > 0.30))
            prev = g
        i += 1
        if cancel is not None and i % 300 == 0:
            cancel.check()
    cap.release()
    return out


def active_range(profile: list[MotionSample], duration: float, thr: float = 0.004):
    """Диапазон, где что-то происходит (отсекает пустой старт/хвост)."""
    act = [s.t for s in profile if s.energy > thr]
    if not act:
        return 0.0, duration
    return max(0.0, act[0] - 0.4), min(duration, act[-1] + 0.6)


def crop_track(profile: list[MotionSample], t0: float, t1: float, max_pan_per_s: float = 0.35):
    """Траектория центра кадрирования cx(t) для сегмента [t0,t1]: возвращает список (t, cx).
    Если камера едет за машиной (весь кадр меняется) — машина по центру → cx=0.5.
    Если камера статична — следуем за центром локального движения."""
    pts = [s for s in profile if t0 - 0.5 <= s.t <= t1 + 0.5]
    track, cur, last_t = [], 0.5, None
    for s in pts:
        target = 0.5 if s.cam_moving else (s.cx if s.energy > 0.002 else cur)
        dt = (s.t - last_t) if last_t is not None else 0.25
        cur_new = cur + (target - cur) * 0.5                      # сглаживание
        lim = max_pan_per_s * dt
        cur = cur + max(-lim, min(lim, cur_new - cur))             # ограничение скорости панорамы
        track.append((s.t, cur))
        last_t = s.t
    return track or [(t0, 0.5), (t1, 0.5)]


def interp(track, t):
    if t <= track[0][0]:
        return track[0][1]
    if t >= track[-1][0]:
        return track[-1][1]
    for (a, ca), (b, cb) in zip(track, track[1:]):
        if a <= t <= b:
            return ca + (cb - ca) * (t - a) / max(1e-6, b - a)
    return 0.5
