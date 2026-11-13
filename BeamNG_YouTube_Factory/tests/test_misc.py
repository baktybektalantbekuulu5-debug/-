import json
from pathlib import Path

import pytest

from ai_director.catalog import Catalog
from cameraman.cameraman import Cameraman, plan_shots
from core.models import Event, Plan, Scene, Take, VehicleSpec
from core.settings import Settings
from database.db import Database
from environment.manager import GameContent, resolve_start
from fakes import FakeRuntime
from core.geometry import Frame
from recorder.obs_recorder import OBSRecorder, RecorderError
from recorder.ffmpeg_recorder import FFmpegRecorder
from recorder.recorder import check_quality
from youtube import metadata, uploader


def test_settings_merge_and_secret(tmp_path, monkeypatch):
    s = Settings(user_path=tmp_path / "u.json")
    assert s.get("obs.port") == 4455
    s.set("obs.port", 4466); s.save()
    s2 = Settings(user_path=tmp_path / "u.json")
    assert s2.get("obs.port") == 4466 and s2.get("obs.host") == "localhost"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert s2.secret("ai.anthropic.api_key", "ANTHROPIC_API_KEY") == "k"


def test_database_roundtrip(tmp_path):
    db = Database(tmp_path / "x.db")
    db.create_project("p1", "t", "script", {"a": 1}, tmp_path)
    t = Take(1, 0, "v.mp4", [Event(1.5, "crash", data={"k": 1})], ok=True)
    db.save_take("p1", t); db.save_take("p1", t)             # перезапись, не дубль
    assert len(db.list_takes("p1")) == 1
    assert Take.from_dict(db.list_takes("p1")[0]).events[0].type == "crash"
    vid = db.add_video("p1", "o.mp4", "vertical", 10.0)
    db.set_youtube_id(vid, "abc")
    assert db.list_videos("p1")[0]["youtube_id"] == "abc"
    db.update_project("p1", status="done", plan={"x": 1})
    assert db.get_project("p1")["status"] == "done"
    db.log("p1", "INFO", "msg"); assert db.get_log("p1")[0]["message"] == "msg"


def test_plan_serialization_roundtrip():
    from ai_director.director import Director
    from core.models import JobRequest
    p = Director().make_plan(JobRequest(script="Синий пикап разгоняется и прыгает с трамплина"))
    p2 = Plan.from_dict(json.loads(json.dumps(p.to_dict())))
    assert p2.to_dict() == p.to_dict()


def test_game_content_scan(tmp_path):
    (tmp_path / "content" / "vehicles" / "etk800").mkdir(parents=True)
    (tmp_path / "content" / "vehicles" / "pickup.zip").write_text("x")
    (tmp_path / "content" / "levels" / "gridmap_v2").mkdir(parents=True)
    g = GameContent(str(tmp_path))
    assert g.cars == {"etk800", "pickup"} and g.levels == {"gridmap_v2"} and g.known
    assert GameContent("").cars is None


def test_resolve_start_missing_spawn_has_instruction():
    sc = Scene(map="italy")
    with pytest.raises(RuntimeError, match="record_spawn"):
        resolve_start(Catalog(), sc)
    assert resolve_start(Catalog(), Scene(map="gridmap_v2"))[2].startswith("не проверено")


def test_user_spawn_overrides(tmp_path):
    cat = Catalog()
    cat._user_maps_path = tmp_path / "user_maps.json"
    cat.save_user_spawn("italy", {"pos": [1, 2, 3], "dir": [0, -1], "verified": True})
    pos, yaw, src = resolve_start(cat, Scene(map="italy"))
    assert pos == (1, 2, 3) and src == "проверено"


