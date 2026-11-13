"""Модели данных: план съёмки, сцены, действия, события."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

ACTION_TYPES = ("cruise", "accelerate", "brake", "turn", "follow_road", "jump",
                "lose_control", "crash", "wait", "chase")
OBJECT_TYPES = ("ramp", "wall", "obstacle_vehicle", "cones")
CAMERA_MODES = ("chase", "orbit", "hood", "driver", "tripod", "flyby", "drone", "side", "front_low")
EVENT_TYPES = ("jump", "landing", "crash", "loss_of_control", "top_speed", "finish")


@dataclass
class VehicleSpec:
    id: str = "hero"
    model: str = "etk800"
    color: str = ""
    role: str = "hero"            # hero | rival | obstacle
    forward: float = 0.0          # смещение от точки старта, м (вперёд)
    lateral: float = 0.0          # смещение, м (влево +)
    yaw_deg: float = 0.0          # поворот относительно направления старта
    requested: str = ""           # что просил пользователь (напр. "Lamborghini")
    note: str = ""


@dataclass
class ObjectSpec:
    type: str = "ramp"
    id: str = ""
    forward: float = 30.0
    lateral: float = 0.0
    params: dict = field(default_factory=dict)  # ramp: length,width,angle_deg; wall: width,height; obstacle_vehicle: model


@dataclass
class ActionSpec:
    type: str = "cruise"
    vehicle: str = "hero"
    params: dict = field(default_factory=dict)  # kph, duration, angle_deg, distance, target ...


@dataclass
class CameraShot:
    mode: str = "chase"
    start: float = 0.0            # секунды от начала сцены
    params: dict = field(default_factory=dict)


@dataclass
class Scene:
    id: int = 1
    description: str = ""
    map: str = "west_coast_usa"
    vehicles: list[VehicleSpec] = field(default_factory=list)
    objects: list[ObjectSpec] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    shots: list[CameraShot] = field(default_factory=list)
    expected_events: list[str] = field(default_factory=list)
    max_duration: float = 45.0
    start_override: dict | None = None  # {"pos":[x,y,z],"dir":[dx,dy]}


@dataclass
class Plan:
    title: str = "Без названия"
    summary: str = ""
    scenes: list[Scene] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    source_script: str = ""
    provider: str = "offline"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Plan":
        scenes = []
        for s in d.get("scenes", []):
            scenes.append(Scene(
                id=int(s.get("id", len(scenes) + 1)),
                description=s.get("description", ""),
                map=s.get("map", "west_coast_usa"),
                vehicles=[VehicleSpec(**_pick(v, VehicleSpec)) for v in s.get("vehicles", [])],
                objects=[ObjectSpec(**_pick(o, ObjectSpec)) for o in s.get("objects", [])],
                actions=[ActionSpec(**_pick(a, ActionSpec)) for a in s.get("actions", [])],
                shots=[CameraShot(**_pick(c, CameraShot)) for c in s.get("shots", [])],
                expected_events=list(s.get("expected_events", [])),
                max_duration=float(s.get("max_duration", 45.0)),
                start_override=s.get("start_override"),
            ))
        return Plan(title=d.get("title", "Без названия"), summary=d.get("summary", ""),
                    scenes=scenes, warnings=list(d.get("warnings", [])),
                    alternatives=list(d.get("alternatives", [])),
                    source_script=d.get("source_script", ""), provider=d.get("provider", "offline"))


def _pick(d: dict, cls) -> dict:
    names = set(cls.__dataclass_fields__)
    return {k: v for k, v in d.items() if k in names}


@dataclass
class Event:
    t: float                      # секунды от начала записи (видео)
    type: str
    vehicle: str = "hero"
    data: dict = field(default_factory=dict)


@dataclass
class Take:
    scene_id: int
    index: int
    video: str = ""
    events: list[Event] = field(default_factory=list)
    ok: bool = False
    camera_preset: str = ""
    duration: float = 0.0
    error: str = ""

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        t = Take(scene_id=d["scene_id"], index=d["index"], video=d.get("video", ""),
                 ok=d.get("ok", False), camera_preset=d.get("camera_preset", ""),
                 duration=d.get("duration", 0.0), error=d.get("error", ""))
        t.events = [Event(**e) for e in d.get("events", [])]
        return t


@dataclass
class JobRequest:
    script: str
    car: str = "auto"             # "auto" или id модели
    map: str = "auto"
    duration: int = 30            # секунд итогового видео
    resolution: str = "1080p"     # 720p | 1080p | 1440p
    fps: int = 60
    camera_style: str = "cinematic"   # cinematic | chase | action
    takes_per_scene: int = 1
    vertical: bool = True         # Shorts 9:16
    horizontal: bool = False      # дополнительно 16:9
    crop_mode: str = "smart"      # smart | blur
    music: bool = True
    sfx: bool = True
    upload: bool = False

    def to_dict(self):
        return asdict(self)
