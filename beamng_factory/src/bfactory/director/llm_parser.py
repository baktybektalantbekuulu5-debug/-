"""Optional Claude API scenario parser.

The ``anthropic`` SDK is imported lazily so the package works offline. Any
problem raises :class:`LLMUnavailableError` or :class:`LLMParseError`; the
caller (``parse_script``) falls back to the rule parser.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from .schema import ScriptPlan

MODEL_ID = "claude-sonnet-5-5"
TOOL_NAME = "submit_script_plan"
MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
You are the Director of an automated BeamNG.drive YouTube channel. You turn a
free-text video scenario (usually Russian, sometimes English) into a structured
plan that a game-automation layer will execute.

Rules:
- Actors are vehicles. Give them ids "car1", "car2", ... in order of first
  mention. The same vehicle mentioned again (also via a pronoun or an implicit
  subject) keeps its id; a new id only when the color differs or the text says
  "second/another/второй/другой/ещё один".
- kind is a category, not a game model. Leave model_hint null.
- color.rgba channels are floats in 0..1.
- Split the story into scenes; each scene is one coherent event, usually ending
  at a highlight (crash, rollover, jump). highlight is the index of the climax
  action inside that scene's actions, or null.
- Every action.actor / action.target must be an actor id. For swerve and
  crash_into, target is the vehicle being avoided or hit, if any.
- time_of_day is a fraction of the day: 0.0 = midnight, 0.5 = noon.
- duration_s: roughly 3-8 s per action, +2 s for the highlight.
- camera_hints: crash/rollover -> cinematic, slowmo, replay; chase -> follow,
  drone; drive -> follow, front; jump -> cinematic, slowmo.
- total_duration_s is the sum of scene durations. language is "ru" or "en".
- Set parser to "llm". Do not invent events that are not in the text.

Call the submit_script_plan tool exactly once with the full plan. Do not reply
with plain text."""


class LLMUnavailableError(RuntimeError):
    """The LLM path cannot run (SDK missing or no API key)."""


class LLMParseError(RuntimeError):
    """The model answered but its output could not be turned into a plan."""


def _load_client(api_key: str | None) -> Any:
    key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )
    if not key:
        raise LLMUnavailableError(
            "No Anthropic API key: pass api_key or set ANTHROPIC_API_KEY to use the LLM parser"
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise LLMUnavailableError(
            "The 'anthropic' package is not installed (pip install anthropic)"
        ) from exc
    if api_key or os.environ.get("ANTHROPIC_API_KEY"):
        return anthropic.Anthropic(api_key=key)
    return anthropic.Anthropic()


def _tool_definition() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Submit the structured plan of the video scenario.",
        "input_schema": ScriptPlan.model_json_schema(),
    }


def _request(client: Any, text: str) -> Any:
    """Send the request, with server-side refusal fallbacks when supported."""
    kwargs: dict[str, Any] = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [_tool_definition()],
        # Forced tool_choice is rejected on this model; steer via the prompt.
        "tool_choice": {"type": "auto"},
        "messages": [{"role": "user", "content": f"Scenario:\n\n{text}"}],
    }
    try:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        )
    except TypeError:
        # Older SDK without the fallbacks parameter.
        return client.messages.create(**kwargs)


def parse_llm(text: str, api_key: str | None = None) -> ScriptPlan:
    """Parse a scenario with Claude; raises on any failure."""
    client = _load_client(api_key)
    response = _request(client, text)

    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMParseError("The model declined the request (stop_reason=refusal)")
    block = next(
        (
            b
            for b in response.content
            if getattr(b, "type", None) == "tool_use" and b.name == TOOL_NAME
        ),
        None,
    )
    if block is None:
        raise LLMParseError(
            f"No {TOOL_NAME} tool call in the response (stop_reason={response.stop_reason})"
        )

    data = block.input if isinstance(block.input, dict) else json.loads(block.input)
    data["parser"] = "llm"
    try:
        plan = ScriptPlan.model_validate(data)
    except ValidationError as exc:
        raise LLMParseError(f"Model output does not match ScriptPlan: {exc}") from exc
    if not plan.total_duration_s:
        plan.total_duration_s = round(sum(s.duration_s for s in plan.scenes), 2)
    return plan
