"""Реальная связь с BeamNG.drive через beamngpy. Единственный модуль, который импортирует beamngpy.

Используются ТОЛЬКО вызовы, существующие в beamngpy 1.3x (проверено по установленному пакету):
BeamNGpy.open/close, Scenario.add_vehicle/add_procedural_mesh/make, bng.scenario.load/start,
Vehicle.control/teleport, vehicle.ai.set_mode/set_speed/set_target/set_aggression,
bng.camera.set_free/set_player_mode/get_player_modes, vehicle.sensors.poll (сенсор State).
"""
import math
import time

from core.geometry import Frame, quat_z, ramp_geometry, wrap
from core.logger import get_logger
from core.models import Scene
from ai_driver.runtime_base import CameraUnsupported, SceneRuntime, VState
from ai_director.catalog import Catalog
from environment.manager import resolve_start

log = get_logger("beamng")


class BeamNGRuntime(SceneRuntime):
    def __init__(self, bng, vehicles: dict, objects: dict, frame: Frame):
        self.bng, self.vehicles, self.objects, self._frame = bng, vehicles, objects, frame
        self._t0 = time.monotonic()
        self._modes_cache = {}
        self.home_pose = {}

    @property
    def frame(self): return self._frame
    def now(self): return time.monotonic() - self._t0
    def sleep(self, dt): time.sleep(dt)

    def state(self, vid) -> VState:
        v = self.vehicles[vid]
        v.sensors.poll("state")
        s = v.sensors["state"]
        return VState(self.now(), tuple(s["pos"]), tuple(s["dir"]), tuple(s["vel"]))

    def control(self, vid, steering=None, throttle=None, brake=None, parkingbrake=None):
        self.vehicles[vid].control(steering=steering, throttle=throttle, brake=brake, parkingbrake=parkingbrake)

    def set_ai(self, vid, mode, speed_mps=None, target=None, aggression=None):
        ai = self.vehicles[vid].ai
        ai.set_mode(mode)
        if mode == "disabled":
            return
        if speed_mps:
            ai.set_speed(speed_mps, "limit")
        if aggression is not None:
            ai.set_aggression(aggression)
        if target:
            ai.set_target(target)

    def teleport(self, vid, pos, yaw):
        # у машины BeamNG передок смотрит в -Y при единичном кватернионе → θ = yaw + 90°
        self.vehicles[vid].teleport(tuple(pos), rot_quat=quat_z(yaw + math.pi / 2), reset=True)

    def reset_to_start(self, vid):
        pos, quat = self.home_pose[vid]
        self.vehicles[vid].teleport(pos, rot_quat=quat, reset=True)
        self.control(vid, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)

    def object_pos(self, obj_id): return self.objects[obj_id]

    def camera_player(self, vid, candidates, config=None):
        v = self.vehicles[vid]
        if vid not in self._modes_cache:
            try:
                self._modes_cache[vid] = list(self.bng.camera.get_player_modes(v).keys())
            except Exception as e:  # noqa: BLE001
                raise CameraUnsupported(f"get_player_modes: {e}")
        avail = self._modes_cache[vid]
        for c in candidates:
            if c in avail:
                self.bng.camera.set_player_mode(v, c, config or {})
                return c
        raise CameraUnsupported(f"нет подходящего режима среди {avail}")

    def camera_free(self, pos, direction):
        try:
            self.bng.camera.set_free(tuple(pos), tuple(direction))
        except Exception as e:  # noqa: BLE001
            raise CameraUnsupported(str(e))

    def damage(self, vid):
        try:
            v = self.vehicles[vid]
            v.sensors.poll("damage")
            return v.sensors["damage"].get("damage")
        except Exception:  # noqa: BLE001
            return None


