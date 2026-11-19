"""AI YouTube Manager: заголовки, описания, хештеги, идеи для следующих роликов."""
import json
import random
import re

from core.logger import get_logger
from core.models import Plan

log = get_logger("meta")

SYSTEM = """Ты — YouTube-продюсер игрового канала про BeamNG.drive. Ответь ТОЛЬКО JSON:
{"title": "до 70 символов, цепляющий, без кликбейта-лжи", "description": "3-6 строк + призыв подписаться",
 "hashtags": ["#BeamNG", ...до 10], "tags": ["слова для поля tags"], "ideas": ["5 идей следующих роликов"]}
Язык: {lang}. Не обещай того, чего нет в ролике."""

OFFLINE_IDEAS = [
    "Тот же трюк, но на грузовике / внедорожнике — сравнить поведение при прыжке",
    "Прыжок через два автобуса: хватит ли разгона?",
    "Погоня полиции за {car} по горной дороге",
    "Краш-тест: лобовое столкновение на 60, 120 и 200 км/ч",
    "Челлендж: проехать трассу без единой царапины",
    "Дрифт по серпантину на заднеприводной машине",
]


def offline_metadata(plan: Plan, duration=0.0, lang="ru") -> dict:
    hero = None
    for s in plan.scenes:
        for v in s.vehicles:
            if v.role == "hero":
                hero = v
                break
        if hero:
            break
    car = (hero.requested or hero.model) if hero else "машина"
    acts = {a.type for s in plan.scenes for a in s.actions}
    bits = []
    if "jump" in acts:
        bits.append("безумный прыжок")
    if "lose_control" in acts:
        bits.append("потеря управления")
    if "crash" in acts:
        bits.append("жёсткий краш")
    if not bits:
        bits.append("скоростная поездка")
    title = f"{car.title()}: {', '.join(bits)} | BeamNG.drive"
    title = title[:95]
    desc = (f"{plan.title}\n\nСцена снята в BeamNG.drive. Что происходит: {', '.join(bits)}.\n"
            f"Ставьте лайк и подписывайтесь — впереди ещё больше трюков!\n\n"
            "Ролик создан автоматически в BeamNG YouTube Factory.")
    tags = ["BeamNG", "BeamNG.drive", "crash", "краш", "трюки", "симулятор", "car crash", "jump"]
    return {"title": title, "description": desc, "hashtags": ["#BeamNG", "#BeamNGdrive", "#crash", "#shorts", "#cars"],
            "tags": tags, "ideas": [i.format(car=car) for i in OFFLINE_IDEAS[:5]], "provider": "offline"}


def generate(plan: Plan, provider, lang="ru", shorts=True) -> dict:
    meta = None
    if provider is not None and getattr(provider, "name", "offline") != "offline":
        try:
            user = f"Сценарий: {plan.source_script}\nПлан: {plan.summary}\nФормат: {'Shorts 9:16' if shorts else '16:9'}"
            meta = provider.complete_json(SYSTEM.replace("{lang}", lang), user, 1500)
            meta["provider"] = provider.name
        except Exception as e:  # noqa: BLE001
            log.warning("ИИ не сгенерировал метаданные (%s) — шаблон", e)
    if not meta:
        meta = offline_metadata(plan, lang=lang)
    meta["title"] = str(meta.get("title", ""))[:100] or offline_metadata(plan)["title"]
    tags = list(dict.fromkeys(["#shorts"] + list(meta.get("hashtags", [])))) if shorts else list(meta.get("hashtags", []))
    meta["hashtags"] = tags[:15]
    if shorts and "#shorts" not in meta["description"].lower():
        meta["description"] = meta["description"].rstrip() + "\n\n" + " ".join(meta["hashtags"][:5])
    return meta
