"""BeamNG YouTube Factory — точка входа.

  python main.py                      — графический интерфейс
  python main.py --check              — проверка программ и ресурсов
  python main.py --plan "сценарий"    — показать план съёмки (без игры)
  python main.py --cli --script-file сценарий.txt [--duration 30]   — полный цикл без окна
  python main.py --edit запись.mp4 [--duration 30]                  — смонтировать готовую запись
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import deps  # noqa: E402
from core.logger import setup_logging  # noqa: E402
from core.models import JobRequest  # noqa: E402
from core.settings import Settings  # noqa: E402
from database.db import Database  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="BeamNG YouTube Factory")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--plan", metavar="TEXT")
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--script"), ap.add_argument("--script-file")
    ap.add_argument("--edit", metavar="VIDEO")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--resolution", default="1080p")
    ap.add_argument("--car", default="auto"), ap.add_argument("--map", default="auto")
    ap.add_argument("--horizontal", action="store_true")
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args(argv)
    log = setup_logging()
    settings = Settings()
    if a.check:
        checks = deps.check_all(settings, deep=True)
        print("\n".join(str(c) for c in checks))
        return 1 if deps.critical_failures(checks) else 0
    db = Database(settings.output_dir / "factory.db")
    from core.pipeline import Pipeline
    if a.plan:
        from ai_director.director import Director
        pl = Pipeline(settings, db)
        plan = pl.make_plan(JobRequest(script=a.plan, car=a.car, map=a.map, duration=a.duration))
        print(Director(catalog=pl.catalog).format_report(plan))
        return 0
    if a.edit:
        from core.models import Take
        from editor.editor import Editor
        out = settings.output_dir / "edits" / Path(a.edit).stem
        res = Editor(settings).edit([Take(1, 0, a.edit, [], ok=True)],
                                    JobRequest(script="", duration=a.duration, fps=a.fps, horizontal=a.horizontal), out, Path(a.edit).stem)
        for f in res["files"]:
            print("Готово:", f["path"])
        return 0
    if a.cli:
        text = a.script or (Path(a.script_file).read_text(encoding="utf-8") if a.script_file else "")
        if not text.strip():
            ap.error("--cli требует --script или --script-file")
        req = JobRequest(script=text, car=a.car, map=a.map, duration=a.duration, fps=a.fps, resolution=a.resolution,
                         horizontal=a.horizontal, upload=a.upload)
        pl = Pipeline(settings, db, progress=lambda p, s, m="": print(f"[{p:5.1f}%] {s}: {m}"))
        res = pl.run(req)
        for f in res["files"]:
            print("Готово:", f["path"])
        print("Заголовок:", res["metadata"]["title"])
        return 0
    from gui.main_window import run_gui
    return run_gui(settings, db)


if __name__ == "__main__":
    sys.exit(main())
