"""Встроенный разбор русскоязычного сценария по правилам (работает без ИИ-модели).

Ограничения честно: понимает типовые трюки (разгон, езда по дороге, прыжок с трамплина через
препятствие, потеря управления, таран стены/машины, торможение, поворот, погоня). Более
свободный текст лучше разбирает подключённая языковая модель (см. настройки ИИ).
"""
import math
import re

from core.models import (ActionSpec, CameraShot, ObjectSpec, Plan, Scene, VehicleSpec)
from ai_director.catalog import Catalog

RULES = [  # (тип, regex) - порядок важен только для одинаковых позиций
    ("jump", r"перепрыг|прыга|прыжок|прыгн|трамплин|взлета|взлёт|взлетает|jump|в воздух"),
    ("crash", r"врез|разби[вт]|авари|столкн|таран|влета|влетел|crash|удар[яи]"),
    ("lose_control", r"тер[яе]\w*\s+управлен|потер\w*\s+управлен|занос|дрифт|юз\b|разворач|вращ|кружи|крут[ия]т|спин|сносит|заноси"),
    ("accelerate", r"разгон|ускоря|набира\w*\s+скорость|мчи|несёт|несет|гонит|полной скорост|максимальн\w+\s+скорост"),
    ("brake", r"тормоз|останавлив"),
    ("turn", r"поворач|сворач"),
    ("chase", r"гонит\w*\s+за|гонятся|преслед|догоня|погон"),
    ("cruise", r"едет|едут|катит|движется|поехал|едем|проезжа"),
]
TARGET_PREP = r"(?:через|над|в|во|об|на)\s+"
WALL_WORDS = r"стен|столб|барьер|бетон|забор|здани|дерев|ограждени|препятств"


def _split_clauses(text: str):
    t = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"[.!?;\n]+|,\s*(?:а\s+)?(?:затем|потом|после этого|после чего|далее)?|\s+(?:затем|потом|после этого|после чего|далее)\s+|\s+и\s+(?=\w)", t)
    return [p.strip() for p in parts if p and p.strip()]


def _speed(clause: str, default=None):
    m = re.search(r"(\d{2,3})\s*(?:км|km|kph)", clause)
    if m:
        return float(m.group(1))
    if re.search(r"медленно|не спеша", clause):
        return 40.0
    return default


def dist_for_speed(kph: float, accel=6.0) -> float:
    v = kph / 3.6
    return v * v / (2 * accel) + 15


def detect_scene_blocks(script: str):
    """Сцены разделяются пустой строкой, словом «Сцена N» или меткой '---'."""
    blocks = re.split(r"(?im)\n\s*\n|^\s*-{3,}\s*$|^\s*сцена\s*\d*[:.]?\s*", script)
    blocks = [b.strip() for b in blocks if b and b.strip()]
    return blocks or [script.strip()]


def parse(script: str, catalog: Catalog, default_duration: int = 30) -> Plan:
    plan = Plan(source_script=script, provider="offline")
    blocks = detect_scene_blocks(script)
    for bi, block in enumerate(blocks):
        plan.scenes.extend(_parse_block(block, catalog, plan, len(plan.scenes) + 1))
    for i, s in enumerate(plan.scenes, 1):
        s.id = i
    first = script.strip().splitlines()[0] if script.strip() else "Ролик"
    plan.title = (first[:60] + "…") if len(first) > 60 else first
    plan.summary = f"Сцен: {len(plan.scenes)}. Разбор: встроенные правила."
    return plan


def _hero_and_obstacle(text: str, catalog: Catalog):
    cars = catalog.find_cars_all(text)
    hero = None
    obstacle = None
    low = text.lower()
    for pos, car, alias in cars:
        before = low[max(0, pos - 12):pos]
        if re.search(TARGET_PREP + r"(?:\w+\s+)?$", before):
            if obstacle is None:
                obstacle = (car, alias)
            continue
        if hero is None:
            hero = (car, alias)
    if hero is None and cars:
        hero = (cars[0][1], cars[0][2])
        if obstacle and obstacle[0]["model"] == hero[0]["model"]:
            obstacle = None
    return hero, obstacle


