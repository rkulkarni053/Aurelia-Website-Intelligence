"""Social content chat — refine posts, hashtags, and soundtrack ideas with Brain."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.social_content import (
    decide_social_content,
    load_social_content,
    write_social_content,
)

CHAT_FILENAME = "design/social_chat.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_social_chat(root: Path) -> dict:
    data = _load_json(root / CHAT_FILENAME) or {}
    return {
        "version": 1,
        "messages": list(data.get("messages") or []),
        "updated_at": data.get("updated_at"),
    }


def save_social_chat(root: Path, chat: dict) -> Path:
    path = root / CHAT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "messages": list(chat.get("messages") or [])[-40:],
        "updated_at": _now(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def ensure_social_pack(
    root: Path,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    profile: dict | None = None,
) -> dict:
    existing = load_social_content(root)
    if existing and (existing.get("post_ideas") or existing.get("soundtracks")):
        return existing

    recs = (recommendations or {}).get("recommendations") or recommendations or {}
    if isinstance(recs.get("social_content"), dict) and recs["social_content"].get(
        "post_ideas"
    ):
        write_social_content(root, recs["social_content"])
        return recs["social_content"]

    pack = evidence_pack or {}
    direction = recs.get("design_direction") if isinstance(recs, dict) else None
    meta = recs.get("content_metadata") if isinstance(recs, dict) else None
    social = decide_social_content(
        pack,
        profile,
        design_direction=direction if isinstance(direction, dict) else None,
        content_metadata=meta if isinstance(meta, dict) else None,
    )
    write_social_content(root, social)
    return social


def _rule_patch(message: str, social: dict) -> tuple[dict, str]:
    """Deterministic edits for common social requests."""
    text = (message or "").strip()
    low = text.lower()
    patch: dict[str, Any] = {}
    notes: list[str] = []
    out = dict(social)

    # Add a Reel / TikTok idea from free text after "add reel:" / "new idea:"
    m = re.search(
        r"(?i)(?:add|new)\s+(?:a\s+)?(?:reel|tiktok|idea|post)\s*[:\-]\s*(.+)$",
        text,
    )
    if m:
        hook = m.group(1).strip()[:140]
        ideas = list(out.get("post_ideas") or [])
        ideas.insert(
            0,
            {
                "format": "Reel / TikTok",
                "hook": hook,
                "body": "Short cut with brand tone — end on the primary CTA.",
                "cta": out.get("post_ideas", [{}])[0].get("cta")
                if out.get("post_ideas")
                else "Get in touch",
            },
        )
        out["post_ideas"] = ideas[:8]
        patch["post_ideas"] = out["post_ideas"]
        notes.append(f"Added Reel idea: {hook}")

    # Swap primary CTA across ideas
    m = re.search(r"(?i)(?:cta|call to action)\s*(?:to|:|=)\s*[\"']?([^\"'\n]+)[\"']?", text)
    if m:
        cta = m.group(1).strip()[:80]
        ideas = []
        for idea in out.get("post_ideas") or []:
            if isinstance(idea, dict):
                row = dict(idea)
                row["cta"] = cta
                ideas.append(row)
        out["post_ideas"] = ideas
        patch["post_ideas"] = ideas
        notes.append(f"Updated CTAs to “{cta}”.")

    # Hashtag add
    tags = re.findall(r"#([A-Za-z0-9_]+)", text)
    if tags and any(w in low for w in ("hashtag", "tag", "add #")):
        current = list(out.get("hashtags") or [])
        for t in tags:
            tag = "#" + t
            if tag not in current:
                current.append(tag)
        out["hashtags"] = current[:16]
        patch["hashtags"] = out["hashtags"]
        notes.append("Updated hashtags: " + ", ".join(out["hashtags"][-len(tags) :]))

    # Soundtrack preference
    if any(w in low for w in ("song", "music", "soundtrack", "audio", "track")):
        if "more upbeat" in low or "energetic" in low or "dance" in low:
            tracks = list(out.get("soundtracks") or [])
            tracks.insert(
                0,
                {
                    "title": "Electric Feel",
                    "artist": "MGMT (or cleared instrumental)",
                    "mood": "upbeat, joyful energy",
                    "why": "Stronger reception / celebration pacing per your request.",
                    "use_for": ["Reel", "reception montage"],
                    "trend_note": "Confirm Reels-cleared audio the week you post.",
                },
            )
            out["soundtracks"] = tracks[:6]
            patch["soundtracks"] = out["soundtracks"]
            notes.append("Prioritised a more upbeat soundtrack reference.")
        elif "softer" in low or "romantic" in low or "intimate" in low or "slower" in low:
            tracks = list(out.get("soundtracks") or [])
            tracks.insert(
                0,
                {
                    "title": "Beyond",
                    "artist": "Leon Bridges",
                    "mood": "warm, romantic, intimate",
                    "why": "Softer emotional bed for vows / portrait cuts.",
                    "use_for": ["highlight film", "Instagram Reel"],
                    "trend_note": "Evergreen wedding edit staple — verify Reels availability.",
                },
            )
            out["soundtracks"] = tracks[:6]
            patch["soundtracks"] = out["soundtracks"]
            notes.append("Prioritised a softer / romantic soundtrack reference.")

    # LinkedIn focus
    if "linkedin" in low:
        platforms = list(out.get("platforms") or [])
        if "linkedin" not in [p.lower() for p in platforms]:
            platforms.insert(0, "linkedin")
        out["platforms"] = platforms
        ideas = list(out.get("post_ideas") or [])
        ideas.insert(
            0,
            {
                "format": "LinkedIn",
                "hook": "What ‘done right’ looks like for buyers",
                "body": "Carousel: problem → process → proof → CTA. Keep jargon out.",
                "cta": (ideas[0].get("cta") if ideas else "Start a project"),
            },
        )
        out["post_ideas"] = ideas[:8]
        patch["platforms"] = platforms
        patch["post_ideas"] = out["post_ideas"]
        notes.append("Added a LinkedIn-first idea and prioritised the platform.")

    if not notes:
        # Summarise current pack
        n_ideas = len(out.get("post_ideas") or [])
        n_tracks = len(out.get("soundtracks") or [])
        pillars = ", ".join(out.get("content_pillars") or [])[:120]
        reply = (
            f"Here’s the social plan for {out.get('brand') or 'this brand'}: "
            f"{n_ideas} post ideas, {n_tracks} soundtrack references. "
            f"Pillars: {pillars or '—'}. "
            "Try: “Add reel: …”, “CTA: Book a discovery call”, "
            "“softer music”, “more upbeat”, “add hashtag #YourTag”, or “focus on LinkedIn”."
        )
        return out, reply

    reply = "Updated the social pack. " + " ".join(notes)
    reply += " Review the panel on the right — ask for another tweak anytime."
    return out, reply


def _llm_social_turn(
    *,
    message: str,
    social: dict,
    model: str | None,
    timeout: float,
) -> dict | None:
    from backend.app.services.llm_client import LLMError, chat_json

    system = (
        "You are Aurelia’s social strategist. Improve the social_content JSON for THIS brand. "
        "Return ONLY JSON: "
        '{"assistant_message":"...", "social_patch":{...partial fields...}, "suggestions":["..."]} '
        "social_patch may include post_ideas, soundtracks, hashtags, platforms, week_plan, "
        "content_pillars, posting_cadence. Keep soundtrack trend_note honest "
        "(mood-fit refs, verify Reels/TikTok — no fake #1 charts)."
    )
    user = json.dumps(
        {"message": message, "social_content": social},
        ensure_ascii=True,
    )[:6000]
    try:
        parsed, _p, _m = chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            provider="ollama",
            model=model,
            temperature=0.35,
            max_tokens=900,
            timeout=timeout,
        )
        return parsed if isinstance(parsed, dict) else None
    except (LLMError, ValueError, json.JSONDecodeError):
        return None


def _merge_social(base: dict, patch: dict | None) -> dict:
    if not isinstance(patch, dict) or not patch:
        return base
    out = dict(base)
    for key, val in patch.items():
        if key in {
            "post_ideas",
            "soundtracks",
            "hashtags",
            "platforms",
            "week_plan",
            "content_pillars",
            "caption_formulas",
        } and isinstance(val, list) and val:
            out[key] = val
        elif key in {"posting_cadence", "music_disclaimer"} and isinstance(val, str) and val.strip():
            out[key] = val.strip()[:240]
    out["updated_at"] = _now()
    out["source"] = "social_chat"
    return out


def process_social_chat_message(
    root: Path,
    message: str,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    profile: dict | None = None,
    prefer_ollama: bool = True,
    model: str | None = None,
) -> dict:
    message = (message or "").strip()
    if not message:
        raise ValueError("Message is empty")

    social = ensure_social_pack(
        root,
        recommendations=recommendations,
        evidence_pack=evidence_pack,
        profile=profile,
    )
    chat = load_social_chat(root)
    chat.setdefault("messages", [])
    chat["messages"].append({"role": "user", "content": message, "at": _now()})

    patched, rule_reply = _rule_patch(message, social)
    assistant = rule_reply
    source = "rule_based"
    suggestions = [
        "Add reel: The moment everything goes quiet",
        "CTA: Enquire about your date",
        "softer music",
        "more upbeat soundtrack",
        "focus on LinkedIn",
    ]
    error = None

    # On CPU, keep chat snappy — only try LLM when rule patch did nothing
    # substantive beyond the summary path... Actually rule_patch always returns
    # either edits or a summary. Try LLM only for open-ended asks when enabled.
    open_ended = not any(
        k in message.lower()
        for k in (
            "add reel",
            "add tiktok",
            "add idea",
            "add post",
            "cta:",
            "cta ",
            "hashtag",
            "#",
            "linkedin",
            "softer",
            "upbeat",
            "energetic",
            "romantic",
            "song",
            "music",
            "soundtrack",
        )
    )

    if prefer_ollama and open_ended:
        from backend.app.database import settings
        from backend.app.services.agency_settings import load_agency_settings
        from backend.app.services.design_chat import (
            _ollama_on_gpu,
            _prefer_fast_ollama_model,
        )

        agency = load_agency_settings()
        agent_cfg = agency.get("agent") or {}
        on_gpu = _ollama_on_gpu(settings.ollama_base_url)
        chat_model = model or settings.ollama_model
        if on_gpu is not True or agent_cfg.get("prefer_fast_chat_model", True):
            chat_model = _prefer_fast_ollama_model(chat_model)
        timeout = float(agent_cfg.get("chat_timeout_seconds") or 40)
        if on_gpu is not True:
            timeout = min(timeout, 40.0)
            # Skip LLM on CPU for social — rule pack + summary is enough.
            llm = None
        else:
            llm = _llm_social_turn(
                message=message,
                social=patched,
                model=chat_model,
                timeout=timeout,
            )
        if isinstance(llm, dict):
            patched = _merge_social(patched, llm.get("social_patch"))
            if llm.get("assistant_message"):
                assistant = str(llm["assistant_message"])
            if isinstance(llm.get("suggestions"), list) and llm["suggestions"]:
                suggestions = [str(s) for s in llm["suggestions"][:6]]
            source = "ollama"

    write_social_content(root, patched)
    chat["messages"].append(
        {
            "role": "assistant",
            "content": assistant,
            "at": _now(),
            "source": source,
            "suggestions": suggestions,
        }
    )
    save_social_chat(root, chat)

    return {
        "assistant_message": assistant,
        "suggestions": suggestions,
        "social_content": patched,
        "messages": chat["messages"],
        "source": source,
        "error": error,
        "updated_at": _now(),
    }
