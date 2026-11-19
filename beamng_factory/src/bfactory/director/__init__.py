"""Director: turns a free-text video scenario into a structured :class:`ScriptPlan`."""

from __future__ import annotations

import logging

from .rule_parser import parse_rules
from .schema import (
    Action,
    ActionType,
    Actor,
    ActorColor,
    ActorKind,
    ActorRole,
    CameraHint,
    Environment,
    LocationType,
    Scene,
    ScriptPlan,
    Weather,
)

log = logging.getLogger(__name__)

__all__ = [
    "Action",
    "ActionType",
    "Actor",
    "ActorColor",
    "ActorKind",
    "ActorRole",
    "CameraHint",
    "Environment",
    "LocationType",
    "Scene",
    "ScriptPlan",
    "Weather",
    "parse_script",
]


def parse_script(
    text: str, use_llm: bool = False, api_key: str | None = None
) -> ScriptPlan:
    """Parse a scenario; with ``use_llm`` try Claude first, falling back to rules."""
    if not text or not text.strip():
        raise ValueError("scenario text is empty")
    if use_llm:
        try:
            from .llm_parser import parse_llm

            return parse_llm(text, api_key=api_key)
        except Exception as exc:  # noqa: BLE001 - any failure means fallback
            log.warning("LLM parser failed, falling back to rule parser: %s", exc)
            plan = parse_rules(text)
            plan.warnings.append(f"llm fallback: {exc}")
            return plan
    return parse_rules(text)