def _parse_block(block: str, catalog: Catalog, plan: Plan, start_id: int):
    low = block.lower()
    hero_sel, obstacle_sel = _hero_and_obstacle(block, catalog)
    color = catalog.find_color(block)
    map_sel = catalog.find_map(block)

    hero = VehicleSpec(id="hero", model=hero_sel[0]["model"] if hero_sel else "etk800",
                       color=color, role="hero", requested=hero_sel[1] if hero_sel else "")
    if hero_sel and hero_sel[1].lower() in [b.lower() for b in hero_sel[0].get("brands", [])]:
        hero.note = f"«{hero_sel[1]}» в BeamNG.drive отсутствует — подобрана ближайшая по типу: {hero_sel[0]['name']}"
        plan.alternatives.append(hero.note)
    if not hero_sel:
        plan.warnings.append("Автомобиль в тексте не найден — выбран ETK 800 (можно изменить в интерфейсе).")

    road_words = re.search(r"дорог|трасс|шоссе|серпантин|горн|трек|улиц|город", low)
    actions_road, actions_stunt = [], []
    objects: list[ObjectSpec] = []
    clauses = _split_clauses(block)
    need_obstacle_model = obstacle_sel[0]["model"] if obstacle_sel else None
    obstacle_alias = obstacle_sel[1] if obstacle_sel else ""

    for cl in clauses:
        hits = []
        for typ, rx in RULES:
            m = re.search(rx, cl)
            if m:
                hits.append((m.start(), typ))
        hits.sort()
        seen = set()
        for _, typ in hits:
            if typ in seen:
                continue
            seen.add(typ)
            kph = _speed(cl)
            if typ == "cruise" and road_words and re.search(r"дорог|трасс|шоссе|серпантин|горн|улиц", cl + " " + low[:200]):
                actions_road.append(ActionSpec("follow_road", "hero", {"kph": kph or 80, "duration": 12}))
            elif typ == "cruise":
                actions_stunt.append(ActionSpec("cruise", "hero", {"kph": kph or 60, "duration": 4}))
            elif typ == "accelerate":
                tgt = kph or 130
                (actions_road if (actions_road and not actions_stunt and not re.search(r"прыж|прыг|трамплин|врез|стен", low)) else actions_stunt) \
                    .append(ActionSpec("accelerate", "hero", {"target_kph": tgt, "max_duration": 25}))
            elif typ == "jump":
                actions_stunt.append(ActionSpec("jump", "hero", {"kph": kph} if kph else {}))
            elif typ == "lose_control":
                d = "left" if re.search(r"влево|налево|лев", cl) else "right"
                actions_stunt.append(ActionSpec("lose_control", "hero", {"duration": 2.5, "direction": d}))
            elif typ == "crash":
                actions_stunt.append(ActionSpec("crash", "hero", {"kph": kph,
                                                                   "into": "obstacle" if (obstacle_sel and re.search(TARGET_PREP + r"\w*\s*" + re.escape(obstacle_alias.lower()), cl) and not re.search(WALL_WORDS, cl)) else "wall"}))
            elif typ == "brake":
                actions_stunt.append(ActionSpec("brake", "hero", {"to_kph": 0}))
            elif typ == "turn":
                ang = -90 if re.search(r"направо|вправо|прав", cl) else 90
                actions_stunt.append(ActionSpec("turn", "hero", {"angle_deg": ang, "kph": kph or 40}))
            elif typ == "chase":
                actions_stunt.append(ActionSpec("chase", "hero", {}))

    if not actions_road and not actions_stunt:
        plan.warnings.append("В сценарии не найдено ни одного распознаваемого действия — добавлен простой проезд. "
                             "Опишите действия глаголами: «разгоняется», «перепрыгивает», «врезается»…")
        actions_road.append(ActionSpec("follow_road", "hero", {"kph": 80, "duration": 12}))

    scenes = []
    # --- дорожная сцена
    if actions_road:
        m = map_sel if (map_sel and map_sel.get("road_ai")) else catalog.map("west_coast_usa")
        scenes.append(Scene(id=start_id, description="Езда по дороге: " + block[:90], map=m["level"],
                            vehicles=[hero], objects=[], actions=actions_road,
                            expected_events=[], max_duration=sum(a.params.get("duration", 10) for a in actions_road) + 8))
    # --- трюковая сцена (объекты ставятся относительно старта → нужна ровная площадка)
    if actions_stunt:
        v2 = VehicleSpec(**hero.__dict__)
        m = map_sel if (map_sel and map_sel.get("flat")) else catalog.map("gridmap_v2")
        if map_sel and not map_sel.get("flat") and any(a.type in ("jump", "crash") for a in actions_stunt):
            plan.warnings.append(f"Трюки с рампой/стеной требуют ровной площадки; вместо «{map_sel['name']}» "
                                 f"выбрана «{m['name']}» (объекты размещаются относительно точки старта).")
            plan.alternatives.append("Чтобы снять трюк на своей карте, откалибруйте ровный участок: tools/record_spawn.py")
        objects, actions_stunt = _layout_stunt(actions_stunt, need_obstacle_model, plan)
        exp = []
        for a in actions_stunt:
            if a.type == "jump":
                exp.append("jump")
            if a.type == "crash":
                exp.append("crash")
            if a.type == "lose_control":
                exp.append("loss_of_control")
        est = 8 + sum({"accelerate": 8, "jump": 8, "lose_control": 4, "crash": 10, "cruise": 5, "brake": 4, "turn": 4, "chase": 12}.get(a.type, 4) for a in actions_stunt)
        vehicles = [v2]
        obstacle_vehicles = [o for o in objects if o.type == "obstacle_vehicle"]
        scenes.append(Scene(id=start_id + len(scenes), description="Трюк: " + block[:90], map=m["level"],
                            vehicles=vehicles, objects=objects, actions=actions_stunt,
                            expected_events=exp, max_duration=min(60, est)))
    return scenes


