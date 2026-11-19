"""Проверка адаптера к beamngpy НА РЕАЛЬНЫХ классах пакета (Scenario, Vehicle, ProceduralCube),
без запуска игры: подменены только сетевое соединение и сенсоры. Это ловит неверные сигнатуры вызовов."""
import math
from unittest.mock import MagicMock, patch

import pytest

beamngpy = pytest.importorskip("beamngpy")

from ai_director.catalog import Catalog
from ai_director.director import Director
from core.models import JobRequest
from environment.beamng_session import BeamNGRuntime, BeamNGSession
from ai_driver.runtime_base import CameraUnsupported


def stunt_scene():
    plan = Director().make_plan(JobRequest(script="Красный Lamborghini разгоняется, перепрыгивает через автобус и врезается в стену"))
    return plan.scenes[0]


def make_session(settings):
    s = BeamNGSession(settings, Catalog())
    s.bng = MagicMock()
    return s


def test_load_scene_builds_valid_beamngpy_scenario(settings):
    sess = make_session(settings)
    made = {}

    def fake_make(self, bng):
        made["scenario"] = self

    state = {"pos": (0, 0, 0.3), "dir": (0.0, 1.0, 0.0), "vel": (0, 0, 0), "rotation": (0, 0, 0, 1)}
    with patch.object(beamngpy.Scenario, "make", fake_make), \
         patch.object(beamngpy.Vehicle, "connect", lambda self, bng, tries=5: None), \
         patch.object(beamngpy.Vehicle, "is_connected", lambda self: True), \
         patch("beamngpy.vehicle.sensors.Sensors.poll", lambda self, *a: None), \
         patch("beamngpy.vehicle.sensors.Sensors.__getitem__", lambda self, k: state), \
         patch("time.sleep", lambda *_: None), \
         patch.object(beamngpy.Vehicle, "teleport", lambda self, *a, **k: True):
        rt = sess.load_scene(stunt_scene(), "unit_test")
    sc = made["scenario"]
    assert sc.level == "gridmap_v2"
    hero = sc.vehicles["hero"]
    assert hero.model == "scintilla" and hero.options["color"] == pytest.approx((0.8, 0.02, 0.02, 1.0))
    assert "obstacle1" in sc.vehicles and sc.vehicles["obstacle1"].model == "citybus"
    names = set(sc.proc_meshes)
    assert {"ramp1", "wall1"} <= names
    sess.bng.scenario.load.assert_called_once()
    sess.bng.scenario.start.assert_called_once()
    assert set(rt.objects) == {"ramp1", "obstacle1", "wall1"} and "hero" in rt.home_pose


def test_runtime_forwards_calls_with_real_signatures():
    bng = MagicMock()
    v = beamngpy.Vehicle("hero", "etk800")
    v.connection = MagicMock()
    ctrl = MagicMock()
    with patch.object(beamngpy.Vehicle, "control", ctrl):
        rt = BeamNGRuntime(bng, {"hero": v}, {}, MagicMock())
        rt.control("hero", steering=0.2, throttle=1.0, brake=0.0, parkingbrake=0.0)
    ctrl.assert_called_once_with(steering=0.2, throttle=1.0, brake=0.0, parkingbrake=0.0)
    rt.camera_free((1, 2, 3), (0, 1, 0))
    bng.camera.set_free.assert_called_with((1, 2, 3), (0, 1, 0))
    bng.camera.get_player_modes.return_value = {"orbit": {}, "driver": {}}
    assert rt.camera_player("hero", ["external", "orbit"]) == "orbit"
    bng.camera.set_player_mode.assert_called_with(v, "orbit", {})
    with pytest.raises(CameraUnsupported):
        rt.camera_player("hero", ["nonexistent"])
    bng.camera.set_free.side_effect = RuntimeError("tech only")
    with pytest.raises(CameraUnsupported):
        rt.camera_free((0, 0, 0), (1, 0, 0))


def test_used_beamngpy_api_exists():
    """Все вызовы, которые использует адаптер, существуют в установленной версии beamngpy."""
    from beamngpy.api.beamng import CameraApi, ScenarioApi
    from beamngpy.api.vehicle import AIApi
    for cls, names in ((CameraApi, ["set_free", "set_player_mode", "get_player_modes"]),
                       (ScenarioApi, ["load", "start", "stop"]),
                       (AIApi, ["set_mode", "set_speed", "set_target", "set_aggression"]),
                       (beamngpy.Vehicle, ["control", "teleport", "connect"]),
                       (beamngpy.Scenario, ["add_vehicle", "add_procedural_mesh", "make"]),
                       (beamngpy.BeamNGpy, ["open", "close"])):
        for n in names:
            assert hasattr(cls, n), f"{cls.__name__}.{n} отсутствует в beamngpy {getattr(beamngpy, '__version__', '?')}"