def test_camera_shots_and_event_cut():
    sc = Scene(max_duration=40)
    shots = plan_shots(sc, "cinematic")
    assert shots[0].start == 0 and [s.start for s in shots] == sorted(s.start for s in shots)
    assert plan_shots(sc, "cinematic", 1) != shots          # другой набор ракурсов для повторного дубля
    fr = Frame((0, 0, 0), 0.0)
    rt = FakeRuntime(fr)
    cam = Cameraman(rt)
    cam.set_shots(shots)
    st = rt.state("hero")
    cam.on_tick(0.0, st)
    assert cam.cur_mode == "chase"
    cam.on_event(Event(1.0, "crash"), st)
    cam.on_tick(1.1, st)
    assert cam.cur_mode == "tripod" and hasattr(rt, "last_free")


def test_camera_unsupported_falls_back_without_crash():
    class NoCam(FakeRuntime):
        def camera_free(self, pos, direction):
            from ai_driver.runtime_base import CameraUnsupported
            raise CameraUnsupported("нет")

        def camera_player(self, vid, cands, config=None):
            from ai_driver.runtime_base import CameraUnsupported
            raise CameraUnsupported("нет")
    rt = NoCam(Frame((0, 0, 0), 0.0))
    cam = Cameraman(rt)
    cam.set_shots(plan_shots(Scene(max_duration=20), "cinematic"))
    for t in range(0, 20):
        cam.on_tick(float(t), rt.state("hero"))
    assert cam.free_ok is False and cam.player_ok is False


def test_quality_check_messages():
    w = check_quality({"width": 1280, "height": 720, "fps": 30.0, "has_audio": False}, "1080p", 60)
    assert len(w) == 3


def test_obs_recorder_with_mock_client(tmp_path):
    class R:  # имитация ответов obs-websocket
        def __init__(self, **k): self.active = False; self.out = tmp_path / "obs_rec.mkv"
        def get_version(self): return type("V", (), {"obs_version": "30", "obs_web_socket_version": "5.4"})()
        def get_record_status(self): return type("S", (), {"output_active": self.active})()
        def start_record(self): self.active = True
        def stop_record(self):
            self.active = False
            self.out.write_bytes(b"x" * 1000)
            return type("O", (), {"output_path": str(self.out)})()
        def get_video_settings(self): return type("V", (), dict(base_width=1920, base_height=1080, output_width=1920, output_height=1080, fps_numerator=60, fps_denominator=1))()
        def get_stats(self): return type("S", (), dict(render_skipped_frames=0, output_skipped_frames=0, cpu_usage=5.0))()
    rec = OBSRecorder()
    rec.cl = R()
    rec.start(tmp_path / "raw", "scene01")
    out = rec.stop()
    assert out.exists() and out.parent.name == "raw" and (tmp_path / "obs_rec.mkv").exists()   # копия, оригинал цел


def test_obs_unreachable_message():
    rec = OBSRecorder(port=1, timeout=1)
    with pytest.raises(RecorderError, match="OBS"):
        rec.connect()


def test_ffmpeg_recorder_command():
    cmd = FFmpegRecorder(title="BeamNG.drive", audio_device="Stereo Mix", fps=60).build_cmd(Path("o.mp4"))
    assert "gdigrab" in cmd and "title=BeamNG.drive" in cmd and "audio=Stereo Mix" in cmd and "60" in cmd


def test_youtube_metadata_offline_and_body():
    from ai_director.director import Director
    from core.models import JobRequest
    plan = Director().make_plan(JobRequest(script="Красный Lamborghini разгоняется, прыгает с трамплина и врезается в стену"))
    m = metadata.generate(plan, None)
    assert len(m["title"]) <= 100 and "#shorts" in m["hashtags"] and m["ideas"]
    b = uploader.build_body(m, "private")
    assert b["status"]["privacyStatus"] == "private" and b["snippet"]["title"] == m["title"]


def test_youtube_upload_requires_client_secret(tmp_path, settings):
    settings.set("youtube.client_secret", str(tmp_path / "nope.json"))
    settings.set("youtube.token", str(tmp_path / "tok.json"))
    with pytest.raises(uploader.YouTubeError, match="client_secret|Нет файла|Не установлены"):
        uploader.upload(tmp_path / "v.mp4", {"title": "t", "description": "d"}, settings)
