"""Unified LLM client for Ollama (local) + OpenAI + Anthropic (cloud).

Used by Brain recommendations, Design chat, and Proposal narrative.
Cloud providers require API keys in the environment — never hardcode secrets.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.app.database import settings


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output (raw or fenced)."""
    if not text:
        raise ValueError("Empty model response")
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        data = json.loads(fenced.group(1))
        if isinstance(data, dict):
            return data

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("No JSON object found in model response")


def resolve_provider(explicit: str | None = None) -> str:
    provider = (explicit or settings.brain_provider or "ollama").strip().lower()
    if provider in {"gpt", "chatgpt"}:
        return "openai"
    if provider in {"claude"}:
        return "anthropic"
    if provider not in {"ollama", "openai", "anthropic"}:
        return "ollama"
    return provider


def resolve_model(provider: str | None = None) -> str:
    p = resolve_provider(provider)
    if p == "openai":
        return settings.openai_model
    if p == "anthropic":
        return settings.anthropic_model
    return settings.ollama_model


def cloud_provider_usable(provider: str) -> bool:
    """True only when a cloud provider has a key and is not known-broke (e.g. no credits)."""
    p = (provider or "").strip().lower()
    if p == "openai":
        return bool(settings.openai_api_key)
    if p != "anthropic":
        return False
    if not settings.anthropic_api_key:
        return False
    # Fast probe — avoid multi-minute Brain waits on empty Anthropic billing.
    try:
        with httpx.Client(timeout=6.0) as client:
            probe = client.post(
                f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
        text = (probe.text or "").lower()
        if probe.status_code == 400 and "credit" in text:
            return False
        if probe.status_code in {401, 403}:
            return False
        # 200 or other non-auth errors: key exists; real call may still fail.
        return probe.status_code < 500
    except Exception:
        return False


def provider_status() -> dict[str, Any]:
    """Status payload for Settings / health UI."""
    provider = resolve_provider()
    model = resolve_model(provider)
    out: dict[str, Any] = {
        "provider": provider,
        "configured_model": model,
        "model_ready": False,
        "ok": False,
        "ollama": None,
        "openai": {
            "configured": bool(settings.openai_api_key),
            "model": settings.openai_model,
        },
        "anthropic": {
            "configured": bool(settings.anthropic_api_key),
            "model": settings.anthropic_model,
            "billing": None,
        },
    }

    # Always probe Anthropic billing when a key exists (even if Brain uses Ollama).
    if settings.anthropic_api_key:
        try:
            with httpx.Client(timeout=8.0) as client:
                probe = client.post(
                    f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            if probe.status_code == 400 and "credit" in (probe.text or "").lower():
                out["anthropic"]["billing"] = "no_credits"
        except Exception:
            pass

    # Always report local Ollama availability as a fallback option.
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            models = [m.get("name") for m in (response.json().get("models") or [])]
            out["ollama"] = {
                "ok": True,
                "models": models,
                "base_url": settings.ollama_base_url,
            }
    except Exception as exc:
        out["ollama"] = {
            "ok": False,
            "models": [],
            "base_url": settings.ollama_base_url,
            "error": str(exc),
        }

    if provider == "ollama":
        models = (out["ollama"] or {}).get("models") or []
        out["ok"] = bool((out["ollama"] or {}).get("ok"))
        out["model_ready"] = model in models or any(
            (m or "").startswith(model.split(":")[0]) for m in models
        )
        out["error"] = None if out["ok"] else (out["ollama"] or {}).get("error")
        return out

    if provider == "openai":
        out["ok"] = bool(settings.openai_api_key)
        out["model_ready"] = out["ok"]
        out["error"] = None if out["ok"] else "Set OPENAI_API_KEY in .env"
        return out

    # anthropic
    out["ok"] = bool(settings.anthropic_api_key)
    out["model_ready"] = out["ok"]
    out["error"] = None if out["ok"] else "Set ANTHROPIC_API_KEY in .env"
    # Soft probe: surface empty billing so Settings explains a "dumb" Brain.
    if out["ok"]:
        try:
            with httpx.Client(timeout=8.0) as client:
                probe = client.post(
                    f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            if probe.status_code == 400 and "credit" in (probe.text or "").lower():
                out["ok"] = False
                out["model_ready"] = False
                out["error"] = (
                    "Anthropic key works but credit balance is too low — "
                    "Brain falls back to local/rules until you add credits."
                )
                if isinstance(out.get("anthropic"), dict):
                    out["anthropic"]["billing"] = "no_credits"
        except Exception:
            pass
    return out


def chat_json(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    timeout: float | None = None,
) -> tuple[dict, str, str]:
    """Send a chat and return (parsed_json, provider_used, model_used).

    ``messages`` use OpenAI-style roles: system / user / assistant.
    """
    provider = resolve_provider(provider)
    model = model or resolve_model(provider)
    timeout = timeout if timeout is not None else float(settings.ollama_timeout_seconds)

    try:
        if provider == "openai":
            parsed = _chat_openai(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                json_mode=True,
            )
            if not isinstance(parsed, dict):
                parsed = extract_json(str(parsed))
            return parsed, "openai", model
        if provider == "anthropic":
            return (
                extract_json(
                    _chat_anthropic(
                        messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                ),
                "anthropic",
                model,
            )
        return (
            extract_json(
                _chat_ollama(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    json_mode=True,
                )
            ),
            "ollama",
            model,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(f"Could not parse model JSON: {exc}") from exc


def chat_text(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 280,
    timeout: float | None = None,
) -> tuple[str, str, str]:
    """Send a chat and return (plain_text, provider_used, model_used)."""
    provider = resolve_provider(provider)
    model = model or resolve_model(provider)
    timeout = timeout if timeout is not None else float(settings.ollama_timeout_seconds)

    if provider == "openai":
        return (
            _chat_openai(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                json_mode=False,
            ),
            "openai",
            model,
        )
    if provider == "anthropic":
        return (
            _chat_anthropic(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            ),
            "anthropic",
            model,
        )
    return (
        _chat_ollama(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            json_mode=False,
        ),
        "ollama",
        model,
    )


def _chat_ollama(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    json_mode: bool = True,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
        "messages": messages,
    }
    # Qwen3 thinking mode wraps reasoning before JSON and breaks format=json.
    if "qwen3" in (model or "").lower():
        payload["think"] = False
    if json_mode:
        payload["format"] = "json"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=timeout, write=30.0, pool=5.0)
        ) as client:
            response = client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json=payload,
            )
            if response.status_code == 404:
                raise LLMError(
                    f"Ollama model '{model}' not found. Pull it with: ollama pull {model}"
                )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc

    content = ((body.get("message") or {}).get("content")) or body.get("response")
    if not content:
        raise LLMError("Ollama returned an empty response")
    return str(content)


def _chat_openai(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    json_mode: bool = True,
) -> str | dict:
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not set in .env")

    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=5.0)
        ) as client:
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code == 401:
                raise LLMError("OpenAI rejected the API key (401)")
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI request failed: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected OpenAI response shape") from exc
    if not content:
        raise LLMError("OpenAI returned an empty response")
    if not json_mode:
        return str(content)
    try:
        return extract_json(content)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(f"Could not parse OpenAI JSON: {exc}") from exc


def _chat_anthropic(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not set in .env")

    system = ""
    converted: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            system = f"{system}\n{content}".strip() if system else content
            continue
        if role not in {"user", "assistant"}:
            continue
        converted.append({"role": role, "content": content})

    if not converted:
        raise LLMError("No user/assistant messages for Anthropic")

    # Anthropic requires alternating roles starting with user.
    if converted[0]["role"] != "user":
        converted.insert(0, {"role": "user", "content": "Continue."})

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": converted,
    }
    if system:
        payload["system"] = system

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=5.0)
        ) as client:
            response = client.post(
                f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                headers=headers,
                json=payload,
            )
            if response.status_code == 401:
                raise LLMError("Anthropic rejected the API key (401)")
            if response.status_code == 400:
                detail = (response.text or "").lower()
                if "credit" in detail:
                    raise LLMError(
                        "Anthropic has no usable credits — add billing or use local Ollama"
                    )
                raise LLMError(
                    f"Anthropic rejected the request (400): {(response.text or '')[:240]}"
                )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"Anthropic request failed: {exc}") from exc

    parts = body.get("content") or []
    content = "".join(
        p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
    )
    if not content:
        raise LLMError("Anthropic returned an empty response")
    return content
