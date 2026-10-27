"""LLM client with automatic provider failover.

Providers are tried in order: Groq -> Gemini -> Pollinations (keyless).
A provider with no API key is skipped. All three expose an OpenAI-compatible
chat-completions endpoint, so one small HTTP client covers them all.

If every provider fails, ``LLMError`` is raised and the caller falls back to
deterministic code (the regex parser or a reply template). The LLM never
touches the database: it only returns text that our code validates.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import Settings, get_settings


@dataclass
class Provider:
    name: str
    url: str
    model: str
    api_key: str = ""
    supports_json_mode: bool = True


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    attempts: list[dict] = field(default_factory=list)


class LLMError(Exception):
    """Every provider failed. ``attempts`` says what happened with each one."""

    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


def configured_providers(settings: Optional[Settings] = None) -> list[Provider]:
    """Providers that can be tried with the current settings, in priority order."""
    s = settings or get_settings()
    providers = []
    if s.groq_api_key:
        providers.append(Provider("groq", s.groq_url, s.groq_model, s.groq_api_key))
    if s.gemini_api_key:
        providers.append(Provider("gemini", s.gemini_url, s.gemini_model, s.gemini_api_key))
    if s.pollinations_enabled:
        providers.append(Provider("pollinations", s.pollinations_url, s.pollinations_model,
                                  supports_json_mode=False))
    return providers


def _call(provider: Provider, messages: list[dict], json_mode: bool, timeout: float,
          transport: Optional[httpx.BaseTransport]) -> str:
    """One chat-completions request. Raises on HTTP errors or an empty answer."""
    body: dict = {"model": provider.model, "messages": messages, "temperature": 0}
    if json_mode and provider.supports_json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    with httpx.Client(timeout=timeout, transport=transport) as client:
        resp = client.post(provider.url, headers=headers, json=body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise ValueError("empty response")
    return content.strip()


def chat(messages: list[dict], *, json_mode: bool = False, settings: Optional[Settings] = None,
         transport: Optional[httpx.BaseTransport] = None) -> LLMResult:
    """Send a chat to the first provider that answers.

    With ``json_mode=True`` the answer must be a JSON object; a provider whose
    answer does not parse as JSON counts as failed and the next one is tried.
    """
    s = settings or get_settings()
    providers = configured_providers(s)
    attempts: list[dict] = []
    if not providers:
        raise LLMError("No LLM provider configured.", attempts)

    for provider in providers:
        start = time.perf_counter()
        try:
            text = _call(provider, messages, json_mode, s.llm_timeout_seconds, transport)
            if json_mode:
                text = extract_json_object(text)
            latency = int((time.perf_counter() - start) * 1000)
            attempts.append({"provider": provider.name, "ok": True, "latency_ms": latency})
            return LLMResult(text, provider.name, provider.model, latency, attempts)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            attempts.append({"provider": provider.name, "ok": False,
                             "error": _short_error(exc),
                             "latency_ms": int((time.perf_counter() - start) * 1000)})
    raise LLMError("All LLM providers failed.", attempts)


def extract_json_object(text: str) -> str:
    """Return the JSON object in an LLM answer (strips ```json fences or extra prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    candidate = text[start:end + 1]
    json.loads(candidate)  # raises ValueError if invalid
    return candidate


def _short_error(exc: Exception) -> str:
    """Error summary safe for logs: status code or type, never the API key."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return type(exc).__name__
