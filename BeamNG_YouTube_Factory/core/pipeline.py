"""Оркестратор: сценарий → план → съёмка сцен → монтаж → метаданные (→ загрузка).

Каждый этап сохраняет результат (project.json + SQLite). При сбое можно продолжить (resume)
или переснять отдельную сцену (retry_scene). Сырые записи никогда не удаляются.
"""
import json
import re
import time
import traceback
from pathlib import Path

from core.logger import get_logger
from core.models import JobRequest, Plan, Take
from core.stop import CancelToken, StopRequested
from core import deps
from ai_director.catalog import Catalog
from ai_director.director import Director
from ai_director.providers import make_provider
from ai_driver.driver import Driver
from cameraman.cameraman import Cameraman, plan_shots
from editor.editor import Editor
from environment.manager import GameContent
from recorder import recorder as rec_mod
from recorder.obs_recorder import RecorderError
from youtube import metadata as ytmeta

log = get_logger("pipeline")

HARD_EVENTS = {"jump", "crash"}
REQUIRED_MANUAL = {"jump", "crash", "lose_control", "accelerate", "brake", "turn", "cruise"}


class PipelineError(Exception):
    pass


def slug(s: str) -> str:
    s = re.sub(r"[^\w]+", "_", s, flags=re.U).strip("_")
    return s[:30] or "project"


