"""Local vision review of crawl screenshots (Ollama VL when available)."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from backend.app.database import settings

DEFAULT_VISION_MODELS = (
    "llava",
    "llava:latest",
    "llava:7b",
    "qwen2.5-vl",
    "qwen2.5-vl:7b",
    "qwen2-vl",
    "minicpm-v",
)


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/png"


def resolve_image_path(root: Path, image_path: str) -> Path:
    """Resolve a crawl-relative image path; reject path escape."""
    rel = (image_path or "").lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise ValueError("Invalid image path")
    full = (root / rel).resolve()
    root_resolved = root.resolve()
    if not str(full).startswith(str(root_resolved)):
        raise ValueError("Image path escapes crawl root")
    if not full.is_file():
        raise ValueError(f"Image not found: {rel}")
    return full


def list_available_vision_models(base_url: str | None = None) -> list[str]:
    url = (base_url or settings.ollama_base_url).rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{url}/api/tags")
            response.raise_for_status()
            names = [m.get("name") for m in (response.json().get("models") or [])]
            return [n for n in names if n]
    except Exception:
        return []


def pick_vision_model(available: list[str] | None = None) -> str | None:
    available = available if available is not None else list_available_vision_models()
    configured = getattr(settings, "ollama_vision_model", None) or ""
    if configured and (
        configured in available
        or any((m or "").startswith(configured.split(":")[0]) for m in available)
    ):
        return configured
    for candidate in DEFAULT_VISION_MODELS:
        for m in available:
            if m == candidate or (m or "").startswith(candidate.split(":")[0]):
                return m
    # Fallback: any model with vl/llava in the name.
    for m in available:
        low = (m or "").lower()
        if "llava" in low or "vl" in low or "vision" in low:
            return m
    return None


def review_screenshot(
    root: Path,
    image_path: str,
    *,
    question: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Ask a local vision model about a crawl screenshot.

    Falls back to a deterministic note when no vision model is available.
    """
    full = resolve_image_path(root, image_path)
    prompt = (question or "").strip() or (
        "Review this website screenshot. Comment on hierarchy, CTA clarity, "
        "trust, mobile readability, and the top 3 visual improvements. "
        "Be concrete and concise."
    )

    available = list_available_vision_models(base_url)
    vision_model = model or pick_vision_model(available)
    if not vision_model:
        return {
            "ok": False,
            "source": "fallback",
            "image_path": image_path,
            "model": None,
            "review": (
                "No local vision model is installed. Pull one with "
                "`ollama pull llava` or `ollama pull qwen2.5-vl`, then retry. "
                f"Image on file: {image_path}."
            ),
            "error": "vision_model_unavailable",
        }

    b64 = base64.b64encode(full.read_bytes()).decode("ascii")
    url = (base_url or settings.ollama_base_url).rstrip("/")
    payload = {
        "model": vision_model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
        "options": {"temperature": 0.2, "num_predict": 500},
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=180.0, write=60.0, pool=5.0)
        ) as client:
            response = client.post(f"{url}/api/chat", json=payload)
            if response.status_code == 404:
                return {
                    "ok": False,
                    "source": "fallback",
                    "image_path": image_path,
                    "model": vision_model,
                    "review": (
                        f"Vision model '{vision_model}' not found. "
                        f"Pull it with: ollama pull {vision_model}"
                    ),
                    "error": "model_not_found",
                }
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "source": "fallback",
            "image_path": image_path,
            "model": vision_model,
            "review": f"Vision request failed: {exc}",
            "error": str(exc),
        }

    content = ((body.get("message") or {}).get("content")) or body.get("response") or ""
    return {
        "ok": True,
        "source": "ollama_vision",
        "image_path": image_path,
        "mime": _guess_mime(full),
        "model": vision_model,
        "review": str(content).strip(),
        "error": None,
    }


def list_crawl_screenshots(root: Path, *, limit: int = 24) -> list[dict]:
    shot_dir = root / "screenshots"
    if not shot_dir.is_dir():
        return []
    out = []
    for path in sorted(shot_dir.glob("*.png"))[:limit]:
        out.append(
            {
                "path": f"screenshots/{path.name}",
                "name": path.name,
                "url": None,  # filled by route with /data/...
            }
        )
    return out
