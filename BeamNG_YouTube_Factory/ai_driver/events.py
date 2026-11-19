"""Детектор игровых событий по телеметрии (прыжок, приземление, авария, занос)."""
import math
from collections import deque

from core.models import Event


class EventDetector:
    def __init__(self, hero="hero"):
        self.hero = hero
        self.hist = deque()          # (t, speed)
        self.events: list[Event] = []
        self.mode = "ground"
        self._air = None
        self._last = {}
        self._slip_since = None
        self.max_speed = 0.0
        self.max_speed_t = 0.0

    def _emit(self, t, typ, debounce=0.0, **data):
        if debounce and t - self._last.get(typ, -1e9) < debounce:
            return None
        self._last[typ] = t
        ev = Event(round(t, 3), typ, self.hero, data)
        self.events.append(ev)
        return ev

    def update(self, t, pos, dir_, vel):
        """Возвращает список новых событий."""
        new = []
        speed = math.hypot(vel[0], vel[1])
        vz = vel[2]
        if speed > self.max_speed:
            self.max_speed, self.max_speed_t = speed, t
        self.hist.append((t, speed))
        while self.hist and t - self.hist[0][0] > 0.6:
            self.hist.popleft()

        # --- авария: резкое падение скорости
        peak = max(s for _, s in self.hist)
        if peak >= 8.0 and peak - speed >= 9.0:
            ev = self._emit(t, "crash", debounce=4.0, speed_before_kph=round(peak * 3.6), speed_after_kph=round(speed * 3.6))
            if ev:
                new.append(ev)

        # --- прыжок
        if self.mode == "ground":
            if vz > 2.0 and speed > 6:
                self.mode = "air"
                self._air = {"t0": t, "z0": pos[2], "zmax": pos[2], "desc": False}
        else:
            a = self._air
            a["zmax"] = max(a["zmax"], pos[2])
            if vz < -1.5:
                a["desc"] = True
            landed = (a["desc"] and vz > -0.8) or t - a["t0"] > 7.0
            if landed:
                air = t - a["t0"]
                self.mode = "ground"
                if air >= 0.6:
                    new.append(self._emit(a["t0"], "jump", airtime=round(air, 2), height=round(a["zmax"] - a["z0"], 2)))
                    new.append(self._emit(t, "landing", airtime=round(air, 2)))
                self._air = None

        # --- занос: угол между курсом и вектором скорости
        if speed > 8.0 and self.mode == "ground":
            ang = abs(math.atan2(dir_[0] * vel[1] - dir_[1] * vel[0], dir_[0] * vel[0] + dir_[1] * vel[1]))
            if 0.7 < ang < 2.6:
                if self._slip_since is None:
                    self._slip_since = t
                elif t - self._slip_since >= 0.3:
                    ev = self._emit(t, "loss_of_control", debounce=3.0, slip_deg=round(math.degrees(ang)))
                    if ev:
                        new.append(ev)
            else:
                self._slip_since = None
        else:
            self._slip_since = None
        return [e for e in new if e]

    def finish(self, t):
        self._emit(t, "top_speed", kph=round(self.max_speed * 3.6))
        self.events[-1].t = round(self.max_speed_t, 3)
        self._emit(t, "finish")
        return self.events

    def got(self, typ):
        return any(e.type == typ for e in self.events)
