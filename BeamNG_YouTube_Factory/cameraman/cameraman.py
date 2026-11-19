"""AI Cameraman: план ракурсов и управление игровой камерой.

Использует только то, что даёт beamngpy: bng.camera.set_player_mode (режимы игры) и
bng.camera.set_free (свободная камера в точке pos, направление dir). Свободные ракурсы
(tripod/flyby/drone/side/front_low) пересчитываются 20 раз в секунду.
Если камера недоступна в вашей версии игры — съёмка продолжается штатной камерой, в журнал пишется причина.
"""
import math

from core.geometry import fwd_vec, left_vec
from core.logger import get_logger
from core.models import CameraShot, Scene
from ai_driver.runtime_base import CameraUnsupported

log = get_logger("camera")

PLAYER_MODES = {   # приоритетные имена режимов игры (реальный список запрашивается у игры)
    "chase": ["external", "chase", "orbit"],
    "orbit": ["orbit", "external"],
    "hood": ["bumper", "hood", "driver"],
    "driver": ["driver", "bumper"],
}
FREE_MODES = ("tripod", "flyby", "drone", "side", "front_low")

STYLES = {  # (режим, доля длительности сцены)
    "chase": [("chase", 0.0)],
    "action": [("chase", 0.0), ("side", 0.35), ("drone", 0.65), ("chase", 0.85)],
    "cinematic": [("chase", 0.0), ("flyby", 0.2), ("side", 0.45), ("drone", 0.65), ("front_low", 0.85)],
}
ALT_TAKES = [   # другой набор ракурсов для повторных дублей
    [("hood", 0.0), ("drone", 0.3), ("tripod", 0.55), ("chase", 0.8)],
    [("drone", 0.0), ("front_low", 0.3), ("side", 0.55), ("hood", 0.8)],
]


def plan_shots(scene: Scene, style: str = "cinematic", take_index: int = 0) -> list[CameraShot]:
    if scene.shots and take_index == 0:
        return scene.shots
    seq = STYLES.get(style, STYLES["cinematic"]) if take_index == 0 else ALT_TAKES[(take_index - 1) % len(ALT_TAKES)]
    d = scene.max_duration
    return [CameraShot(mode=m, start=round(f * d, 2)) for m, f in seq]


class Cameraman:
    def __init__(self, rt, hero="hero", event_cuts=True):
        self.rt, self.hero, self.event_cuts = rt, hero, event_cuts
        self.shots: list[CameraShot] = []
        self.cur_mode = None
        self.override = None            # (mode, until_t)
        self.cam = None                 # сглаженная позиция свободной камеры
        self.anchor = None              # неподвижная точка для tripod/flyby
        self.free_ok = True
        self.player_ok = True
        self.available_modes = None
        self.log_lines = []

    def set_shots(self, shots):
        self.shots = sorted(shots, key=lambda s: s.start)
        self.cur_mode = None

    # --------------------------------------------------------------- события
    def on_event(self, ev, st):
        if not self.event_cuts:
            return
        if ev.type == "jump":
            self._override("side", ev.t + ev.data.get("airtime", 1.5) + 1.0, st)
        elif ev.type == "crash":
            self._override("tripod", ev.t + 4.0, st)
        elif ev.type == "loss_of_control":
            self._override("drone", ev.t + 2.5, st)

    def _override(self, mode, until, st):
        self.override = (mode, until)
        self._enter(mode, st)

    # --------------------------------------------------------------- тик
    def on_tick(self, t, st):
        mode = None
        if self.override and t < self.override[1]:
            mode = self.override[0]
        else:
            self.override = None
            for s in self.shots:
                if s.start <= t:
                    mode = s.mode
        if mode is None:
            mode = "chase"
        if mode != self.cur_mode:
            self._enter(mode, st)
        if self.cur_mode in FREE_MODES:
            self._update_free(st)

    def _enter(self, mode, st):
        self.cur_mode = mode
        self.anchor = None
        if mode in FREE_MODES:
            if not self.free_ok:
                mode = "chase"
            else:
                f = fwd_vec(math.atan2(st.dir[1], st.dir[0]))
                l = left_vec(math.atan2(st.dir[1], st.dir[0]))
                ahead = max(20.0, st.speed * 2.5)
                side = 9.0 if mode == "tripod" else 5.5
                if mode in ("tripod", "flyby"):
                    self.anchor = (st.pos[0] + f[0] * ahead + l[0] * side,
                                   st.pos[1] + f[1] * ahead + l[1] * side, st.pos[2] + (1.6 if mode == "flyby" else 2.2))
                self.cam = None
                return
        try:
            if self.player_ok:
                cands = PLAYER_MODES.get(mode, PLAYER_MODES["chase"])
                used = self.rt.camera_player(self.hero, cands)
                log.debug("камера: режим игры %s", used)
        except (CameraUnsupported, Exception) as e:  # noqa: BLE001
            self.player_ok = False
            log.warning("режимы камеры игры недоступны (%s) — остаётся штатная камера", e)

    def _update_free(self, st):
        pos, dr = self.pose(self.cur_mode, st)
        # сглаживание позиции для движущихся камер
        if self.cam is None or self.anchor is not None:
            self.cam = pos
        else:
            a = 0.18
            self.cam = tuple(self.cam[i] + (pos[i] - self.cam[i]) * a for i in range(3))
        d = tuple(st.pos[i] - self.cam[i] for i in range(3))
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        d = tuple(c / n for c in d)
        try:
            self.rt.camera_free(self.cam, d)
        except (CameraUnsupported, Exception) as e:  # noqa: BLE001
            self.free_ok = False
            log.warning("свободная камера недоступна (%s) — переключаюсь на камеры игры", e)
            self.cur_mode = None

    def pose(self, mode, st):
        yaw = math.atan2(st.dir[1], st.dir[0])
        f, l = fwd_vec(yaw), left_vec(yaw)
        p = st.pos
        if mode in ("tripod", "flyby") and self.anchor:
            return self.anchor, (0, 0, 0)
        if mode == "drone":
            return (p[0] - f[0] * 12 , p[1] - f[1] * 12, p[2] + 7.0), (0, 0, 0)
        if mode == "side":
            return (p[0] + l[0] * 7.5 + f[0] * 2, p[1] + l[1] * 7.5 + f[1] * 2, p[2] + 1.3), (0, 0, 0)
        if mode == "front_low":
            return (p[0] + f[0] * 9, p[1] + f[1] * 9, p[2] + 0.8), (0, 0, 0)
        return (p[0] - f[0] * 8, p[1] - f[1] * 8, p[2] + 2.5), (0, 0, 0)
