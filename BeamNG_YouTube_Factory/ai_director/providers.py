"""Подключаемые ИИ-провайдеры. Архитектура не привязана к одному поставщику.

Интерфейс: provider.complete_json(system, user) -> dict | None
Чтобы добавить своего провайдера: наследуйтесь от AIProvider и зарегистрируйте в PROVIDERS.
"""
import json
import re

import requests

from core.logger import get_logger

log = get_logger("ai")


class AIError(Exception):
    pass


class AIProvider:
    name = "base"
    available = True

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        raise NotImplementedError

    def complete_json(self, system: str, user: str, max_tokens: int = 4000):
        text = self.complete(system, user, max_tokens)
        return extract_json(text)


def extract_json(text: str):
    """Достаёт первый JSON-объект из ответа модели (допускает ```json ... ```)."""
    if not text:
        raise AIError("пустой ответ модели")
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b == -1:
            raise AIError("в ответе нет JSON")
        text = text[a:b + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIError(f"некорректный JSON: {e}")


class OfflineProvider(AIProvider):
    """Нет языковой модели: используется встроенный разбор сценария по правилам."""
    name = "offline"

    def complete(self, system, user, max_tokens=4000):
        raise AIError("offline-провайдер не генерирует текст")


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key, model, timeout=90):
        self.api_key, self.model, self.timeout = api_key, model, timeout
        if not api_key:
            raise AIError("не задан API-ключ Anthropic")

    def complete(self, system, user, max_tokens=4000):
        try:
            import anthropic
        except ImportError:
            raise AIError("пакет anthropic не установлен (pip install anthropic)")
        client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        resp = client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class OpenAICompatibleProvider(AIProvider):
    """OpenAI, OpenRouter, LM Studio, Ollama (/v1) и любой совместимый сервер."""
    name = "openai"

    def __init__(self, api_key, base_url, model, timeout=90):
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url.rstrip("/"), model, timeout

    def complete(self, system, user, max_tokens=4000):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0.4,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        r = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=self.timeout)
        if r.status_code != 200:
            raise AIError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


def make_provider(settings) -> AIProvider:
    kind = settings.get("ai.provider", "offline")
    timeout = settings.get("ai.timeout", 90)
    if kind == "anthropic":
        return AnthropicProvider(settings.secret("ai.anthropic.api_key", "ANTHROPIC_API_KEY"),
                                 settings.get("ai.anthropic.model"), timeout)
    if kind == "openai":
        return OpenAICompatibleProvider(settings.secret("ai.openai.api_key", "OPENAI_API_KEY"),
                                        settings.get("ai.openai.base_url"), settings.get("ai.openai.model"), timeout)
    return OfflineProvider()
