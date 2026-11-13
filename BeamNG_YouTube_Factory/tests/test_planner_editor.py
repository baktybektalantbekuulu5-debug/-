import subprocess
from pathlib import Path

import pytest

from conftest import needs_ffmpeg
from core.models import Event, JobRequest, Take
from editor import analysis, planner
from editor.planner import Segment
from editor.render import atempo_chain


def mk_take(events, video="a.mp4", sid=1, idx=0):
    return Take(sid, idx, video, [Event(t, ty) for t, ty in events], ok=True)


def test_plan_scene_windows_and_slowmo():
    tk = mk_take([(8, "jump"), (14, "crash")])
    segs = planner.plan_scene(tk, (0.0, 20.0), 20.0, [], 0.4)
    assert any(s.label == "слоу-мо" and s.speed == 0.4 for s in segs)
    assert all(s.start >= 0 and s.end <= 20 for s in segs)
    crash_slow = [s for s in segs if s.label == "слоу-мо" and s.start <= 14 <= s.end]
    assert crash_slow


@pytest.mark.parametrize("target", [5, 10, 20, 40])
def test_fit_respects_target(target):
    tk = mk_take([(20, "jump"), (35, "loss_of_control"), (50, "crash")])
    segs = planner.plan_scene(tk, (0, 60), 60, [], 0.4)
    segs += planner.plan_replays([mk_take([(12, "crash")], "b.mp4", 1, 1), tk], tk)
    out = planner.fit(segs, target)
    assert sum(s.out_len for s in out) <= target + 0.1
    assert out and all(s.end > s.start for s in out)


def test_fit_keeps_crash_core():
    tk = mk_take([(10, "crash")])
    out = planner.fit(planner.plan_scene(tk, (0, 30), 30, []) + planner.plan_replays([mk_take([(5, "crash")], "b.mp4", 1, 1)], tk), 6)
    assert any(s.start <= 10 <= s.end for s in out)


def test_map_events_to_output_timeline():
    tk = mk_take([(10, "crash")], "a.mp4")
    segs = [Segment("a.mp4", 5, 9, 1.0), Segment("a.mp4", 9, 12, 0.5)]     # 4 с + 6 с
    ev = planner.map_events(segs, [tk])
    assert ev[0][1] == "crash" and ev[0][0] == pytest.approx(4 + (10 - 9) / 0.5)


def test_best_window_prefers_active_part():
    class M:
        def __init__(self, t, e): self.t, self.energy = t, e
    prof = [M(t * 0.25, 0.9 if 20 <= t * 0.25 < 25 else 0.01) for t in range(160)]
    a, b = planner.best_window(prof, 0, 40, 5)
    assert 19 <= a <= 21


def test_atempo_chain_ranges():
    assert atempo_chain(1.0) == ""
    assert atempo_chain(0.4) == "atempo=0.5,atempo=0.8000"
    assert atempo_chain(3.0) == "atempo=2.0,atempo=1.5000"


def test_crop_track_static_camera_follows_motion_chase_camera_centers():
    S = analysis.MotionSample
    static = [S(t * 0.25, 0.02, 0.2 + t * 0.02, False) for t in range(20)]
    tr = analysis.crop_track(static, 0, 5)
    assert tr[-1][1] < 0.5 and tr[0][1] != 0.5 or tr[-1][1] != 0.5
    chase = [S(t * 0.25, 0.6, 0.9, True) for t in range(20)]
    assert all(abs(c - 0.5) < 1e-9 for _, c in analysis.crop_track(chase, 0, 5))


@needs_ffmpeg
def test_end_to_end_edit_creates_valid_shorts(tmp_path, settings):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=14",
                    "-f", "lavfi", "-i", "sine=f=300:d=14", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True)
    tk = Take(1, 0, str(src), [Event(5, "jump", data={"airtime": 1.2}), Event(9, "crash")], ok=True)
    from editor.editor import Editor
    req = JobRequest(script="", duration=8, fps=30, horizontal=True)
    res = Editor(settings).edit([tk], req, tmp_path / "final", "Тест видео")
    assert len(res["files"]) == 2
    from recorder.recorder import probe
    v = probe(res["files"][0]["path"])
    assert (v["width"], v["height"]) == (1080, 1920) and v["has_audio"]
    assert v["duration"] <= 8.6 and v["duration"] > 3
    h = probe(res["files"][1]["path"])
    assert (h["width"], h["height"]) == (1920, 1080)


@needs_ffmpeg
def test_shorts_capped_at_60s(tmp_path, settings):
    src = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=90",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    from editor.editor import Editor
    res = Editor(settings).edit([Take(1, 0, str(src), [], ok=True)], JobRequest(script="", duration=100, fps=10, music=False, sfx=False),
                                tmp_path / "f", "long")
    assert res["files"][0]["duration"] <= 59.1 and res["notes"]
