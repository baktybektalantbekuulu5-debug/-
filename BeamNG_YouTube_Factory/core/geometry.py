"""Геометрия сцены: система координат относительно точки старта, кватернионы."""
import math


def yaw_of(d) -> float:
    return math.atan2(d[1], d[0])


def wrap(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def fwd_vec(yaw): return (math.cos(yaw), math.sin(yaw))


def left_vec(yaw): return (-math.sin(yaw), math.cos(yaw))


def quat_z(angle):
    return (0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2))


def quat_x(angle):
    return (math.sin(angle / 2), 0.0, 0.0, math.cos(angle / 2))


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


class Frame:
    """Сцена: начало O и курс yaw. Позиции объектов задаются (вперёд, влево)."""

    def __init__(self, origin, yaw):
        self.origin = tuple(origin)
        self.yaw = yaw

    def world(self, forward, lateral, z=None):
        f, l = fwd_vec(self.yaw), left_vec(self.yaw)
        return (self.origin[0] + f[0] * forward + l[0] * lateral,
                self.origin[1] + f[1] * forward + l[1] * lateral,
                self.origin[2] if z is None else z)

    def local(self, pos):
        dx, dy = pos[0] - self.origin[0], pos[1] - self.origin[1]
        f, l = fwd_vec(self.yaw), left_vec(self.yaw)
        return dx * f[0] + dy * f[1], dx * l[0] + dy * l[1]


def ramp_geometry(frame: Frame, forward, lateral, length, width, angle_deg, thickness=0.4):
    """Центр и кватернион наклонной плиты (ProceduralCube), нижняя кромка у земли.
    Размер куба: (ширина по X, длина по Y, толщина по Z). Локальная ось +Y направлена вдоль курса."""
    a = math.radians(angle_deg)
    cx = forward + (length / 2) * math.cos(a)
    cz = frame.origin[2] + (length / 2) * math.sin(a) + (thickness / 2) * math.cos(a)
    pos = frame.world(cx, lateral, cz)
    q = quat_mul(quat_z(frame.yaw - math.pi / 2), quat_x(a))
    return pos, q, (width, length, thickness)
