"""AI Driver: исполняет действия сцены через SceneRuntime (ручное управление + встроенный ИИ игры)."""
import math

from core.geometry import fwd_vec, wrap
from core.logger import get_logger
from core.models import Event, Scene
from core.stop import CancelToken
from ai_driver.controllers import HeadingHold, LineTracker, PointTracker, SpeedController, clip
from ai_driver.events import EventDetector
from ai_driver.runtime_base import SceneRuntime

log = get_logger("driver")
DT = 0.05  # 20 Гц


class SceneTimeout(Exception):
    pass


class Driver:
    def __init__(self, rt: SceneRuntime, cancel: CancelToken | None = None, steer_sign: int = 0,
                 on_event=None, on_tick=None, hero="hero"):
        self.rt = rt
        self.cancel = cancel or CancelToken()
        self.steer_sign = steer_sign or 1
        self.need_calibration = steer_sign == 0
        self.on_event, self.on_tick = on_event, on_tick
        self.hero = hero
        self.det = EventDetector(hero)
        self.origin_t = 0.0
        self.deadline = 1e18
        self._hold_ctl = None

    # ------------------------------------------------------------------ служебное
    def _t(self):
        return self.rt.now() - self.origin_t

    def _tick(self, vid=None):
        self.cancel.check()
        if self.rt.now() > self.deadline:
            raise SceneTimeout()
        st = self.rt.state(self.hero)
        evs = self.det.update(self._t(), st.pos, st.dir, st.vel)
        for e in evs:
            log.info("событие: %s t=%.1f %s", e.type, e.t, e.data)
            if self.on_event:
                self.on_event(e, st)
        if self.on_tick:
            self.on_tick(self._t(), st)
        return st

    def _step(self):
        st = self._tick()
        self.rt.sleep(DT)
        return st

    def _drive(self, vid, steer_left, thr, brk, parking=0.0):
        self.rt.control(vid, steering=clip(steer_left * self.steer_sign, -1, 1), throttle=thr, brake=brk,
                        parkingbrake=parking)

    # ---------------------------------------------------------------- калибровка руля
    def calibrate_steer(self, vid=None):
        """Определяет знак руля: подаём руль +0.35 на ~25 км/ч и смотрим, куда повернул курс.
        Нужно, чтобы не гадать, как в данной версии игры направлен положительный руль."""
        vid = vid or self.hero
        sc = SpeedController()
        for _ in range(int(14 / DT)):
            st = self.rt.state(vid)
            if st.speed > 6.5:
                break
            thr, brk = sc.step(7.0, st.speed, DT)
            self.rt.control(vid, steering=0.0, throttle=thr, brake=brk, parkingbrake=0.0)
            self.cancel.check()
            self.rt.sleep(DT)
        y0 = self.rt.state(vid).yaw
        for _ in range(int(0.9 / DT)):
            st = self.rt.state(vid)
            thr, brk = sc.step(7.0, st.speed, DT)
            self.rt.control(vid, steering=0.35, throttle=thr, brake=brk)
            self.rt.sleep(DT)
        dy = wrap(self.rt.state(vid).yaw - y0)
        self.rt.control(vid, steering=0.0, throttle=0.0, brake=1.0)
        if abs(dy) < math.radians(0.8):
            raise RuntimeError("Калибровка руля не удалась: курс не изменился (автомобиль не едет?)")
        self.steer_sign = 1 if dy > 0 else -1
        self.need_calibration = False
        log.info("калибровка руля: знак=%+d (изменение курса %.1f°)", self.steer_sign, math.degrees(dy))
        return self.steer_sign

    # ----------------------------------------------------------------- сцена
    def run_scene(self, scene: Scene, origin_t: float | None = None):
        """Выполняет действия сцены. Возвращает список событий (время — от origin_t)."""
        self.origin_t = self.rt.now() if origin_t is None else origin_t
        self.deadline = self.rt.now() + scene.max_duration
        frame = self.rt.frame
        self._line = LineTracker(frame.origin[:2], frame.yaw)
        # фоновые ИИ-машины
        for a in scene.actions:
            if a.vehicle != self.hero:
                self._background(a)
        try:
            for a in scene.actions:
                if a.vehicle != self.hero:
                    continue
                log.info("действие: %s %s", a.type, a.params)
                getattr(self, "_a_" + a.type)(a.params)
        except SceneTimeout:
            log.warning("достигнут лимит времени сцены (%.0f с)", scene.max_duration)
        finally:
            try:
                self.rt.control(self.hero, steering=0.0, throttle=0.0, brake=0.3, parkingbrake=0.0)
            except Exception:  # noqa: BLE001
                pass
        self.det.finish(self._t())
        return list(self.det.events)

    def _background(self, a):
        if a.type == "chase":
            self.rt.set_ai(a.vehicle, "chase", target=self.hero, speed_mps=a.params.get("kph", 150) / 3.6)
        elif a.type in ("follow_road", "cruise", "accelerate"):
            self.rt.set_ai(a.vehicle, "span", speed_mps=a.params.get("kph", a.params.get("target_kph", 80)) / 3.6)

    # --------------------------------------------------------------- действия
    def _hold_line(self, kph, duration=None, until=None, tracker=None, timeout=60.0):
        sc = SpeedController()
        t_end = self.rt.now() + (duration if duration is not None else timeout)
        tracker = tracker or self._line
        while self.rt.now() < t_end:
            st = self._tick()
            if until and until(st):
                return st
            thr, brk = sc.step(kph / 3.6, st.speed, DT)
            self._drive(self.hero, tracker.steer(st.pos, st.yaw, st.speed), thr, brk)
            self.rt.sleep(DT)
        return self.rt.state(self.hero)

    def _relock_line(self):
        """После заноса — новая линия от текущей точки вдоль курса сцены."""
        st = self.rt.state(self.hero)
        self._line = LineTracker(st.pos[:2], self.rt.frame.yaw)

    def _a_wait(self, p):
        end = self.rt.now() + p.get("duration", 2.0)
        while self.rt.now() < end:
            self._step()

    def _a_cruise(self, p):
        self._hold_line(p.get("kph", 60), duration=p.get("duration", 5))

    def _a_accelerate(self, p):
        tgt = p.get("target_kph", 100) / 3.6
        self._hold_line(tgt * 3.6, until=lambda st: st.speed >= tgt - 1.0, timeout=p.get("max_duration", 25))

    def _a_brake(self, p):
        to = p.get("to_kph", 0) / 3.6
        end = self.rt.now() + p.get("max_duration", 10)
        while self.rt.now() < end:
            st = self._tick()
            if st.speed <= to + 0.5:
                break
            self._drive(self.hero, 0.0, 0.0, 1.0)
            self.rt.sleep(DT)
        self._relock_line()

    def _a_turn(self, p):
        st0 = self.rt.state(self.hero)
        target = wrap(st0.yaw + math.radians(p.get("angle_deg", 90)))
        hold = HeadingHold(target)
        sc = SpeedController()
        ok_since = None
        end = self.rt.now() + p.get("max_duration", 8)
        while self.rt.now() < end:
            st = self._tick()
            thr, brk = sc.step(p.get("kph", 40) / 3.6, st.speed, DT)
            self._drive(self.hero, hold.steer(st.pos, st.yaw, st.speed), thr, brk)
            if abs(wrap(target - st.yaw)) < math.radians(6):
                ok_since = ok_since or self.rt.now()
                if self.rt.now() - ok_since > 0.4:
                    break
            else:
                ok_since = None
            self.rt.sleep(DT)
        self._line = LineTracker(self.rt.state(self.hero).pos[:2], target)

    def _a_follow_road(self, p):
        """Встроенный ИИ игры ведёт машину по дорожной сети карты."""
        kph = p.get("kph", 80)
        self.rt.set_ai(self.hero, "span", speed_mps=kph / 3.6, aggression=p.get("aggression", 0.5))
        end = self.rt.now() + p.get("duration", 10)
        while self.rt.now() < end:
            self._step()
        self.rt.disable_ai(self.hero)

    def _a_chase(self, p):
        self._a_wait({"duration": p.get("duration", 5)})

    def _a_jump(self, p):
        """Подъезд к рампе по оси рампы на заданной скорости и пролёт за неё."""
        frame = self.rt.frame
        ramp = self.rt.object_pos(p["ramp"])
        ramp_local = frame.local(ramp)
        kph = p.get("kph", 100)
        # линия проходит через ось рампы вдоль курса сцены
        tracker = LineTracker(ramp[:2], frame.yaw)
        land = p.get("landing_distance", ramp_local[0] + 40)
        sc = SpeedController()
        end = self.rt.now() + 40
        while self.rt.now() < end:
            st = self._tick()
            along, _ = frame.local(st.pos)
            if along >= land:
                break
            if self.det.mode == "air":      # в воздухе руль/газ не трогаем
                self._drive(self.hero, 0.0, 0.0, 0.0)
            else:
                thr, brk = sc.step(kph / 3.6, st.speed, DT)
                self._drive(self.hero, tracker.steer(st.pos, st.yaw, st.speed), thr, brk)
            self.rt.sleep(DT)
        # постпосадочная стабилизация
        self._hold_line(max(30, kph * 0.6), duration=1.2, tracker=tracker)
        self._relock_line()

    def _a_lose_control(self, p):
        sign = 1.0 if p.get("direction", "right") == "left" else -1.0
        dur = p.get("duration", 2.5)
        end = self.rt.now() + dur
        sc = SpeedController()
        t0 = self.rt.now()
        while self.rt.now() < end:
            st = self._tick()
            k = (self.rt.now() - t0) / dur
            thr, _ = sc.step(max(st.speed, 25.0) / 3.6 * 3.6, st.speed, DT)
            # резкий руль + ручник: провоцирует занос/разворот
            self._drive(self.hero, sign * (1.0 if k < 0.7 else -0.6), 0.6, 0.0, parking=1.0 if 0.15 < k < 0.8 else 0.0)
            self.rt.sleep(DT)
        # короткая «ловля» машины
        end2 = self.rt.now() + 1.0
        while self.rt.now() < end2:
            st = self._tick()
            self._drive(self.hero, 0.0, 0.0, 0.2)
            self.rt.sleep(DT)
        self._relock_line()

    def _a_crash(self, p):
        """Таран цели: едем в её центр на заданной скорости, затем катимся после удара."""
        tgt = self.rt.object_pos(p["target"])
        tracker = PointTracker(tgt[:2])
        kph = p.get("kph", 110)
        sc = SpeedController()
        end = self.rt.now() + 40
        crash_t = None
        while self.rt.now() < end:
            st = self._tick()
            if self.det.got("crash") and crash_t is None:
                crash_t = self.rt.now()
            if crash_t is not None and self.rt.now() - crash_t > p.get("after", 3.0):
                break
            if crash_t is not None:
                self._drive(self.hero, 0.0, 0.0, 0.0)
            else:
                thr, brk = sc.step(kph / 3.6, st.speed, DT)
                self._drive(self.hero, tracker.steer(st.pos, st.yaw, st.speed), thr, brk)
                if tracker.distance(st.pos) < 1.0 and st.speed < 1.0:
                    break  # уже стоим у цели
            self.rt.sleep(DT)
