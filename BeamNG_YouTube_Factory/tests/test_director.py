import pytest

from ai_director.catalog import Catalog
from ai_director.director import Director
from ai_director.providers import AIError, AIProvider, extract_json
from core.models import JobRequest

SCRIPT = ("Красный Lamborghini едет по горной дороге, разгоняется, перепрыгивает через автобус, "
          "теряет управление и врезается в стену.")


def plan_for(script=SCRIPT, **kw):
    return Director().make_plan(JobRequest(script=script, **kw))


def test_example_scenario_structure():
    p = plan_for()
    assert len(p.scenes) == 2
    road, stunt = p.scenes
    assert [a.type for a in road.actions] == ["follow_road"]
    assert road.map == "west_coast_usa"
    assert [a.type for a in stunt.actions] == ["accelerate", "jump", "lose_control", "crash"]
    kinds = [o.type for o in stunt.objects]
    assert kinds == ["ramp", "obstacle_vehicle", "wall"]
    assert stunt.objects[1].params["model"] == "citybus"
    assert set(stunt.expected_events) == {"jump", "loss_of_control", "crash"}
    assert stunt.map == "gridmap_v2"            # трюки только на ровной карте


def test_lamborghini_alternative_and_color():
    p = plan_for()
    hero = p.scenes[0].vehicles[0]
    assert hero.model == "scintilla" and hero.color.startswith("красн")
    assert any("lamborghini" in a.lower() for a in p.alternatives)
    assert Catalog().color_rgba(hero.color)[0] > 0.5


def test_ramp_far_enough_for_speed():
    stunt = plan_for().scenes[1]
    ramp = stunt.objects[0]
    assert ramp.forward >= (100 / 3.6) ** 2 / 12 + 10   # хватает места разогнаться
    wall = stunt.objects[-1]
    assert wall.forward > ramp.forward


def test_explicit_speed_and_scenes():
    p = plan_for("Синий пикап разгоняется до 90 км/ч.\n\nЖёлтый суперкар врезается в стену на 140 км/ч.")
    assert len(p.scenes) == 2
    assert p.scenes[0].actions[0].params["target_kph"] == 90
    assert p.scenes[0].vehicles[0].model == "pickup"
    assert p.scenes[1].actions[-1].params["kph"] >= 100


def test_unrecognized_script_warns():
    p = plan_for("Просто красивый закат")
    assert any("не найдено" in w for w in p.warnings)
    assert p.scenes


def test_overrides():
    p = plan_for(car="pickup", map="gridmap_v2")
    assert all(v.model == "pickup" for s in p.scenes for v in s.vehicles if v.role == "hero")


def test_resource_substitution_when_not_installed():
    d = Director()
    p = d.make_plan(JobRequest(script=SCRIPT), installed_cars={"etk800", "citybus"}, installed_levels={"gridmap_v2", "west_coast_usa"})
    assert all(v.model in {"etk800", "citybus"} for s in p.scenes for v in s.vehicles)
    assert any("не установлена" in w for w in p.warnings)


def test_missing_level_gets_alternative():
    p = Director().make_plan(JobRequest(script=SCRIPT), installed_cars=None, installed_levels={"smallgrid"})
    assert all(s.map == "smallgrid" for s in p.scenes if s.map != "west_coast_usa") or any("не установлена" in w for w in p.warnings)


class FakeLLM(AIProvider):
    name = "fake"

    def __init__(self, payload):
        self.payload = payload

    def complete(self, system, user, max_tokens=4000):
        if isinstance(self.payload, Exception):
            raise self.payload
        return "Вот план:\n```json\n" + self.payload + "\n```"


LLM_PLAN = """{"title":"Тест","summary":"s","scenes":[{"id":1,"description":"d","map":"nonexistent_map",
 "vehicles":[{"id":"hero","model":"ferrari_f40","role":"hero"}],
 "objects":[{"type":"ramp","id":"r1","forward":100}],
 "actions":[{"type":"fly_to_moon","vehicle":"hero","params":{}},{"type":"jump","vehicle":"hero","params":{"kph":90,"ramp":"zzz"}}]}]}"""


def test_llm_plan_is_sanitized():
    p = Director(FakeLLM(LLM_PLAN)).make_plan(JobRequest(script="x"))
    s = p.scenes[0]
    assert p.provider == "fake"
    assert s.map == "gridmap_v2"                       # неизвестная карта заменена
    assert s.vehicles[0].model == Catalog().cars[0]["model"]
    assert [a.type for a in s.actions] == ["jump"]     # выдуманное действие удалено
    assert s.actions[0].params["ramp"] == "ramp_auto"  # рампа добавлена
    assert len(p.warnings) >= 3


def test_llm_failure_falls_back_to_offline():
    p = Director(FakeLLM(AIError("нет сети"))).make_plan(JobRequest(script=SCRIPT))
    assert p.provider == "offline" and len(p.scenes) == 2
    assert any("не ответила" in w for w in p.warnings)


def test_extract_json():
    assert extract_json('текст {"a": 1} конец') == {"a": 1}
    with pytest.raises(AIError):
        extract_json("нет json")
