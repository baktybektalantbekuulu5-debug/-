"""PC check ("doctor"): detects everything automatically and tests the game.

Run:  python -m bfactory.doctor
Writes projects/_doctor/report.txt (+ report.json, test video) and
config/settings.toml with the detected values.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .core import config, logsetup, paths
from .system import ffmpeg_tools, game_locator, sysinfo, windows

log = logsetup.setup("doctor")
OUT_DIR = paths.PROJECTS_DIR / "_doctor"


@dataclass
class Check:
    name: str
    ok: bool
    details: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class Doctor:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.settings = config.load()
        self.ffmpeg: str | None = None
        self.encoders: list[str] = []
        self.home: Path | None = None

    # ------------------------------------------------------------------ utils
    def record(self, name: str, ok: bool, details: str = "", **data: Any) -> Check:
        c = Check(name, ok, details, data)
        self.checks.append(c)
        (log.info if ok else log.warning)("%s %s: %s", "OK " if ok else "ERR", name, details)
        return c

    def step(self, name: str, fn: Callable[[], None]) -> bool:
        try:
            fn()
            return True
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            log.debug(traceback.format_exc())
            self.record(name, False, f"{type(e).__name__}: {e}")
            return False

    # ----------------------------------------------------------------- checks
    def check_system(self) -> None:
        info = sysinfo.collect()
        gpu = ", ".join(g.get("Name", "?") for g in info["gpus"]) or "не определена"
        self.record("Компьютер", True,
                    f"{info['os']}; CPU {info['cpu_threads']} потоков; RAM {info['ram_gb']} ГБ; "
                    f"видеокарта: {gpu}", **info)

    def check_game(self) -> None:
        res = game_locator.locate()
        best = res.best
        if self.settings.game.home and Path(self.settings.game.home).is_dir():
            self.home = Path(self.settings.game.home)
        elif best:
            self.home = best.home
        versions = ", ".join(res.user_versions) or "нет данных"
        if self.home:
            self.record("Игра BeamNG.drive", True,
                        f"найдена: {self.home} (источник: {best.source if best else 'настройки'}; "
                        f"версии в папке пользователя: {versions}; Steam build: "
                        f"{best.steam_build_id if best else '-'})",
                        installs=[str(i.home) for i in res.installs],
                        user_folders=[str(u) for u in res.user_folders], versions=res.user_versions)
            self.settings.game.home = str(self.home)
        else:
            self.record("Игра BeamNG.drive", False,
                        "не найдена. Запустите игру один раз вручную и повторите проверку — "
                        "программа найдёт её по запущенному процессу.")

    def check_ffmpeg(self) -> None:
        self.ffmpeg = ffmpeg_tools.find_ffmpeg()
        if not self.ffmpeg:
            self.record("FFmpeg (запись видео)", False, "не найден и не скачался")
            return
        self.encoders = ffmpeg_tools.working_encoders(self.ffmpeg)
        dda = ffmpeg_tools.supports_ddagrab(self.ffmpeg)
        self.settings.capture.ffmpeg = self.ffmpeg
        self.settings.capture.encoder = self.encoders[0]
        self.record("FFmpeg (запись видео)", True,
                    f"{self.ffmpeg}; рабочие кодеки: {', '.join(self.encoders)}; "
                    f"захват DXGI (ddagrab): {'да' if dda else 'нет'}",
                    encoders=self.encoders, ddagrab=dda)

    # ---------------------------------------------------------- game session
    def check_beamng(self) -> None:
        if not self.home:
            self.record("Запуск игры через API", False, "пропущено: игра не найдена")
            return
        from beamngpy import BeamNGpy, Scenario, Vehicle
        from beamngpy.sensors import Damage, GForces

        g = self.settings.game
        bng = BeamNGpy(g.host, g.port, home=str(self.home), user=g.user_folder or None)
        log.info("Запускаю BeamNG.drive через BeamNGpy (первый запуск может идти несколько минут)...")
        t0 = time.time()
        bng.open(launch=True)
        try:
            tech = bool(bng.tech_enabled())
            g.tech_enabled = tech
            self.record("Запуск игры через API", True,
                        f"подключено за {time.time() - t0:.0f} c; BeamNG.tech функции: "
                        f"{'есть' if tech else 'нет (обычная BeamNG.drive — это нормально)'}")

            levels: dict[str, Any] = {}
            vehicles: dict[str, Any] = {}

            def catalog() -> None:
                nonlocal levels, vehicles
                levels = bng.scenario.get_levels()
                vehicles = bng.vehicles.get_available()
                (OUT_DIR / "catalog.json").write_text(json.dumps(
                    {"levels": sorted(levels), "vehicles": {
                        k: {"name": (v.get("model") or {}).get("Name") if isinstance(v, dict) else None,
                            "type": (v.get("model") or {}).get("Type") if isinstance(v, dict) else None,
                            "configs": sorted((v.get("configurations") or {}).keys())
                            if isinstance(v, dict) else []}
                        for k, v in vehicles.items()}},
                    ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                self.record("Каталог игры", True,
                            f"карт: {len(levels)}, моделей машин: {len(vehicles)} "
                            f"(список сохранён в catalog.json)",
                            levels=sorted(levels), vehicle_count=len(vehicles))

            self.step("Каталог игры", catalog)

            level = g.default_level if (not levels or g.default_level in levels) else sorted(levels)[0]
            if level != "west_coast_usa":
                self.record("Тестовая сцена", False, f"нет карты west_coast_usa (есть: {level})")
                return
            hero = Vehicle("hero", model="etk800", license="FACTORY", color="Red")
            hero.sensors.attach("damage", Damage())
            hero.sensors.attach("g", GForces())
            scenario = Scenario(level, "factory_doctor", description="PC check")
            scenario.add_vehicle(hero, pos=(-717.121, 101, 118.675),
                                 rot_quat=(0, 0, 0.3826834, 0.9238795))

            def build_scene() -> None:
                scenario.make(bng)
                bng.scenario.load(scenario)
                bng.scenario.start()
                self.step("Скрыть интерфейс", bng.ui.hide_hud)
                self.record("Тестовая сцена", True, f"карта {level}, красный etk800 создан")

            if not self.step("Тестовая сцена", build_scene):
                return
            self.session_tests(bng, hero)
        finally:
            config.save(self.settings)
            try:
                bng.close()
            except Exception:  # noqa: BLE001
                pass

    def session_tests(self, bng: Any, hero: Any) -> None:
        from beamngpy import Vehicle
        from beamngpy.sensors import Damage

        recorder = None
        video = OUT_DIR / "test_capture.mp4"
        windows.make_dpi_aware()

        def start_recording() -> None:
            nonlocal recorder
            from .capture.ffmpeg_recorder import FFmpegRecorder
            win = windows.find_window("BeamNG")
            if not win or not self.ffmpeg:
                raise RuntimeError("окно игры или FFmpeg не найдены")
            windows.bring_to_front(win[0])
            time.sleep(1)
            rect = windows.client_rect(win[0])
            grabber = self.pick_grabber(rect)
            recorder = FFmpegRecorder(self.ffmpeg, fps=60, encoder=self.encoders[0], grabber=grabber)
            recorder.start(rect, video)
            self.settings.capture.grabber = grabber
            self.record("Запись: старт", True, f"окно «{win[1]}» {rect.w}x{rect.h}, захват {grabber}")

        self.step("Запись: старт", start_recording)

        # 1. AI driving.
        def ai_drive() -> None:
            hero.sensors.poll()
            p0 = hero.state["pos"]
            hero.ai.set_mode("span")
            hero.ai.drive_in_lane(True)
            hero.ai.set_speed(60 / 3.6, mode="limit")
            follow_camera(bng, hero, seconds=8)
            hero.sensors.poll()
            dist = math.dist(p0, hero.state["pos"])
            self.record("AI вождение", dist > 20, f"машина проехала сама {dist:.0f} м")

        self.step("AI вождение", ai_drive)

        # 2. Scripted crash into a parked truck + damage detection.
        def crash() -> None:
            hero.sensors.poll()
            pos, d, rot = hero.state["pos"], hero.state["dir"], hero.state["rotation"]
            n = math.hypot(d[0], d[1]) or 1.0
            fx, fy = d[0] / n, d[1] / n
            obstacle = Vehicle("obstacle", model="pickup", color="White")
            obstacle.sensors.attach("damage", Damage())
            bng.vehicles.spawn(obstacle, (pos[0] + fx * 35, pos[1] + fy * 35, pos[2] + 0.5), rot)
            hero.sensors.poll()
            dmg0 = hero.sensors["damage"].data.get("damage", 0)
            hero.ai.set_mode("disabled")
            hero.control(throttle=1.0, steering=0.0, brake=0.0)
            cam = (pos[0] + fx * 30 - fy * 12, pos[1] + fy * 30 + fx * 12, pos[2] + 3)
            t_end = time.time() + 7
            while time.time() < t_end:
                hero.sensors.poll()
                hp = hero.state["pos"]
                look = (hp[0] - cam[0], hp[1] - cam[1], hp[2] - cam[2])
                bng.camera.set_free(cam, look)
                time.sleep(0.05)
            hero.control(throttle=0.0, brake=1.0)
            hero.sensors.poll()
            dmg = hero.sensors["damage"].data.get("damage", 0) - dmg0
            self.record("Столкновение + датчик повреждений", dmg > 100,
                        f"урон после удара: {dmg:.0f} (датчик Damage работает)")

        self.step("Столкновение + датчик повреждений", crash)

        # 3. Slow motion via game Lua.
        def slowmo() -> None:
            bng.control.queue_lua_command(
                "if simTimeAuthority and simTimeAuthority.set then simTimeAuthority.set(0.25) "
                "elseif bullettime then bullettime.set(0.25) end")
            follow_camera(bng, hero, seconds=3, orbit=True)
            bng.control.queue_lua_command(
                "if simTimeAuthority and simTimeAuthority.set then simTimeAuthority.set(1) "
                "elseif bullettime then bullettime.set(1) end")
            self.record("Замедление времени (Lua)", True,
                        "команда выполнена; визуально проверить в test_capture.mp4 (последние секунды)")

        self.step("Замедление времени (Lua)", slowmo)

        def env() -> None:
            bng.env.set_tod(0.85)
            time.sleep(1)
            bng.env.set_tod(0.5)
            self.record("Время суток", True, "смена времени суток работает")

        self.step("Время суток", env)

        def stop_recording() -> None:
            if not recorder:
                return
            out = recorder.stop()
            dur = ffmpeg_tools.probe_duration(self.ffmpeg, out) if out else None
            bright = ffmpeg_tools.frame_brightness(self.ffmpeg, out, (dur or 2) / 2) if out else None
            ok = bool(dur and dur > 5 and bright is not None and bright > 8)
            self.record("Запись: результат", ok,
                        f"{out.name if out else '-'}: {dur or 0:.1f} c, яркость кадра {bright or 0:.0f}/255"
                        + ("" if ok else " — видео пустое/чёрное"))

        self.step("Запись: результат", stop_recording)

    def pick_grabber(self, rect: Any) -> str:
        """Try DXGI capture first (best for games); fall back to GDI if frames are black."""
        from .capture.ffmpeg_recorder import FFmpegRecorder
        if not ffmpeg_tools.supports_ddagrab(self.ffmpeg):
            return "gdigrab"
        probe = OUT_DIR / "probe_ddagrab.mp4"
        try:
            r = FFmpegRecorder(self.ffmpeg, fps=30, encoder="libx264", grabber="ddagrab")
            r.start(rect, probe)
            time.sleep(3)
            r.stop()
            b = ffmpeg_tools.frame_brightness(self.ffmpeg, probe, 1.5)
            return "ddagrab" if b is not None and b > 8 else "gdigrab"
        except Exception:  # noqa: BLE001
            return "gdigrab"

    # ---------------------------------------------------------------- report
    def write_report(self) -> Path:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "report.json").write_text(
            json.dumps([asdict(c) for c in self.checks], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        ok = sum(c.ok for c in self.checks)
        lines = ["BEAMNG YOUTUBE FACTORY — отчёт проверки ПК",
                 f"Дата: {datetime.now():%Y-%m-%d %H:%M}", f"Успешно: {ok} из {len(self.checks)}", ""]
        lines += [f"[{'OK ' if c.ok else 'ERR'}] {c.name}: {c.details}" for c in self.checks]
        lines += ["", "Скопируйте весь этот текст и отправьте его в чат с Claude."]
        txt = OUT_DIR / "report.txt"
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def run(self) -> Path:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        paths.ensure_dirs()
        for name, fn in (("Компьютер", self.check_system), ("Игра BeamNG.drive", self.check_game),
                         ("FFmpeg (запись видео)", self.check_ffmpeg),
                         ("Запуск игры через API", self.check_beamng)):
            self.step(name, fn)
        config.save(self.settings)
        return self.write_report()


def follow_camera(bng: Any, vehicle: Any, seconds: float, orbit: bool = False) -> None:
    """Simple chase / orbit camera driven from Python via camera.set_free."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        vehicle.sensors.poll("state")
        p, d = vehicle.state["pos"], vehicle.state["dir"]
        if orbit:
            a = (time.time() - t0) * 0.8
            cam = (p[0] + 9 * math.cos(a), p[1] + 9 * math.sin(a), p[2] + 3)
        else:
            cam = (p[0] - d[0] * 9, p[1] - d[1] * 9, p[2] + 3.2)
        bng.camera.set_free(cam, (p[0] - cam[0], p[1] - cam[1], p[2] + 0.8 - cam[2]))
        time.sleep(0.05)


def main() -> int:
    report = Doctor().run()
    print("\n" + report.read_text(encoding="utf-8"))
    if sys.platform == "win32":
        os.startfile(report)  # noqa: S606 - open the report in Notepad
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
