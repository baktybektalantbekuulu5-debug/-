"""AI Editor: дубли → анализ → план фрагментов → рендер Shorts 9:16 / 16:9 → MP4."""
import json
import re
from pathlib import Path

from core.logger import get_logger
from core.models import JobRequest, Take
from editor import analysis, audio, planner, render

log = get_logger("editor")


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.U).strip("_")
    return (s[:40] or "video")


class Editor:
    def __init__(self, settings, cancel=None, progress=None):
        self.s = settings
        self.ffmpeg = settings.get("paths.ffmpeg", "ffmpeg")
        self.ffprobe = settings.get("paths.ffprobe", "ffprobe")
        self.cancel = cancel
        self.progress = progress or (lambda frac, msg="": None)

    def select_main(self, takes: list[Take]):
        """Для каждой сцены — лучший дубль (успешный, с большим числом ожидаемых событий)."""
        by_scene: dict[int, list[Take]] = {}
        for t in takes:
            if t.video and Path(t.video).exists():
                by_scene.setdefault(t.scene_id, []).append(t)
        mains = {}
        for sid, lst in sorted(by_scene.items()):
            lst.sort(key=lambda t: (t.ok, len({e.type for e in t.events} & {"crash", "jump", "loss_of_control"}), -t.index), reverse=True)
            mains[sid] = lst[0]
        return mains, by_scene

    def build_plan(self, takes, target, profiles=None, infos=None):  # noqa: C901
        mains, by_scene = self.select_main(takes)
        if not mains:
            raise RuntimeError("Нет записанных видеофайлов для монтажа")
        segs = []
        slow = self.s.get("editor.slowmo_factor", 0.4)
        for sid, main in mains.items():
            info = infos[main.video] if infos else analysis.video_info(main.video)
            prof = profiles[main.video] if profiles else []
            act = analysis.active_range(prof, info.duration)
            segs += planner.plan_scene(main, act, info.duration, prof, slow, budget=target / max(1, len(mains)))
            segs += planner.plan_replays(by_scene[sid], main, slow)
        return planner.fit(segs, target)

    def edit(self, takes: list[Take], req: JobRequest, out_dir: Path, title: str = "video") -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        work = out_dir / "_work"
        work.mkdir(exist_ok=True)
        mains, _ = self.select_main(takes)
        if not mains:
            raise RuntimeError("Нет записанных видеофайлов для монтажа")
        # 1. анализ
        infos, profiles = {}, {}
        for i, (sid, tk) in enumerate(mains.items()):
            self.progress(i / max(1, len(mains)) * 0.15, f"Анализ видео сцены {sid}")
            infos[tk.video] = analysis.video_info(tk.video)
            profiles[tk.video] = analysis.motion_profile(tk.video, self.s.get("editor.motion_sample_fps", 4), self.cancel)
        for tk in takes:  # профили для повторов
            if tk.video and tk.video not in profiles and Path(tk.video).exists():
                infos[tk.video] = analysis.video_info(tk.video)
                profiles[tk.video] = analysis.motion_profile(tk.video, 4, self.cancel)
        results = {"files": [], "notes": []}
        formats = []
        if req.vertical:
            formats.append("vertical")
        if req.horizontal:
            formats.append("horizontal")
        if not formats:
            formats = ["vertical"]
        base = safe_name(title)
        for fi, mode in enumerate(formats):
            target = float(req.duration)
            if mode == "vertical" and target > 60:
                results["notes"].append("YouTube Shorts ограничены 60 секундами — вертикальное видео сокращено до 59 с.")
                target = 59.0
            segs = self.build_plan(takes, target, profiles, infos)
            total = sum(s.out_len for s in segs)
            log.info("план монтажа (%s): %d фрагментов, %.1f с", mode, len(segs), total)
            fps = int(round(min(req.fps, max(infos[s.src].fps for s in segs))))
            ev = planner.map_events(segs, takes)
            impact_t = [t for t, typ, _ in ev if typ == "crash"]
            sfx = []
            cache = Path(self.s.output_dir) / "_cache"
            if req.sfx:
                for t, typ, _ in ev:
                    name = audio.EVENT_SFX.get(typ)
                    if name:
                        sfx.append((t, audio.sfx_file(name, self.ffmpeg, cache)))
            music = audio.music_file(self.ffmpeg, cache, total) if req.music else None
            suffix = "shorts_9x16" if mode == "vertical" else "16x9"
            out = out_dir / f"{base}_{suffix}.mp4"
            vtmp, atmp = work / f"{suffix}_v.mp4", work / f"{suffix}_a.wav"
            lo, hi = 0.15 + 0.8 * fi / len(formats), 0.15 + 0.8 * (fi + 1) / len(formats)
            self.progress(lo, f"Рендер {suffix}")
            render.render_video(segs, vtmp, self.ffmpeg, mode, req.crop_mode, fps, profiles, impact_t,
                                self.s.get("editor.crf", 18), self.s.get("editor.preset", "medium"), self.cancel,
                                lambda f: self.progress(lo + (hi - lo) * 0.85 * f, f"Рендер {suffix}"))
            self.progress(hi - 0.03, "Сведение звука")
            render.build_audio(segs, self.ffmpeg, self.ffprobe, atmp, music, sfx,
                               self.s.get("editor.game_volume", 1.0), self.s.get("editor.music_volume", 0.35),
                               self.s.get("editor.sfx_volume", 0.9))
            render.mux(vtmp, atmp, out, self.ffmpeg)
            results["files"].append({"path": str(out), "mode": mode, "duration": total, "fps": fps,
                                     "segments": [{"src": s.src, "start": round(s.start, 2), "end": round(s.end, 2),
                                                   "speed": s.speed, "label": s.label, "scene": s.scene_id} for s in segs]})
            (out_dir / f"{base}_{suffix}.edl.json").write_text(json.dumps(results["files"][-1], ensure_ascii=False, indent=1), encoding="utf-8")
        self.progress(1.0, "Монтаж завершён")
        return results
