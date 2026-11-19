"""Tests for the Director (scenario -> ScriptPlan)."""

from __future__ import annotations

import logging

import pytest

from bfactory.director import (
    ActionType,
    ActorKind,
    ActorRole,
    CameraHint,
    LocationType,
    ScriptPlan,
    Weather,
    parse_script,
)
from bfactory.director.llm_parser import LLMUnavailableError, parse_llm

EXAMPLE = (
    "Красный спортивный автомобиль разгоняется по трассе. "
    "Впереди появляется грузовик. "
    "Спорткар пытается увернуться, теряет управление и переворачивается."
)


def _types(scene) -> list[ActionType]:
    return [a.type for a in scene.actions]


def test_reference_example() -> None:
    plan = parse_script(EXAMPLE)
    assert plan.language == "ru"
    assert len(plan.actors) == 2
    car, truck = plan.actors
    assert car.kind == ActorKind.sports_car
    assert car.color is not None and car.color.name == "red"
    assert car.color.rgba[0] > 0.5
    assert truck.kind == ActorKind.truck
    assert truck.role == ActorRole.obstacle

    assert len(plan.scenes) == 1
    scene = plan.scenes[0]
    assert scene.environment.location_type == LocationType.highway
    assert _types(scene) == [
        ActionType.accelerate,
        ActionType.appear,
        ActionType.swerve,
        ActionType.lose_control,
        ActionType.rollover,
    ]
    acc, appear, swerve, lose, roll = scene.actions
    assert acc.actor == car.id
    assert appear.actor == truck.id
    assert swerve.actor == car.id and swerve.target == truck.id
    assert lose.actor == car.id and roll.actor == car.id
    assert scene.highlight == 4
    assert CameraHint.slowmo in scene.camera_hints
    assert CameraHint.replay in scene.camera_hints
    assert scene.duration_s > 10
    assert plan.total_duration_s == pytest.approx(scene.duration_s)


def test_chase_with_pronoun_and_speed() -> None:
    plan = parse_script(
        "Ночью в городе синий седан мчится на скорости 180 км/ч. "
        "За ним гонится полиция. Полиция догоняет седан и таранит его."
    )
    kinds = {a.kind for a in plan.actors}
    assert kinds == {ActorKind.sedan, ActorKind.police}
    sedan = next(a for a in plan.actors if a.kind == ActorKind.sedan)
    police = next(a for a in plan.actors if a.kind == ActorKind.police)
    actions = [a for s in plan.scenes for a in s.actions]
    chases = [a for a in actions if a.type == ActionType.chase]
    assert chases and all(a.actor == police.id and a.target == sedan.id for a in chases)
    crash = next(a for a in actions if a.type == ActionType.crash_into)
    assert crash.actor == police.id and crash.target == sedan.id
    drive = next(a for a in actions if a.type == ActionType.drive)
    assert drive.speed_kmh == 180
    assert police.role == ActorRole.pursuer
    assert sedan.role == ActorRole.fugitive
    env = plan.scenes[0].environment
    assert env.location_type == LocationType.city
    assert env.time_of_day == 0.0
    hints = {h for s in plan.scenes for h in s.camera_hints}
    assert {CameraHint.follow, CameraHint.drone} <= hints


def test_explicit_scene_headers() -> None:
    plan = parse_script(
        "Сцена 1: Чёрный джип едет по бездорожью под дождём.\n"
        "Сцена 2: Джип прыгает с трамплина и переворачивается.\n"
        "Сцена 3: Второй джип врезается в него."
    )
    assert len(plan.scenes) == 3
    assert [s.index for s in plan.scenes] == [0, 1, 2]
    assert len(plan.actors) == 2
    first, second = plan.actors
    assert first.color is not None and first.color.name == "black"
    assert _types(plan.scenes[0]) == [ActionType.drive]
    assert plan.scenes[0].highlight is None
    assert _types(plan.scenes[1]) == [ActionType.jump, ActionType.rollover]
    assert plan.scenes[1].actions[0].params.get("ramp") is True
    crash = plan.scenes[2].actions[0]
    assert crash.type == ActionType.crash_into
    assert crash.actor == second.id and crash.target == first.id
    for scene in plan.scenes:  # environment is inherited
        assert scene.environment.location_type == LocationType.offroad
        assert scene.environment.weather == Weather.rain


def test_auto_scene_split_on_highlight() -> None:
    plan = parse_script(
        "Белый пикап едет по серпантину. Пикап врезается в отбойник. "
        "Затем жёлтый автобус обгоняет фуру."
    )
    assert len(plan.scenes) == 2
    assert plan.scenes[0].actions[-1].type == ActionType.crash_into
    assert plan.scenes[0].actions[-1].params.get("object")
    assert plan.scenes[0].environment.location_type == LocationType.mountain
    assert _types(plan.scenes[1]) == [ActionType.overtake]