class BeamNGSession:
    """Запуск/подключение к игре и загрузка сцен."""

    def __init__(self, settings, catalog: Catalog):
        self.s, self.catalog = settings, catalog
        self.bng = None
        self.tech = None

    def open(self):
        from beamngpy import BeamNGpy
        host, port = self.s.get("beamng.host"), int(self.s.get("beamng.port"))
        home = self.s.get("paths.beamng_home") or None
        user = self.s.get("paths.beamng_user") or None
        self.bng = BeamNGpy(host, port, home=home, user=user)
        launch = bool(self.s.get("beamng.launch"))
        log.info("%s BeamNG.drive (%s:%s)…", "Запуск" if launch else "Подключение к", host, port)
        self.bng.open(launch=launch)
        self.tech = self.bng.tech_enabled
        log.info("BeamNG подключена. tech-режим: %s", self.tech)

    def close(self):
        if self.bng:
            try:
                self.bng.close()
            except Exception as e:  # noqa: BLE001
                log.warning("закрытие BeamNG: %s", e)
            self.bng = None

    def load_scene(self, scene: Scene, name: str) -> BeamNGRuntime:
        from beamngpy import Scenario, Vehicle, ProceduralCube
        pos0, yaw, src = resolve_start(self.catalog, scene)
        log.info("Сцена %s: карта=%s старт=%s (%s)", scene.id, scene.map, pos0, src)
        frame = Frame(pos0, yaw)
        sc = Scenario(scene.map, name, description="BeamNG YouTube Factory")
        vehicles, obj_pos = {}, {}
        for i, vs in enumerate(scene.vehicles):
            kw = {}
            rgba = self.catalog.color_rgba(vs.color)
            if rgba:
                kw["color"] = rgba
            v = Vehicle(vs.id, model=vs.model, license="FACTORY", **kw)
            p = frame.world(vs.forward, vs.lateral)
            sc.add_vehicle(v, pos=p, rot_quat=quat_z(frame.yaw + math.radians(vs.yaw_deg) + math.pi / 2))
            vehicles[vs.id] = v
        for o in scene.objects:
            if o.type == "ramp":
                pr = o.params
                pos, q, size = ramp_geometry(frame, o.forward, o.lateral, pr.get("length", 8), pr.get("width", 5), pr.get("angle_deg", 15))
                sc.add_procedural_mesh(ProceduralCube(pos, size, o.id, rot_quat=q))
                obj_pos[o.id] = frame.world(o.forward + pr.get("length", 8) / 2, o.lateral)
            elif o.type == "wall":
                pr = o.params
                w, h, t = pr.get("width", 60), pr.get("height", 3), pr.get("thickness", 1.5)
                pos = frame.world(o.forward, o.lateral, frame.origin[2] + h / 2)
                q = quat_z(frame.yaw - math.pi / 2)   # ширина (локальная X) поперёк курса
                sc.add_procedural_mesh(ProceduralCube(pos, (w, t, h), o.id, rot_quat=q))
                obj_pos[o.id] = frame.world(o.forward, o.lateral)
            elif o.type == "obstacle_vehicle":
                v = Vehicle(o.id, model=o.params.get("model", "citybus"), license="OBSTACLE")
                p = frame.world(o.forward, o.lateral)
                yaw = frame.yaw + math.radians(o.params.get("yaw_deg", 90))
                sc.add_vehicle(v, pos=p, rot_quat=quat_z(yaw + math.pi / 2))
                vehicles[o.id] = v
                obj_pos[o.id] = p
            elif o.type == "cones":
                for k in range(int(o.params.get("count", 5))):
                    cp = frame.world(o.forward + k * 3.0, o.lateral)
                    sc.add_procedural_mesh(ProceduralCube(cp, (0.4, 0.4, 0.7), f"{o.id}_{k}", rot_quat=quat_z(0)))
                obj_pos[o.id] = frame.world(o.forward, o.lateral)
        from beamngpy.sensors import Electrics
        for vs in scene.vehicles:
            try:
                vehicles[vs.id].sensors.attach("electrics", Electrics())
            except Exception:  # noqa: BLE001
                pass
        sc.make(self.bng)
        self.bng.scenario.load(sc)
        self.bng.scenario.start()
        for v in vehicles.values():
            if not v.is_connected():
                v.connect(self.bng)
        rt = BeamNGRuntime(self.bng, vehicles, obj_pos, frame)
        time.sleep(2.0)  # дать машинам встать на подвеску
        for vs in scene.vehicles:
            self._align(rt, vs.id, frame.yaw + math.radians(vs.yaw_deg))
            v = vehicles[vs.id]
            v.sensors.poll("state")
            st = v.sensors["state"]
            rt.home_pose[vs.id] = (tuple(st["pos"]), tuple(st["rotation"]))
        return rt

    @staticmethod
    def _align(rt: BeamNGRuntime, vid: str, yaw: float):
        """Если курс машины после спавна не совпал с нужным (ориентация осей зависит от модели) — поправить."""
        try:
            st = rt.state(vid)
            diff = wrap(yaw - st.yaw)
            if abs(diff) > math.radians(3):
                log.info("%s: курс отличается на %.0f° — выравниваю", vid, math.degrees(diff))
                v = rt.vehicles[vid]
                v.teleport(tuple(st.pos), rot_quat=_quat_from_diff(v, diff), reset=True)
        except Exception as e:  # noqa: BLE001
            log.warning("выравнивание %s не удалось: %s", vid, e)


def _quat_from_diff(v, diff):
    """Текущая ориентация известна из state['rotation']; добавляем поворот вокруг Z на diff."""
    from core.geometry import quat_mul
    rot = tuple(v.sensors["state"]["rotation"])
    return quat_mul(quat_z(diff), rot)
