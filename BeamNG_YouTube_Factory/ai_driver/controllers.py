"""Регуляторы управления автомобилем (чистая математика, без игры)."""
import math

from core.geometry import wrap, fwd_vec, left_vec


def clip(x, lo, hi):
    return max(lo, min(hi, x))


class SpeedController:
    """Выдаёт (throttle, brake) по разнице скоростей (м/с)."""

    def __init__(self, kp=0.35, ki=0.04, brake_kp=0.25, max_throttle=1.0):
        self.kp, self.ki, self.brake_kp, self.max_throttle = kp, ki, brake_kp, max_throttle
        self.integ = 0.0

    def step(self, target, speed, dt):
        err = target - speed
        if err >= -0.5:
            self.integ = clip(self.integ + err * dt, -5, 5)
            thr = clip(self.kp * err + self.ki * self.integ, 0.0, self.max_throttle)
            return thr, 0.0
        self.integ = 0.0
        return 0.0, clip(-err * self.brake_kp, 0.0, 1.0)


class LineTracker:
    """Следование прямой (origin, yaw) по схеме Стэнли. Возвращает руль «влево положительный» [-1..1]."""

    def __init__(self, origin_xy, yaw, k_head=0.9, k_cte=1.4):
        self.origin, self.yaw, self.k_head, self.k_cte = origin_xy, yaw, k_head, k_cte

    def cte(self, pos):
        """Смещение машины влево от линии, м."""
        l = left_vec(self.yaw)
        return (pos[0] - self.origin[0]) * l[0] + (pos[1] - self.origin[1]) * l[1]

    def steer(self, pos, car_yaw, speed):
        c = self.cte(pos)
        desired = self.yaw - math.atan2(self.k_cte * c, speed + 3.0)
        err = wrap(desired - car_yaw)
        return clip(self.k_head * err / (1.0 + speed / 18.0) * 2.2, -1.0, 1.0)


class PointTracker:
    """Движение к точке в мире (таран, подъезд к рампе)."""

    def __init__(self, target_xy, k=0.9):
        self.target, self.k = target_xy, k

    def steer(self, pos, car_yaw, speed):
        desired = math.atan2(self.target[1] - pos[1], self.target[0] - pos[0])
        err = wrap(desired - car_yaw)
        return clip(self.k * err / (1.0 + speed / 18.0) * 2.2, -1.0, 1.0)

    def distance(self, pos):
        return math.hypot(self.target[0] - pos[0], self.target[1] - pos[1])


class HeadingHold:
    def __init__(self, yaw, k=0.9):
        self.yaw, self.k = yaw, k

    def steer(self, pos, car_yaw, speed):
        err = wrap(self.yaw - car_yaw)
        return clip(self.k * err / (1.0 + speed / 18.0) * 2.2, -1.0, 1.0)