class Pipeline:
    def __init__(self, settings, db, cancel: CancelToken | None = None, progress=None,
                 session_factory=None, recorder_factory=None, catalog=None, provider=None):
        self.s, self.db = settings, db
        self.cancel = cancel or CancelToken()
        self._progress = progress or (lambda pct, stage, msg="": None)
        self.catalog = catalog or Catalog()
        self.provider = provider
        self.session_factory = session_factory or self._default_session
        self.recorder_factory = recorder_factory or (lambda res, fps: rec_mod.make_recorder(self.s, res, fps))
        self.session = None
        self.pid = None

    # -------------------------------------------------------------- утилиты
    def _default_session(self):
        from environment.beamng_session import BeamNGSession
        return BeamNGSession(self.s, self.catalog)

    def progress(self, pct, stage, msg=""):
        self._progress(max(0, min(100, pct)), stage, msg)

    def _log(self, level, msg):
        getattr(log, level)(msg)
        if self.pid:
            try:
                self.db.log(self.pid, level.upper(), msg)
            except Exception:  # noqa: BLE001
                pass

    def _provider(self):
        if self.provider is None:
            self.provider = make_provider(self.s)
        return self.provider

    def _folder(self, pid):
        return self.s.output_dir / "projects" / pid

    def _save_state(self, folder: Path, req: JobRequest, plan: Plan | None, takes: list[Take], extra=None):
        data = {"request": req.to_dict(), "plan": plan.to_dict() if plan else None,
                "takes": [t.to_dict() for t in takes], **(extra or {})}
        tmp = folder / "project.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(folder / "project.json")

    # ------------------------------------------------------------ планирование
    def make_plan(self, req: JobRequest) -> Plan:
        content = GameContent(self.s.get("paths.beamng_home"))
        director = Director(self._provider(), self.catalog)
        return director.make_plan(req, content.cars, content.levels)

    def preflight(self, deep=True):
        checks = deps.check_all(self.s, need_game=True, need_recorder=True, deep=deep)
        for c in checks:
            self._log("info" if c.ok else "warning", str(c))
        bad = deps.critical_failures(checks)
        if bad:
            raise PipelineError("Не выполнены обязательные условия:\n" + "\n".join(str(c) for c in bad))
        return checks

    # --------------------------------------------------------------- основной запуск
    def run(self, req: JobRequest, project_id: str | None = None, resume: bool = False) -> dict:
        self.cancel.reset()
        plan, takes = None, []
        if resume and project_id:
            plan, takes, req = self._load(project_id)
            self.pid = project_id
            folder = self._folder(project_id)
        else:
            pid = project_id or f"{time.strftime('%Y%m%d_%H%M%S')}_{slug(req.script.split(chr(10))[0])}"
            self.pid, folder = pid, self._folder(pid)
            folder.mkdir(parents=True, exist_ok=True)
            self.db.create_project(pid, req.script[:60], req.script, req.to_dict(), folder)
        try:
            self.db.update_project(self.pid, status="running", error="")
            # 1. План
            if plan is None:
                self.progress(2, "AI Director", "Анализ сценария…")
                plan = self.make_plan(req)
                self._save_state(folder, req, plan, takes)
                self.db.update_project(self.pid, title=plan.title, plan=plan.to_dict(), status="planned")
                for w in plan.warnings:
                    self._log("warning", w)
                for a in plan.alternatives:
                    self._log("info", "Альтернатива: " + a)
            self.cancel.check()
            # 2. Проверка среды
            self.progress(6, "Проверка", "Проверка программ и ресурсов…")
            self.preflight(deep=True)
            # 3. Съёмка
            takes = self._shoot_all(plan, req, folder, takes)
            self.cancel.check()
            # 4. Монтаж
            result = self._edit_and_publish(plan, req, folder, takes)
            self.db.update_project(self.pid, status="done")
            self.progress(100, "Готово", "Видео создано")
            return result
        except StopRequested:
            self._log("warning", "Процесс остановлен пользователем. Записанные материалы сохранены.")
            self.db.update_project(self.pid, status="stopped")
            raise
        except Exception as e:  # noqa: BLE001
            self._log("error", f"Ошибка: {e}\n{traceback.format_exc()}")
            self.db.update_project(self.pid, status="failed", error=str(e)[:500])
            raise
        finally:
            self._close_session()

    def _load(self, pid):
        row = self.db.get_project(pid)
        if not row:
            raise PipelineError(f"Проект {pid} не найден")
        data = json.loads((Path(row["folder"]) / "project.json").read_text(encoding="utf-8"))
        req = JobRequest(**{k: v for k, v in data["request"].items() if k in JobRequest.__dataclass_fields__})
        plan = Plan.from_dict(data["plan"]) if data.get("plan") else None
        takes = [Take.from_dict(t) for t in data.get("takes", [])]
        return plan, takes, req

    def retry_scene(self, project_id: str, scene_id: int) -> dict:
        """Переснять сцену заново (новый дубль) и пересобрать видео."""
        self.cancel.reset()
        plan, takes, req = self._load(project_id)
        self.pid = project_id
        folder = self._folder(project_id)
        scene = next((s for s in plan.scenes if s.id == scene_id), None)
        if scene is None:
            raise PipelineError(f"В проекте нет сцены {scene_id}")
        try:
            self.db.update_project(project_id, status="running", error="")
            self.preflight(deep=True)
            takes = self._shoot_scene(plan, req, scene, folder, takes, force=True, base_progress=10, span=60)
            result = self._edit_and_publish(plan, req, folder, takes)
            self.db.update_project(project_id, status="done")
            return result
        except StopRequested:
            self.db.update_project(project_id, status="stopped")
            raise
        except Exception as e:  # noqa: BLE001
            self._log("error", f"Ошибка повтора сцены: {e}")
            self.db.update_project(project_id, status="failed", error=str(e)[:500])
            raise
        finally:
            self._close_session()

    def edit_only(self, project_id: str) -> dict:
        """Пересобрать видео из уже записанных дублей (без игры)."""
        self.cancel.reset()
        plan, takes, req = self._load(project_id)
        self.pid = project_id
        try:
            return self._edit_and_publish(plan, req, self._folder(project_id), takes)
        finally:
            self._close_session()

    # ----------------------------------------------------------------- съёмка
    def _shoot_all(self, plan, req, folder, takes):
        n = len(plan.scenes)
        for i, scene in enumerate(plan.scenes):
            base = 10 + 60 * i / max(1, n)
            takes = self._shoot_scene(plan, req, scene, folder, takes, base_progress=base, span=60 / max(1, n))
        return takes

    def _shoot_scene(self, plan, req, scene, folder, takes, force=False, base_progress=10, span=50):
        want_good = max(1, req.takes_per_scene)
        max_attempts = max(want_good, int(self.s.get("production.max_scene_attempts", 3)))
        mine = [t for t in takes if t.scene_id == scene.id]
        good = [t for t in mine if t.ok]
        if good and not force and len(good) >= want_good:
            self._log("info", f"Сцена {scene.id}: уже снята ({len(good)} успешных дублей), пропускаю")
            return takes
        attempts = 0
        idx = max([t.index for t in mine], default=-1) + 1
        need = want_good - (len(good) if not force else 0)
        got = 0
        while got < need and attempts < max_attempts:
            self.cancel.check()
            attempts += 1
            self.progress(base_progress + span * (attempts - 1) / max_attempts, f"Сцена {scene.id}",
                          f"Съёмка сцены {scene.id}, дубль {idx + 1}")
            take = self._record_take(plan, req, scene, folder, idx)
            takes.append(take)
            self.db.save_take(self.pid, take)
            self._save_state(folder, req, plan, takes)
            idx += 1
            if take.ok:
                got += 1
            else:
                self._log("warning", f"Сцена {scene.id}, дубль {take.index + 1}: цель не достигнута "
                                     f"({take.error or 'ожидаемые события не зафиксированы'}); попытка {attempts}/{max_attempts}")
        if got == 0 and not any(t.ok for t in takes if t.scene_id == scene.id):
            best = [t for t in takes if t.scene_id == scene.id and t.video]
            if best:
                self._log("warning", f"Сцена {scene.id}: идеального дубля нет — для монтажа будет использован лучший из {len(best)}.")
            else:
                raise PipelineError(f"Сцена {scene.id}: не удалось записать ни одного дубля")
        return takes

    def _open_session(self):
        if self.session is None:
            self.session = self.session_factory()
            self.session.open()
        return self.session

    def _close_session(self):
        if self.session is not None:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass
            self.session = None

    def _record_take(self, plan, req, scene, folder, index) -> Take:
        raw = folder / "raw"
        raw.mkdir(exist_ok=True)
        name = f"scene{scene.id:02d}_take{index + 1}"
        take = Take(scene_id=scene.id, index=index, camera_preset=req.camera_style if index == 0 else f"alt{index}")
        session = self._open_session()
        recorder = None
        recording = False
        try:
            rt = session.load_scene(scene, f"factory_{self.pid[-12:]}_{scene.id}_{index}")
            cam = Cameraman(rt)
            cam.set_shots(plan_shots(scene, req.camera_style, index))
            driver = Driver(rt, self.cancel, int(self.s.get("beamng.steer_sign", 0)),
                            on_event=cam.on_event, on_tick=cam.on_tick)
            if driver.need_calibration and any(a.type in REQUIRED_MANUAL for a in scene.actions):
                self._log("info", "Калибровка направления руля…")
                sign = driver.calibrate_steer()
                self.s.set("beamng.steer_sign", sign)
                self.s.save()
                rt.reset_to_start("hero")
                rt.sleep(1.0)
            recorder = self.recorder_factory(req.resolution, req.fps)
            recorder.start(raw, name)
            recording = True
            latency = float(self.s.get("obs.start_latency", 0.3)) if recorder.name == "obs" else 0.5
            origin = rt.now() + latency
            pre = float(self.s.get("beamng.scene_pre_roll", 2.0))
            end_pre = rt.now() + pre
            while rt.now() < end_pre:
                st = rt.state("hero")
                cam.on_tick(rt.now() - origin, st)
                rt.sleep(0.05)
            events = driver.run_scene(scene, origin_t=origin)
            post = float(self.s.get("beamng.scene_post_roll", 3.0))
            end_post = rt.now() + post
            while rt.now() < end_post:
                self.cancel.check()
                st = rt.state("hero")
                cam.on_tick(rt.now() - origin, st)
                rt.sleep(0.05)
            take.events = events
            video = recorder.stop()
            recording = False
            take.video = str(video)
            info = rec_mod.probe(video, self.s.get("paths.ffprobe", "ffprobe"))
            take.duration = info["duration"]
            for w in rec_mod.check_quality(info, req.resolution, req.fps):
                self._log("warning", f"Сцена {scene.id}: {w}")
            got = {e.type for e in events}
            # обязательны только надёжно детектируемые трюки; занос — желательное событие (порог пробуксовки зависит от машины)
            expected = set(scene.expected_events) & HARD_EVENTS
            if set(scene.expected_events) - got - HARD_EVENTS:
                self._log("info", f"Сцена {scene.id}: событие(я) {sorted(set(scene.expected_events) - got - HARD_EVENTS)} не зафиксировано (не критично)")
            take.ok = expected <= got and take.duration >= float(self.s.get("production.min_scene_seconds", 6))
            if not take.ok:
                take.error = "не зафиксировано: " + ", ".join(sorted(expected - got)) if expected - got else "слишком короткая запись"
        except StopRequested:
            take.error = "остановлено"
            raise
        except RecorderError as e:
            if not recording and not take.video:   # рекордер недоступен — повторы бессмысленны
                raise PipelineError(f"Запись невозможна: {e}")
            take.error = str(e)[:300]
            self._log("error", f"Сцена {scene.id}: {e}")
        except Exception as e:  # noqa: BLE001
            take.error = str(e)[:300]
            self._log("error", f"Сцена {scene.id}, дубль {index + 1}: {e}")
        finally:
            if recording and recorder:
                # не теряем запись при сбое/остановке
                try:
                    video = recorder.stop()
                    take.video = take.video or str(video)
                    self._log("info", f"Запись сохранена после сбоя: {video}")
                except Exception as e2:  # noqa: BLE001
                    self._log("warning", f"Не удалось корректно остановить запись: {e2}")
                    try:
                        recorder.abort()
                    except Exception:  # noqa: BLE001
                        pass
            if take.video or take.error:
                self.db.save_take(self.pid, take)
            try:
                if self.session and getattr(self.session, "bng", None):
                    self.session.bng.scenario.stop()
            except Exception:  # noqa: BLE001
                pass
        return take

    # ------------------------------------------------------- монтаж и публикация
    def _edit_and_publish(self, plan, req, folder, takes):
        usable = [t for t in takes if t.video and Path(t.video).exists()]
        if not usable:
            raise PipelineError("Нет записанных видео для монтажа")
        final = folder / "final"
        self.progress(72, "AI Editor", "Монтаж…")
        editor = Editor(self.s, self.cancel, lambda f, m="": self.progress(72 + 23 * f, "AI Editor", m))
        res = editor.edit(usable, req, final, plan.title)
        for n in res["notes"]:
            self._log("warning", n)
        self.progress(96, "YouTube Manager", "Заголовок, описание, хештеги…")
        meta = ytmeta.generate(plan, self._provider(), self.s.get("youtube.language", "ru"), shorts=req.vertical)
        (final / "youtube_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        res["metadata"] = meta
        for f in res["files"]:
            vid = self.db.add_video(self.pid, f["path"], f["mode"], f["duration"], {"title": meta["title"]})
            f["db_id"] = vid
        if req.upload:
            try:
                from youtube import uploader
                main = next((f for f in res["files"] if f["mode"] == "vertical"), res["files"][0])
                yt = uploader.upload(Path(main["path"]), meta, self.s,
                                     lambda p: self.progress(96 + 3 * p, "YouTube", f"Загрузка {p:.0%}"))
                self.db.set_youtube_id(main["db_id"], yt)
                res["youtube_id"] = yt
            except Exception as e:  # noqa: BLE001
                self._log("error", f"Загрузка на YouTube не удалась: {e}")
                res["upload_error"] = str(e)
        self._save_state(folder, req, plan, takes, {"result": {k: v for k, v in res.items() if k != "metadata"}, "metadata": meta})
        return res
