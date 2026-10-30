"""Human-in-the-loop feedback store — few-shot examples for the generative agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

FEEDBACK_DIR = Path("data/agency/feedback")
EXAMPLES_DIR = Path("config/agency/examples")

# Preferred kinds for Brain training (order matters).
BRAIN_KINDS = (
    "brain_recommendation",
    "executive_summary",
    "content_suggestions",
    "opportunity_rewrite",
    "chat_reply",
    "proposal_narrative",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_feedback(
    *,
    kind: str,
    before: Any,
    after: Any,
    domain: str | None = None,
    crawl_id: str | None = None,
    meta: dict | None = None,
) -> Path:
    """Persist an edit so future agent runs can learn agency voice."""
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": str(uuid4()),
        "kind": kind,
        "domain": domain,
        "crawl_id": crawl_id,
        "before": before,
        "after": after,
        "meta": meta or {},
        "created_at": _now(),
        "approved_example": True,
    }
    path = FEEDBACK_DIR / f"{entry['created_at'][:10]}_{entry['id'][:8]}_{kind}.json"
    path.write_text(json.dumps(entry, indent=2, default=str), encoding="utf-8")
    return path


def load_examples(
    limit: int = 5,
    *,
    kinds: tuple[str, ...] | None = None,
    industry: str | None = None,
) -> list[dict[str, Any]]:
    """Load approved curated + feedback examples for few-shot prompts."""
    items: list[dict[str, Any]] = []

    if EXAMPLES_DIR.exists():
        for path in sorted(EXAMPLES_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("approved_example") is False:
                    continue
                data["_source"] = str(path)
                items.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    if FEEDBACK_DIR.exists():
        for path in sorted(FEEDBACK_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("approved_example") is False:
                    continue
                data["_source"] = str(path)
                items.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    want = kinds or BRAIN_KINDS
    preferred = [i for i in items if (i.get("kind") or "") in want]
    pool = preferred or items

    if industry:
        industry_key = industry.lower().replace(" ", "_")
        matched = [
            i
            for i in pool
            if industry_key in str(i.get("industry") or "").lower()
            or industry_key in str(i.get("_source") or "").lower()
        ]
        # Industry matches first, then the rest
        rest = [i for i in pool if i not in matched]
        pool = matched + rest

    return pool[:limit]


def format_few_shot_block(
    examples: list[dict],
    *,
    max_chars: int = 3200,
) -> str:
    """Serialize gold examples for prompt injection."""
    if not examples:
        return ""
    chunks = [
        "Approved agency training examples — match this voice, structure, and CTA specificity:"
    ]
    used = 0
    for ex in examples:
        kind = ex.get("kind") or "example"
        industry = ex.get("industry") or ""
        refs = ((ex.get("meta") or {}).get("references") or [])[:3]
        after = ex.get("after")
        if isinstance(after, dict):
            # Prefer the commercially useful fields for Brain.
            slim = {
                k: after[k]
                for k in (
                    "executive_summary",
                    "site_story_summary",
                    "priority_actions",
                    "content_suggestions",
                    "proposal_angles",
                    "quick_wins",
                    "rules",
                )
                if k in after
            }
            if not slim:
                slim = after
            body = json.dumps(slim, ensure_ascii=True)
            # Allow more room for full brain_recommendation gold answers.
            cap = 1400 if kind == "brain_recommendation" else 500
            body = body[:cap]
        else:
            body = str(after or "")[:500]
        header = f"[{kind}" + (f" / {industry}" if industry else "") + "]"
        if refs:
            header += f" refs: {', '.join(str(r) for r in refs)}"
        piece = f"- {header}\n  {body}"
        if used + len(piece) > max_chars:
            break
        chunks.append(piece)
        used += len(piece)
    if len(chunks) == 1:
        return ""
    return "\n".join(chunks)


def pick_industry_template(
    industry: str | None,
    *,
    kind: str = "brain_recommendation",
) -> dict | None:
    """Return the best matching curated brain_recommendation.after dict."""
    examples = load_examples(limit=8, kinds=(kind,), industry=industry)
    for ex in examples:
        after = ex.get("after")
        if isinstance(after, dict) and (
            after.get("content_suggestions") or after.get("executive_summary")
        ):
            return after
    # Fallback: any brain_recommendation
    for ex in load_examples(limit=5, kinds=(kind,)):
        after = ex.get("after")
        if isinstance(after, dict):
            return after
    return None


_GENERIC_ACTION_TITLES = {
    "make the website feel faster, especially on mobile",
    "improve accessibility and readability across the website",
    "improve site security and visitor trust signals",
    "upgrade the website platform where it is holding the business back",
    "strengthen search visibility foundations",
    "clean up technical quality issues affecting reliability",
    "improve homepage conversion and primary calls to action",
    "clarify what the business offers and who it serves",
}


def _actions_look_generic(actions: list | None) -> bool:
    """True when most priority_actions are stock opportunity theme titles."""
    items = [a for a in (actions or []) if isinstance(a, dict) and a.get("title")]
    if not items:
        return True
    generic = sum(
        1
        for a in items
        if str(a.get("title") or "").strip().lower() in _GENERIC_ACTION_TITLES
    )
    return generic >= max(2, (len(items) + 1) // 2)


def enrich_recommendations_from_examples(
    recommendations: dict,
    *,
    industry: str | None = None,
) -> dict:
    """Blend gold example voice into a baseline (profile-first / rule-based) answer.

    Does not invent a new business story — upgrades executive pitch, CTAs,
    content_suggestions, and generic scanner-led priority_actions.
    """
    gold = pick_industry_template(industry)
    if not gold:
        return recommendations

    out = dict(recommendations)

    # Upgrade executive summary if it still reads like a score dump.
    summary = str(out.get("executive_summary") or "")
    gold_summary = str(gold.get("executive_summary") or "")
    if gold_summary and (
        len(summary) < 120
        or "overall score is" in summary.lower()
        or "core services:" in summary.lower()
        or summary.lower().startswith("we reviewed")
    ):
        # Keep brand/domain facts from baseline when present; prefer gold pitch shape.
        out["executive_summary"] = gold_summary

    # Prefer gold content_suggestions structure when baseline heroes look SEO-y.
    gold_copy = gold.get("content_suggestions")
    base_copy = out.get("content_suggestions") or []
    if isinstance(gold_copy, list) and gold_copy:
        needs_upgrade = False
        for item in base_copy:
            if not isinstance(item, dict):
                continue
            sug = str(item.get("suggested") or "")
            cur = str(item.get("current") or "")
            if "|" in sug or " – " in sug:
                needs_upgrade = True
            if item.get("area") == "Hero headline" and (
                "|" in cur or sug.lower() in {"home", "homepage"}
            ):
                needs_upgrade = True
        if needs_upgrade or len(base_copy) < 3:
            # Keep baseline "current" fields when possible; take suggested/why from gold.
            merged: list[dict] = []
            by_area = {
                str(i.get("area")): i
                for i in base_copy
                if isinstance(i, dict) and i.get("area")
            }
            for g in gold_copy:
                if not isinstance(g, dict):
                    continue
                area = str(g.get("area") or "")
                base = by_area.get(area) or {}
                merged.append(
                    {
                        "area": area or g.get("area"),
                        "current": base.get("current") or g.get("current") or "",
                        "suggested": g.get("suggested") or base.get("suggested") or "",
                        "why": g.get("why") or base.get("why") or "",
                    }
                )
            if merged:
                out["content_suggestions"] = merged

    # Replace scanner-theme priority_actions with industry gold commercial plan.
    gold_actions = gold.get("priority_actions")
    base_actions = out.get("priority_actions") or []
    if isinstance(gold_actions, list) and gold_actions and _actions_look_generic(base_actions):
        out["priority_actions"] = [dict(a) for a in gold_actions if isinstance(a, dict)][:6]
        if isinstance(gold.get("quick_wins"), list) and gold["quick_wins"]:
            out["quick_wins"] = list(gold["quick_wins"])[:5]
        if isinstance(gold.get("strategic_improvements"), list) and gold[
            "strategic_improvements"
        ]:
            out["strategic_improvements"] = list(gold["strategic_improvements"])[:6]
        if isinstance(gold.get("proposal_angles"), list) and gold["proposal_angles"]:
            out["proposal_angles"] = list(gold["proposal_angles"])[:4]
    elif not base_actions and isinstance(gold_actions, list):
        out["priority_actions"] = list(gold_actions)[:6]

    # Soft-merge proposal angles / quick wins if baseline is empty.
    if not out.get("proposal_angles") and gold.get("proposal_angles"):
        out["proposal_angles"] = list(gold["proposal_angles"])[:4]
    if not out.get("quick_wins") and gold.get("quick_wins"):
        out["quick_wins"] = list(gold["quick_wins"])[:5]

    out["_trained_from_examples"] = True
    return out
