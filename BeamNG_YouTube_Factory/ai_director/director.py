"""AI Director: сценарий -> проверенный технический план (Plan)."""
import json

from core.logger import get_logger
from core.models import ACTION_TYPES, OBJECT_TYPES, ActionSpec, JobRequest, ObjectSpec, Plan, Scene, VehicleSpec
from ai_director import offline_parser
from ai_director.catalog import Catalog
from ai_director.providers import AIError, AIProvider, OfflineProvider

log = get_logger("director")

SYSTEM_PROMPT = """Ты — режиссёр-постановщик для игры BeamNG.drive. Преврати сценарий в JSON-план съёмки.
Отвечай ТОЛЬКО одним JSON-объектом без пояснений.

Схема:
{"title":str,"summary":str,"warnings":[str],"alternatives":[str],
 "scenes":[{"id":int,"description":str,"map":<level из каталога>,
   "vehicles":[{"id":"hero","model":<model из каталога>,"color":str,"role":"hero|rival|obstacle","requested":str,"note":str}],
   "objects":[{"type":"ramp|wall|obstacle_vehicle|cones","id":str,"forward":метры вперёд от старта,"lateral":метры влево,
     "params":{ramp:{length,width,angle_deg}; wall:{width,height,thickness}; obstacle_vehicle:{model,yaw_deg}}}],
   "actions":[{"type":"cruise|accelerate|brake|turn|follow_road|jump|lose_control|crash|wait|chase","vehicle":"hero","params":{...}}],
   "expected_events":["jump","crash","loss_of_control"],"max_duration":сек}]}

Параметры действий: accelerate{target_kph,max_duration}; cruise{kph,duration}; brake{to_kph}; turn{angle_deg,kph};
follow_road{kph,duration} (ИИ-водитель игры едет по дороге; только карты road_ai=true);
jump{kph,ramp:<id рампы>}; lose_control{duration,direction:left|right}; crash{kph,target:<id стены/машины>}; chase{}.
Правила:
- Используй ТОЛЬКО модели и карты из каталога. Если запрошенной машины нет (например Lamborghini) — выбери ближайшую по типу и запиши это в alternatives и vehicles[].note.
- Рампы и стены размещаются относительно точки старта на плоской поверхности: для таких сцен выбирай карту с flat=true.
  Езду по горной дороге (follow_road) делай отдельной сценой на карте с road_ai=true.
- Не выдумывай возможности. Если что-то нельзя сделать — объясни в warnings и предложи альтернативу.
- forward для рампы должен быть >= v^2/12+25 метров (v в м/с), чтобы машина успела разогнаться.
"""


