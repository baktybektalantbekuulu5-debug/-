"""Тестовые двойники: кинематический симулятор автомобиля (НЕ используется в продукте)."""
import math

from ai_driver.runtime_base import SceneRuntime, VState
from core.geometry import Frame, wrap


class FakeCar:
    def __init__(self, pos, yaw):
        self.x, self.y, self.z = pos
        self.yaw = yaw
        self.v = 0.0
        self.vz = 0.0
        self.steer = self.thr = self.brk = self.park = 0.0


class FakeRuntime(SceneRuntime):
    """Велосипедная модель: руль→рыскание, газ/тормоз→скорость, стена останавливает, рампа даёт вертикальную скорость."""
    L = 2.7
    MAXDELTA = math.radians(28)

    def __init__(self, frame: Frame, steer_hidden_sign=1, objects=None):
        self._frame = frame
        self.cars = {"hero": FakeCar(frame.origin, frame.yaw)}
        self.hidden = steer_hidden_sign
        self.objects = objects or {}
        self.t = 0.0
        self.ai_calls = []
        self.ramp_at = None
        self.air = 0.0

    @property
    def frame(self):
        return self._frame

    def now(self): return self.t

    def sleep(self, dt):
        for vid, c in self.cars.items():
            self._integrate(c, dt)
        self.t += dt

    def _integrate(self, c, dt):
        a = 7.0 * c.thr - 12.0 * c.brk - 0.02 * c.v * c.v / 10 - (6 if c.park else 0)
        c.v = max(0.0, c.v + a * dt)
        delta = self.hidden * c.steer * self.MAXDELTA / (1 + c.v / 25.0)
        c.yaw += c.v / self.L * math.tan(delta) * dt * (1.6 if c.park else 1.0)
        c.x += math.cos(c.yaw) * c.v * dt
        c.y += math.sin(c.yaw) * c.v * dt
        # рампа: если пересекли x рампы — прыжок
        if self.ramp_at is not None and self.air <= 0 and c.z <= self._frame.origin[2] + 0.01:
            along, lat = self._frame.local((c.x, c.y))
            if abs(along - self.ramp_at) < c.v * dt + 0.2 and abs(lat) < 3 and c.v > 15:
                c.vz = 6.0
                self.air = 1.4
        if self.air > 0:
            self.air -= dt
            c.vz -= 9.8 * dt
            c.z += c.vz * dt
            if c.z <= self._frame.origin[2]:
                c.z, c.vz, self.air = self._frame.origin[2], 0.0, 0.0
        # стена
        for oid, (pos, kind) in self.objects.items():
            if kind == "wall" and math.hypot(c.x - pos[0], c.y - pos[1]) < 2.0 and c.v > 1.0:
                c.v = 0.0

    def state(self, vid):
        c = self.cars[vid]
        return VState(self.t, (c.x, c.y, c.z), (math.cos(c.yaw), math.sin(c.yaw), 0.0),
                      (math.cos(c.yaw) * c.v, math.sin(c.yaw) * c.v, c.vz))

    def control(self, vid, steering=None, throttle=None, brake=None, parkingbrake=None):
        c = self.cars[vid]
        if steering is not None: c.steer = steering
        if throttle is not None: c.thr = throttle
        if brake is not None: c.brk = brake
        if parkingbrake is not None: c.park = parkingbrake

    def set_ai(self, vid, mode, speed_mps=None, target=None, aggression=None):
        self.ai_calls.append((vid, mode, speed_mps))

    def teleport(self, vid, pos, yaw):
        c = self.cars[vid]
        c.x, c.y, c.z = pos
        c.yaw, c.v = yaw, 0.0

    def reset_to_start(self, vid):
        self.teleport(vid, self._frame.origin, self._frame.yaw)

    def object_pos(self, obj_id): return self.objects[obj_id][0]
    def camera_player(self, vid, candidates, config=None): return candidates[0]
    def camera_free(self, pos, direction): self.last_free = (pos, direction)
