"""Doctor/session tests against a fake BeamNG (no game needed)."""

from __future__ import annotations

from pathlib import Path

from bfactory import doctor
from bfactory.capture.ffmpeg_recorder import build_command
from bfactory.core import config
from bfactory.system.windows import Rect


class FakeSensor(dict):
    @property
    def data(self):
        return self


class FakeSensors:
    def __init__(self, veh: "FakeVehicle"):
        self.veh = veh
        self._s = {"state": FakeSensor(), "damage": FakeSensor(damage=0.0)}

    def poll(self, *names):
        v = self.veh
        v.t += 1
        if v.mode == "span":
            v.x += 2.0
        elif v.throttle and v.t > v.crash_at:
            self._s["damage"]["damage"] = 5000.0
        self._s["state"].update(pos=(v.x, 0.0, 100.0), dir=(1.0, 0.0, 0.0),
                                rotation=(0, 0, 0, 1), up=(0, 0, 1))

    def __getitem__(self, k):
        return self._s[k]


class FakeAI:
    def __init__(self, v):
        self.v = v

    def set_mode(self, m):
        self.v.mode = m

    def drive_in_lane(self, flag):
        pass

    def set_speed(self, s, mode="limit"):
        assert mode == "limit"


class FakeVehicle:
    def __init__(self):
        self.t, self.x, self.mode, self.throttle, self.crash_at = 0, 0.0, "disabled", 0.0, 10
        self.sensors = FakeSensors(self)
        self.ai = FakeAI(self)

    @property
    def state(self):
        return self.sensors["state"]

    def control(self, steering=None, throttle=None, brake=None, **_):
        if throttle is not None:
            self.throttle = throttle


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def f(*a, **k):
            self.calls.append((name, a))
        return f


class FakeBNG:
    def __init__(self):
        self.camera, self.control, self.env = Recorder(), Recorder(), Recorder()
        self.vehicles = Recorder()


def test_session_tests_with_fake_game(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "OUT_DIR", tmp_path)
    monkeypatch.setattr(doctor.time, "sleep", lambda s: None)
    clock = iter(range(0, 10_000_000, 1))
    monkeypatch.setattr(doctor.time, "time", lambda: next(clock) * 0.05)
    d = doctor.Doctor()
    bng, hero = FakeBNG(), FakeVehicle()
    d.session_tests(bng, hero)
    res = {c.name: c for c in d.checks}
    assert res["AI вождение"].ok
    assert res["Столкновение + датчик повреждений"].ok
    assert res["Замедление времени (Lua)"].ok
    assert res["Время суток"].ok
    assert not res["Запись: старт"].ok  # no window on CI
    assert any(c[0] == "spawn" for c in bng.vehicles.calls)
    assert len(bng.camera.calls) > 10


def test_ffmpeg_command_gdigrab_and_ddagrab():
    r = Rect(10, 20, 1920, 1080)
    g = build_command("ffmpeg", r, Path("o.mp4"), fps=60, encoder="h264_nvenc")
    assert ["-offset_x", "10"] == g[g.index("-offset_x"):g.index("-offset_x") + 2]
    assert "desktop" in g and "h264_nvenc" in g
    d = build_command("ffmpeg", r, Path("o.mp4"), fps=60, encoder="libx264", grabber="ddagrab")
    assert any(a.startswith("ddagrab=") and "video_size=1920x1080" in a for a in d)


def test_settings_roundtrip(tmp_path):
    s = config.Settings()
    s.game.home = r"C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
    s.capture.encoder = "h264_amf"
    p = tmp_path / "s.toml"
    config.save(s, p)
    assert config.load(p) == s