def test_english_input() -> None:
    plan = parse_script(
        "A red sports car drives down the highway at 120 mph. Suddenly a truck appears ahead. "
        "The sports car swerves, loses control and rolls over."
    )
    assert plan.language == "en"
    assert [a.kind for a in plan.actors] == [ActorKind.sports_car, ActorKind.truck]
    scene = plan.scenes[0]
    assert scene.environment.location_type == LocationType.highway
    assert _types(scene) == [
        ActionType.drive,
        ActionType.appear,
        ActionType.swerve,
        ActionType.lose_control,
        ActionType.rollover,
    ]
    assert scene.actions[0].speed_kmh == pytest.approx(193.1, abs=0.5)
    assert scene.actions[2].target == plan.actors[1].id
    assert scene.highlight == 4


@pytest.mark.parametrize(
    ("text", "color"),
    [
        ("Зелёная машина едет.", "green"),
        ("Зеленая машина едет.", "green"),
        ("Жёлтый седан едет.", "yellow"),
        ("Желтого седана обгоняет пикап.", "yellow"),
        ("Чёрный внедорожник едет.", "black"),
        ("Черном внедорожнике едет водитель.", "black"),
        ("Красного спорткара не видно, он едет.", "red"),
        ("Синяя машина едет.", "blue"),
        ("Голубой хэтчбек едет.", "light_blue"),
        ("Серебристый седан едет.", "silver"),
        ("Серый фургон едет.", "gray"),
        ("Оранжевый автобус едет.", "orange"),
        ("Фиолетовая машина едет.", "purple"),
        ("Розовый пикап едет.", "pink"),
        ("Коричневый грузовик едет.", "brown"),
        ("Белый седан едет.", "white"),
    ],
)
def test_colors_with_yo_variants(text: str, color: str) -> None:
    plan = parse_script(text)
    colored = [a for a in plan.actors if a.color is not None]
    assert colored and colored[0].color.name == color  # type: ignore[union-attr]


def test_kind_synonyms() -> None:
    cases = {
        "Спортивная машина едет.": ActorKind.sports_car,
        "Фура едет.": ActorKind.semi,
        "Тягач едет.": ActorKind.semi,
        "Грузовик едет.": ActorKind.truck,
        "Полицейская машина едет.": ActorKind.police,
        "Автобус едет.": ActorKind.bus,
        "Микроавтобус едет.": ActorKind.van,
        "Внедорожник едет.": ActorKind.suv,
        "Джип едет.": ActorKind.offroad,
        "Пикап едет.": ActorKind.pickup,
    }
    for text, kind in cases.items():
        plan = parse_script(text)
        assert [a.kind for a in plan.actors] == [kind], text


def test_same_noun_vs_new_actor() -> None:
    plan = parse_script(
        "Красный седан едет. Седан тормозит. Другой седан обгоняет его."
    )
    assert len(plan.actors) == 2
    plan = parse_script("Красный седан едет. Синий седан обгоняет красный седан.")
    assert len(plan.actors) == 2
    overtake = next(
        a for s in plan.scenes for a in s.actions if a.type == ActionType.overtake
    )
    assert overtake.actor == "car2" and overtake.target == "car1"


def test_speed_extraction() -> None:
    plan = parse_script("Спорткар разгоняется до 250 км/ч, а потом тормозит.")
    acc, brake = plan.scenes[0].actions
    assert acc.type == ActionType.accelerate and acc.speed_kmh == 250
    assert brake.type == ActionType.brake and brake.speed_kmh is None
    plan = parse_script("Машина едет со скоростью 90,5 км в час.")
    assert plan.scenes[0].actions[0].speed_kmh == 90.5


def test_weather_time_and_format() -> None:
    plan = parse_script("Шортс. На закате в тумане фура дрифтует на гоночной трассе.")
    env = plan.scenes[0].environment
    assert env.location_type == LocationType.track
    assert env.weather == Weather.fog
    assert env.time_of_day == pytest.approx(0.78)
    assert plan.target_format == "shorts"
    assert _types(plan.scenes[0]) == [ActionType.drift]


def test_json_round_trip() -> None:
    plan = parse_script(EXAMPLE)
    restored = ScriptPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert isinstance(restored.actors[0].color.rgba, tuple)  # type: ignore[union-attr]


def test_schema_rejects_unknown_actor() -> None:
    data = parse_script(EXAMPLE).model_dump()
    data["scenes"][0]["actions"][0]["actor"] = "car99"
    with pytest.raises(ValueError):
        ScriptPlan.model_validate(data)


def test_empty_text_raises() -> None:
    with pytest.raises(ValueError):
        parse_script("   ")


def test_llm_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(LLMUnavailableError):
        parse_llm(EXAMPLE)


def test_llm_fallback_without_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with caplog.at_level(logging.WARNING, logger="bfactory.director"):
        plan = parse_script(EXAMPLE, use_llm=True)
    assert plan.parser == "rule"
    assert plan == parse_script(EXAMPLE).model_copy(update={"warnings": plan.warnings})
    assert any("falling back" in r.getMessage() for r in caplog.records)
    assert any("llm fallback" in w for w in plan.warnings)