def _layout_stunt(actions, obstacle_model, plan: Plan):
    """Раскладывает рампы/стены/препятствия по оси «вперёд» от точки старта."""
    objs: list[ObjectSpec] = []
    cursor = 0.0
    speed = 60.0
    out = []
    # если прыжок или таран идёт без разгона — добавим разгон
    need_run = actions and actions[0].type in ("jump", "crash")
    if need_run:
        tgt = actions[0].params.get("kph", 100)
        out.append(ActionSpec("accelerate", "hero", {"target_kph": tgt, "max_duration": 25}))
        speed = tgt
        cursor += dist_for_speed(tgt)
    n_ramp = n_wall = 0
    for a in actions:
        p = a.params
        if a.type == "accelerate":
            speed = p.get("target_kph", 120)
            cursor += dist_for_speed(speed)
            out.append(a)
        elif a.type == "cruise":
            cursor += speed / 3.6 * p.get("duration", 4)
            out.append(a)
        elif a.type == "jump":
            kph = p.get("kph") or max(speed, 100)
            ramp_len, angle = 8.0, 15.0
            ramp_fwd = max(cursor, dist_for_speed(kph)) + 10
            n_ramp += 1
            rid = f"ramp{n_ramp}"
            objs.append(ObjectSpec("ramp", rid, ramp_fwd, 0.0, {"length": ramp_len, "width": 5.0, "angle_deg": angle}))
            ramp_end = ramp_fwd + ramp_len * math.cos(math.radians(angle))
            if obstacle_model:
                gap = 3.0
                objs.append(ObjectSpec("obstacle_vehicle", f"obstacle{len([o for o in objs if o.type=='obstacle_vehicle'])+1}",
                                       ramp_end + gap + 5.5, 0.0, {"model": obstacle_model, "yaw_deg": 90}))
                cursor = ramp_end + gap + 12 + 30
            else:
                cursor = ramp_end + 40
            a2 = ActionSpec("jump", "hero", {"kph": kph, "ramp": rid, "landing_distance": cursor})
            out.append(a2)
        elif a.type == "lose_control":
            cursor += speed / 3.6 * p.get("duration", 2.5) + 5
            out.append(a)
        elif a.type == "crash":
            n_wall += 1
            target = p.get("into", "wall")
            wall_fwd = cursor + 60
            if target == "obstacle" and obstacle_model and not any(o.type == "obstacle_vehicle" for o in objs):
                objs.append(ObjectSpec("obstacle_vehicle", "obstacle1", wall_fwd, 0.0, {"model": obstacle_model, "yaw_deg": 90}))
                tid = "obstacle1"
            else:
                objs.append(ObjectSpec("wall", f"wall{n_wall}", wall_fwd, 0.0, {"width": 60.0, "height": 3.0, "thickness": 1.5}))
                tid = f"wall{n_wall}"
            cursor = wall_fwd
            out.append(ActionSpec("crash", "hero", {"kph": p.get("kph") or max(speed, 100), "target": tid}))
        else:
            out.append(a)
    return objs, out