class Director:
    def __init__(self, provider: AIProvider | None = None, catalog: Catalog | None = None):
        self.provider = provider or OfflineProvider()
        self.catalog = catalog or Catalog()

    # ---------------------------------------------------------------- план
    def make_plan(self, req: JobRequest, installed_cars=None, installed_levels=None) -> Plan:
        plan = None
        if not isinstance(self.provider, OfflineProvider):
            try:
                plan = self._llm_plan(req)
                plan.provider = self.provider.name
            except (AIError, Exception) as e:  # noqa: BLE001 - любой сбой сети/парсинга -> резерв
                log.warning("ИИ-провайдер недоступен (%s) — используется встроенный разбор", e)
                plan = None
        if plan is None:
            plan = offline_parser.parse(req.script, self.catalog, req.duration)
            if not isinstance(self.provider, OfflineProvider):
                plan.warnings.append("ИИ-модель не ответила, использован встроенный разбор по правилам.")
        self.apply_overrides(plan, req)
        self.validate(plan, installed_cars, installed_levels)
        return plan

    def _llm_plan(self, req: JobRequest) -> Plan:
        cat = {"cars": [{"model": c["model"], "name": c["name"], "tags": c["tags"]} for c in self.catalog.cars],
               "maps": [{"level": m["level"], "name": m["name"], "tags": m["tags"], "flat": m["flat"], "road_ai": m["road_ai"],
                         "has_spawn": bool(m.get("spawn"))} for m in self.catalog.maps]}
        user = f"КАТАЛОГ:\n{json.dumps(cat, ensure_ascii=False)}\n\nЦЕЛЕВАЯ ДЛИТЕЛЬНОСТЬ РОЛИКА: {req.duration} с\n\nСЦЕНАРИЙ:\n{req.script}"
        data = self.provider.complete_json(SYSTEM_PROMPT, user)
        data["source_script"] = req.script
        return Plan.from_dict(data)

    # ----------------------------------------------------------- переопределения
    def apply_overrides(self, plan: Plan, req: JobRequest):
        for s in plan.scenes:
            if req.map not in ("auto", "", None):
                m = self.catalog.map(req.map)
                if m:
                    if m["level"] != s.map and any(o.type in ("ramp", "wall") for o in s.objects) and not m.get("flat"):
                        plan.warnings.append(f"Выбрана карта «{m['name']}», а сцена {s.id} содержит рампы/стены. "
                                             f"Размещение объектов на неровной местности может быть неточным.")
                    if not any(a.type == "follow_road" for a in s.actions) or m.get("road_ai"):
                        s.map = m["level"]
            if req.car not in ("auto", "", None):
                car = self.catalog.car(req.car)
                if car:
                    for v in s.vehicles:
                        if v.role == "hero":
                            v.model = car["model"]
                            v.note = ""

    # ----------------------------------------------------------- проверка
    def validate(self, plan: Plan, installed_cars=None, installed_levels=None) -> Plan:
        """Приводит план к допустимому виду и проверяет ресурсы. Не бросает исключений на «плохие» значения."""
        if not plan.scenes:
            plan.warnings.append("План пуст.")
        for s in plan.scenes:
            m = self.catalog.map(s.map)
            if m is None:
                alt = self.catalog.map("gridmap_v2")
                plan.warnings.append(f"Сцена {s.id}: неизвестная карта «{s.map}», заменена на {alt['name']}.")
                s.map = alt["level"]
                m = alt
            if installed_levels is not None and s.map not in installed_levels:
                alt = next((x for x in self.catalog.maps_with_spawn() if x["level"] in installed_levels
                            and bool(x.get("flat")) == bool(m.get("flat"))), None) \
                    or next((x for x in self.catalog.maps_with_spawn() if x["level"] in installed_levels), None)
                if alt:
                    plan.warnings.append(f"Сцена {s.id}: карта «{s.map}» не установлена, предложена «{alt['name']}».")
                    plan.alternatives.append(f"Сцена {s.id}: карта {s.map} → {alt['level']}")
                    s.map, m = alt["level"], alt
                else:
                    plan.warnings.append(f"Сцена {s.id}: карта «{s.map}» не найдена в установленной игре.")
            if not m.get("spawn") and not s.start_override:
                alt = next((x for x in self.catalog.maps_with_spawn()
                            if x.get("flat") == m.get("flat") and (installed_levels is None or x["level"] in installed_levels)), None)
                plan.warnings.append(f"Сцена {s.id}: для карты «{m['name']}» нет точки старта (запишите её: tools/record_spawn.py)."
                                     + (f" Использована «{alt['name']}»." if alt else ""))
                if alt:
                    s.map = alt["level"]
                    m = alt
            if not s.vehicles:
                s.vehicles = [VehicleSpec()]
            ids = set()
            for v in s.vehicles:
                car = self.catalog.car(v.model)
                if car is None:
                    fb = self.catalog.cars[0]
                    plan.warnings.append(f"Сцена {s.id}: модель «{v.model}» неизвестна, заменена на {fb['name']}.")
                    v.model = fb["model"]
                elif installed_cars is not None and v.model not in installed_cars:
                    alt = next((c for c in self.catalog.cars if c["model"] in installed_cars and set(c["tags"]) & set(car["tags"])), None) \
                        or next((c for c in self.catalog.cars if c["model"] in installed_cars), None)
                    if alt:
                        plan.warnings.append(f"Сцена {s.id}: машина «{car['name']}» не установлена → {alt['name']}.")
                        v.model = alt["model"]
                ids.add(v.id)
            hero_id = next((v.id for v in s.vehicles if v.role == "hero"), s.vehicles[0].id)
            clean_actions = []
            for a in s.actions:
                if a.type not in ACTION_TYPES:
                    plan.warnings.append(f"Сцена {s.id}: неизвестное действие «{a.type}» пропущено.")
                    continue
                if a.vehicle not in ids:
                    a.vehicle = hero_id
                if a.type == "follow_road" and not m.get("road_ai"):
                    plan.warnings.append(f"Сцена {s.id}: на карте «{m['name']}» нет подтверждённой сети дорог для ИИ-водителя; "
                                         f"действие заменено на езду по прямой.")
                    a = ActionSpec("cruise", a.vehicle, {"kph": a.params.get("kph", 60), "duration": a.params.get("duration", 8)})
                clean_actions.append(a)
            s.actions = clean_actions
            clean_objs = []
            for o in s.objects:
                if o.type not in OBJECT_TYPES:
                    plan.warnings.append(f"Сцена {s.id}: неизвестный объект «{o.type}» пропущен.")
                    continue
                if o.type == "obstacle_vehicle" and self.catalog.car(o.params.get("model", "")) is None:
                    o.params["model"] = "citybus"
                if not o.id:
                    o.id = f"{o.type}{len(clean_objs)+1}"
                clean_objs.append(o)
            s.objects = clean_objs
            s.max_duration = max(10.0, min(120.0, float(s.max_duration)))
            have_ramp = {o.id for o in s.objects}
            for a in s.actions:
                if a.type in ("jump",) and a.params.get("ramp") not in have_ramp:
                    plan.warnings.append(f"Сцена {s.id}: у прыжка нет рампы — рампа добавлена автоматически.")
                    rid = "ramp_auto"
                    s.objects.append(ObjectSpec("ramp", rid, 90.0, 0.0, {"length": 8.0, "width": 5.0, "angle_deg": 15.0}))
                    a.params["ramp"] = rid
                if a.type == "crash" and a.params.get("target") not in have_ramp | {o.id for o in s.objects}:
                    plan.warnings.append(f"Сцена {s.id}: у тарана нет цели — стена добавлена автоматически.")
                    s.objects.append(ObjectSpec("wall", "wall_auto", 120.0, 0.0, {"width": 60.0, "height": 3.0, "thickness": 1.5}))
                    a.params["target"] = "wall_auto"
        return plan

    def format_report(self, plan: Plan) -> str:
        lines = [f"План: {plan.title}  (разбор: {plan.provider})"]
        for s in plan.scenes:
            cars = ", ".join(f"{v.model}{' ('+v.color+')' if v.color else ''}" for v in s.vehicles)
            lines.append(f" Сцена {s.id}: карта={s.map}; машины=[{cars}]; "
                         f"объекты={[o.type for o in s.objects]}; действия={[a.type for a in s.actions]}")
        for w in plan.warnings:
            lines.append(" ⚠ " + w)
        for a in plan.alternatives:
            lines.append(" ➜ " + a)
        return "\n".join(lines)
