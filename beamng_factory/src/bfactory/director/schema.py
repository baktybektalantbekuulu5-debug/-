"""Structured plan produced by the Director from a free-text video scenario."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActorKind(str, Enum):
    """Vehicle category; the planner maps it to a concrete in-game model."""

    sports_car = "sports_car"
    sedan = "sedan"
    suv = "suv"
    pickup = "pickup"
    truck = "truck"
    semi = "semi"
    bus = "bus"
    police = "police"
    van = "van"
    hatchback = "hatchback"
    offroad = "offroad"
    generic = "generic"


class ActorRole(str, Enum):
    """Narrative role of an actor in the video."""

    hero = "hero"
    obstacle = "obstacle"
    pursuer = "pursuer"
    fugitive = "fugitive"
    traffic = "traffic"
    other = "other"


class ActionType(str, Enum):
    drive = "drive"
    accelerate = "accelerate"
    brake = "brake"
    stop = "stop"
    overtake = "overtake"
    chase = "chase"
    flee = "flee"
    swerve = "swerve"
    lose_control = "lose_control"
    rollover = "rollover"
    crash_into = "crash_into"
    jump = "jump"
    drift = "drift"
    appear = "appear"
    follow = "follow"


class LocationType(str, Enum):
    highway = "highway"
    city = "city"
    offroad = "offroad"
    track = "track"
    mountain = "mountain"
    gridmap = "gridmap"
    any = "any"


class Weather(str, Enum):
    clear = "clear"
    rain = "rain"
    fog = "fog"
    snow = "snow"


class CameraHint(str, Enum):
    follow = "follow"
    front = "front"
    drone = "drone"
    cinematic = "cinematic"
    slowmo = "slowmo"
    replay = "replay"


class ActorColor(BaseModel):
    """Named color with an RGBA value, each channel in 0..1."""

    name: str
    rgba: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _check_range(self) -> ActorColor:
        if any(not 0.0 <= c <= 1.0 for c in self.rgba):
            raise ValueError("rgba channels must be within 0..1")
        return self


class Actor(BaseModel):
    """A vehicle taking part in the video, shared across scenes."""

    id: str = Field(description='Stable id such as "car1"')
    kind: ActorKind = ActorKind.generic
    role: ActorRole = ActorRole.other
    color: ActorColor | None = None
    descriptors: list[str] = Field(default_factory=list)
    model_hint: str | None = Field(
        default=None, description="Concrete game model, filled later by the planner"
    )


class Action(BaseModel):
    """One step of a scene, performed by an actor."""

    type: ActionType
    actor: str = Field(description="Id of the acting actor")
    target: str | None = Field(default=None, description="Id of the target actor")
    speed_kmh: float | None = Field(default=None, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)


class Environment(BaseModel):
    """Where and when a scene happens.

    ``time_of_day`` is a fraction of the day: 0.0 = midnight, 0.5 = noon.
    The game layer converts it to the engine's own convention.
    """

    location_type: LocationType = LocationType.any
    time_of_day: float | None = Field(default=None, ge=0.0, le=1.0)
    weather: Weather | None = None


class Scene(BaseModel):
    """A coherent event, usually ending at a highlight (crash, rollover, jump)."""

    index: int = Field(ge=0)
    description: str
    environment: Environment = Field(default_factory=Environment)
    actors: list[str] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    duration_s: float = Field(default=5.0, gt=0)
    highlight: int | None = Field(
        default=None, description="Index into actions of the climax action"
    )
    camera_hints: list[CameraHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_highlight(self) -> Scene:
        if self.highlight is not None and not 0 <= self.highlight < len(self.actions):
            raise ValueError(f"scene {self.index}: highlight index out of range")
        return self


class ScriptPlan(BaseModel):
    """Complete structured plan of a video."""

    model_config = ConfigDict(validate_assignment=False)

    title: str
    language: str = Field(description='ISO code, e.g. "ru" or "en"')
    actors: list[Actor] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    target_format: Literal["shorts", "long"] | None = None
    total_duration_s: float = Field(default=0.0, ge=0)
    parser: Literal["rule", "llm"] = "rule"
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> ScriptPlan:
        ids = [a.id for a in self.actors]
        if len(ids) != len(set(ids)):
            raise ValueError("actor ids must be unique")
        known = set(ids)
        for scene in self.scenes:
            for act in scene.actions:
                for ref in (act.actor, act.target):
                    if ref is not None and ref not in known:
                        raise ValueError(
                            f"scene {scene.index}: unknown actor id {ref!r}"
                        )
            for ref in scene.actors:
                if ref not in known:
                    raise ValueError(f"scene {scene.index}: unknown actor id {ref!r}")
        return self

    def actor(self, actor_id: str) -> Actor:
        """Return the actor with the given id."""
        for a in self.actors:
            if a.id == actor_id:
                return a
        raise KeyError(actor_id)
