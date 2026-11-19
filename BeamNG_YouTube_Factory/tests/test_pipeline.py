"""Сквозной тест оркестратора: реальные FFmpeg/OpenCV/SQLite/монтаж; подменены только игра и OBS."""
import subprocess
from pathlib import Path

import pytest

from ai_director.catalog import Catalog
from ai_driver.runtime_base import SceneRuntime
from conftest import needs_ffmpeg
from core.geometry import Frame
from core.models import JobRequest
from core.pipeline import Pipeline, PipelineError
from core.stop import CancelToken, StopRequested
from database.db import Database
from environment.manager import resolve_start
from fakes import FakeRuntime
from recorder.obs_recorder import RecorderError

SCRIPT = ("Красный Lamborghini едет по горной дороге, разгоняется, перепрыгивает через автобус, "
          "теряет управление и врезается в стену.")


class FakeSession:
    bng = None

    def __init__(self, catalog, drop_wall_first=False):
        self.catalog, self.drop_wall_first = catalog, drop_wall_first
        self.loads = 0
        self.rt = None
        self.opened = self.closed = False

    def open(self): self.opened = True
    def close(self): self.closed = True

    def load_scene(self, scene, name):
        self.loads += 1
        pos, yaw, _ = resolve_start(self.catalog, scene)
        fr = Frame(pos, yaw)
        rt = FakeRuntime(fr, steer_hidden_sign=-1)
        for o in scene.objects:
            if o.type == "ramp":
                rt.objects[o.id] = (fr.world(o.forward + 4, o.lateral), "ramp")
                rt.ramp_at = o.forward
            elif o.type == "wall":
                if self.drop_wall_first and self.loads == 2:      # 1-й дубль трюковой сцены: сбой посреди съёмки (стена не создалась)
                    pass
                else:
                    rt.objects[o.id] = (fr.world(o.forward, o.lateral), "wall")
            elif o.type == "obstacle_vehicle":
                rt.objects[o.id] = (fr.world(o.forward, o.lateral), "obstacle")
        self.rt = rt
        return rt


class FakeRecorder:
    name = "fake"

    def __init__(self, session, ffmpeg="ffmpeg"):
        self.session, self.t0 = session, 0.0

    def start(self, out_dir, name):
        self.out = Path(out_dir) / f"{name}.mp4"
        self.t0 = self.session.rt.t

    def stop(self):
        dur = max(1.0, self.session.rt.t - self.t0)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=15:duration={dur:.2f}",
                        "-f", "lavfi", "-i", f"sine=f=200:d={dur:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.out)], check=True)
        return self.out

    def abort(self): pass


def make_pipeline(settings, tmp_path, **kw):
    cat = Catalog()
    sess = FakeSession(cat, kw.pop("drop_wall_first", False))
    db = Database(tmp_path / "f.db")
    cancel = kw.pop("cancel", None)
    prog = []
    pl = Pipeline(settings, db, cancel=cancel, progress=lambda p, s, m="": prog.append((p, s)), catalog=cat,
                  session_factory=lambda: sess, recorder_factory=lambda res, fps: FakeRecorder(sess))
    return pl, sess, db, prog


def req(**kw):
    base = dict(script=SCRIPT, duration=15, fps=30, resolution="720p")
    base.update(kw)
    return JobRequest(**base)


@needs_ffmpeg
def test_full_pipeline_produces_mp4_with_metadata(settings, tmp_path):
    pl, sess, db, prog = make_pipeline(settings, tmp_path)
    res = pl.run(req())
    f = Path(res["files"][0]["path"])
    assert f.exists() and f.suffix == ".mp4" and f.stat().st_size > 10_000
    from recorder.recorder import probe
    info = probe(f)
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"] and info["duration"] <= 15.6
    assert res["metadata"]["title"] and "#shorts" in res["metadata"]["hashtags"]
    assert sess.opened and sess.closed
    # 2 сцены → 2 дубля, оба с видео; сырьё сохранено
    takes = db.list_takes(pl.pid)
    assert len(takes) == 2 and all(Path(t["video"]).exists() for t in takes)
    stunt = next(t for t in takes if t["scene_id"] == 2)
    types = {e["type"] for e in stunt["events"]}
    assert {"jump", "crash"} <= types and stunt["ok"]
    assert db.get_project(pl.pid)["status"] == "done"
    assert db.list_videos(pl.pid)
    assert prog[-1][0] == 100 and [p for p, _ in prog] == sorted(p for p, _ in prog)
    assert settings.get("beamng.steer_sign") in (1, -1)         # калибровка руля сохранилась


@needs_ffmpeg
def test_failed_scene_is_retried_automatically(settings, tmp_path):
    pl, sess, db, _ = make_pipeline(settings, tmp_path, drop_wall_first=True)
    pl.run(req())
    takes = db.list_takes(pl.pid)
    stunt = [t for t in takes if t["scene_id"] == 2]
    assert len(stunt) == 2 and not stunt[0]["ok"] and stunt[1]["ok"]
    assert "wall1" in stunt[0]["error"]                       # причина сбоя записана
    assert Path(stunt[0]["video"]).exists()                    # запись неудачного дубля не потеряна


@needs_ffmpeg
def test_resume_skips_finished_scenes_and_retry_scene_adds_take(settings, tmp_path):
    pl, sess, db, _ = make_pipeline(settings, tmp_path)
    pl.run(req())
    loads = sess.loads
    pl2, sess2, _, _ = make_pipeline(settings, tmp_path)
    pl2.db = db
    pl2.run(None, project_id=pl.pid, resume=True)
    assert sess2.loads == 0                                  # всё уже снято
    pl2.retry_scene(pl.pid, 2)
    assert sess2.loads == 1
    assert len([t for t in db.list_takes(pl.pid) if t["scene_id"] == 2]) == 2


@needs_ffmpeg
def test_stop_button_preserves_progress(settings, tmp_path):
    tok = CancelToken()
    pl, sess, db, _ = make_pipeline(settings, tmp_path, cancel=tok)
    orig = FakeRuntime.sleep
    n = {"i": 0}

    def sleepy(self, dt):
        n["i"] += 1
        if n["i"] == 600:       # посреди съёмки
            tok.cancel()
        orig(self, dt)
    FakeRuntime.sleep = sleepy
    try:
        with pytest.raises(StopRequested):
            pl.run(req())
    finally:
        FakeRuntime.sleep = orig
    assert db.get_project(pl.pid)["status"] == "stopped"
    takes = db.list_takes(pl.pid)
    assert takes and all(Path(t["video"]).exists() for t in takes if t["video"])   # записанное не потеряно


def test_recorder_unavailable_gives_clear_error(settings, tmp_path):
    cat = Catalog()
    sess = FakeSession(cat)
    db = Database(tmp_path / "f.db")

    def bad(res, fps):
        raise RecorderError("OBS не запущен")
    pl = Pipeline(settings, db, catalog=cat, session_factory=lambda: sess, recorder_factory=bad)
    with pytest.raises(PipelineError, match="Запись невозможна"):
        pl.run(req())
    assert db.get_project(pl.pid)["status"] == "failed"


def test_preflight_reports_missing_ffmpeg(settings, tmp_path):
    settings.set("paths.ffmpeg", "ffmpeg_does_not_exist")
    pl, *_ = make_pipeline(settings, tmp_path)
    with pytest.raises(PipelineError, match="FFmpeg"):
        pl.preflight(deep=False)
