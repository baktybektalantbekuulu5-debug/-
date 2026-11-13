import math

import pytest

from ai_driver.controllers import LineTracker, SpeedController
from ai_driver.driver import Driver
from ai_driver.events import EventDetector
from core.geometry import Frame, ramp_geometry, quat_mul, quat_z
from core.models import ActionSpec, Scene
from core.stop import CancelToken, StopRequested
from fakes import FakeRuntime


def world(sign=1, yaw_deg=70):
    fr = Frame((10.0, -5.0, 0.3), math.radians(yaw_deg))
    rt = FakeRuntime(fr, steer_hidden_sign=sign)
    rt.objects = {"ramp1": (fr.world(130, 0), "ramp"), "wall1": (fr.world(330, 0), "wall")}
    rt.ramp_at = 130
    return fr, rt


@pytest.mark.parametrize("sign", [1, -1])
def test_steer_calibration_detects_sign(sign):
    fr, rt = world(sign)
    d = Driver(rt)
    assert d.calibrate_steer() == sign


@pytest.mark.parametrize("sign", [1, -1])
def test_full_stunt_sequence(sign):
    fr, rt = world(sign)
    d = Driver(rt)
    d.calibrate_steer()
    rt.reset_to_start("hero")
    sc = Scene(actions=[ActionSpec("accelerate", "hero", {"target_kph": 120}),
                        ActionSpec("jump", "hero", {"kph": 110, "ramp": "ramp1", "landing_distance": 180}),
                        ActionSpec("lose_control", "hero", {"duration": 2.5}),
                        ActionSpec("crash", "hero", {"kph": 110, "target": "wall1"})], max_duration=80)
    evs = d.run_scene(sc)
    types = [e.type for e in evs]
    assert "jump" in types and "crash" in types and "finish" in types
    jump = next(e for e in evs if e.type == "jump")
    crash = next(e for e in evs if e.type == "crash")
    assert jump.t < crash.t
    assert 0.6 <= jump.data["airtime"] < 3
    x, y, _ = rt.state("hero").pos
    assert math.hypot(x - rt.objects["wall1"][0][0], y - rt.objects["wall1"][0][1]) < 4   # доехал до стены


def test_line_tracker_corrects_offset():
    fr, rt = world(1, 0)
    rt.cars["hero"].y += 3.0          # смещение от линии на 3 м
    rt.cars["hero"].v = 15
    trk = LineTracker(fr.origin[:2], fr.yaw)
    sc = SpeedController()
    for _ in range(400):
        st = rt.state("hero")
        thr, brk = sc.step(15, st.speed, 0.05)
        rt.control("hero", steering=trk.steer(st.pos, st.yaw, st.speed), throttle=thr, brake=brk)
        rt.sleep(0.05)
    assert abs(trk.cte(rt.state("hero").pos)) < 0.3


def test_stop_token_interrupts_scene():
    fr, rt = world()
    tok = CancelToken()
    d = Driver(rt, tok, steer_sign=1)
    n = {"i": 0}

    def tick(t, st):
        n["i"] += 1
        if n["i"] > 20:
            tok.cancel()
    d.on_tick = tick
    with pytest.raises(StopRequested):
        d.run_scene(Scene(actions=[ActionSpec("cruise", "hero", {"kph": 50, "duration": 60})], max_duration=100))


def test_scene_timeout_does_not_crash():
    fr, rt = world()
    d = Driver(rt, steer_sign=1)
    evs = d.run_scene(Scene(actions=[ActionSpec("cruise", "hero", {"kph": 50, "duration": 60})], max_duration=3))
    assert evs[-1].type == "finish" and rt.t < 5


def test_ai_actions_use_game_ai():
    fr, rt = world()
    d = Driver(rt, steer_sign=1)
    d.run_scene(Scene(actions=[ActionSpec("follow_road", "hero", {"kph": 72, "duration": 1.0})], max_duration=10))
    assert ("hero", "span", 72 / 3.6) in rt.ai_calls and rt.ai_calls[-1][1] == "disabled"


# ---------------------------------------------------------------- события
def feed(det, samples):
    for t, pos, d, vel in samples:
        det.update(t, pos, d, vel)
    return [e.type for e in det.events]


def test_event_crash_detected():
    det = EventDetector()
    s = [(i * 0.05, (i, 0, 0), (1, 0, 0), (30.0, 0, 0)) for i in range(20)]
    s += [(1.0 + i * 0.05, (30, 0, 0), (1, 0, 0), (2.0, 0, 0)) for i in range(5)]
    assert "crash" in feed(det, s)


def test_event_no_false_crash_on_normal_braking():
    det = EventDetector()
    s = [(i * 0.05, (i, 0, 0), (1, 0, 0), (max(0, 30 - i * 0.6), 0, 0)) for i in range(50)]
    assert "crash" not in feed(det, s)


def test_event_jump_and_landing():
    det = EventDetector()
    s = []
    t = 0.0
    z, vz = 0.0, 0.0
    for i in range(10):
        s.append((t, (i, 0, z), (1, 0, 0), (25, 0, 0))); t += 0.05
    vz = 6.0
    for i in range(30):
        z += vz * 0.05; vz -= 9.8 * 0.05
        s.append((t, (20 + i, 0, max(z, 0)), (1, 0, 0), (25, 0, vz))); t += 0.05
        if z <= 0 and vz < 0:
            vz = -0.2; z = 0
    for i in range(5):
        s.append((t, (60, 0, 0), (1, 0, 0), (25, 0, 0.0))); t += 0.05
    ev = feed(det, s)
    assert "jump" in ev and "landing" in ev


def test_event_loss_of_control():
    det = EventDetector()
    s = [(i * 0.05, (i, 0, 0), (0.0, 1.0, 0), (20.0, 0.0, 0)) for i in range(20)]   # едем боком (90°)
    assert "loss_of_control" in feed(det, s)


def test_no_loss_of_control_when_straight():
    det = EventDetector()
    s = [(i * 0.05, (i, 0, 0), (1.0, 0.0, 0), (20.0, 0.0, 0)) for i in range(60)]
    assert "loss_of_control" not in feed(det, s)


# ---------------------------------------------------------------- геометрия
def test_frame_roundtrip():
    fr = Frame((3, 4, 1), 1.1)
    p = fr.world(25, -7)
    f, l = fr.local(p)
    assert f == pytest.approx(25) and l == pytest.approx(-7)


def test_ramp_geometry_low_edge_on_ground_and_rises_forward():
    fr = Frame((0, 0, 0), 0.0)
    pos, q, size = ramp_geometry(fr, 50, 0, 8, 5, 15, 0.4)
    assert size == (5, 8, 0.4)
    # центр приподнят, но не ниже нуля; высота верхней кромки ≈ L*sin(a)
    assert pos[0] > 50 and pos[2] > 0.4 * math.cos(math.radians(15)) / 2
    assert 2 * (pos[2]) == pytest.approx(8 * math.sin(math.radians(15)) + 0.4 * math.cos(math.radians(15)), abs=1e-6)
    # кватернион единичный
    assert sum(c * c for c in q) == pytest.approx(1.0)


def test_quat_mul_identity():
    q = quat_z(0.7)
    assert quat_mul((0, 0, 0, 1), q) == pytest.approx(q)
