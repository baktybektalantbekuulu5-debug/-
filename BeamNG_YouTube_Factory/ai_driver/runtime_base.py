"""Интерфейс «рантайма сцены» — всё, что нужно драйверу и оператору от игры.
Реализации: environment.beamng_session.BeamNGRuntime (настоящая игра), tests/fakes.py (кинематический симулятор для тестов)."""
import math
from dataclasses import dataclass


@dataclass
class VState:
    t: float
    pos: tuple
    dir: tuple
    vel: tuple

    @property
    def speed(self) -> float:           # горизонтальная скорость, м/с
        return math.hypot(self.vel[0], self.vel[1])

    @property
    def yaw(self) -> float:
        return math.atan2(self.dir[1], self.dir[0])


class CameraUnsupported(Exception):
    pass


class SceneRuntime:
    def now(self) -> float: raise NotImplementedError
    def sleep(self, dt: float): raise NotImplementedError
    def state(self, vid: str) -> VState: raise NotImplementedError
    def control(self, vid, steering=None, throttle=None, brake=None, parkingbrake=None): raise NotImplementedError
    def set_ai(self, vid, mode: str, speed_mps=None, target=None, aggression=None): raise NotImplementedError
    def disable_ai(self, vid): self.set_ai(vid, "disabled")
    def teleport(self, vid, pos, yaw: float): raise NotImplementedError
    def reset_to_start(self, vid): raise NotImplementedError
    def object_pos(self, obj_id: str) -> tuple: raise NotImplementedError
    def camera_player(self, vid, candidates: list, config: dict | None = None) -> str: raise NotImplementedError
    def camera_free(self, pos, direction): raise NotImplementedError
    def damage(self, vid): return None
    @property
    def frame(self): raise NotImplementedError
