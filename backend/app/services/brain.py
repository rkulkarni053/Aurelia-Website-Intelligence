"""Local AI brain: turn an evidence pack into structured recommendations.

Talks to a local Ollama instance (free / open-source). Falls back to a
deterministic rule-based plan when Ollama is unavailable so the product
still returns useful suggestions.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

RECOMMENDATIONS_FILENAME = "evidence/recommendations.json"

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
# 7B on CPU needs more headroom than 3B for Brain + long Design chat.
REQUEST_TIMEOUT = 240.0
OLLAMA_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=REQUEST_TIMEOUT, write=30.0, pool=5.0)

SYSTEM_PROMPT = """You are Website Intelligence, a senior web consultant.
Given a compact website audit evidence pack that includes site_story narrative
excerpts (homepage/about/services copy), you must:

1) Understand what the business/website is actually about.
2) Recommend improvements that fit that story (not generic SEO spam).

Return ONLY valid JSON matching this schema:
{
  "site_story_summary": {
    "business_type": "what kind of company/product/site this is",
    "audience": "who it seems to speak to",
    "story": "2-4 sentences: the story/promise the site is trying to tell",
    "offer": "what they appear to sell or offer",
    "tone": "brand tone in a few words (e.g. formal, playful, clinical)",
    "gaps": ["story/messaging gaps visible from the excerpts"]
  },
  "executive_summary": "2-4 sentences for a business owner covering story + audit priorities",
  "priority_actions": [
    {
      "title": "short action title",
      "category": "seo|performance|accessibility|security|technical|content|ux",
      "impact": "high|medium|low",
      "effort": "low|medium|high",
      "why": "why this matters for THIS business/story",
      "how": "concrete next step"
    }
  ],
  "quick_wins": ["short items that can be done this week"],
  "strategic_improvements": ["larger upgrades / redesign themes tied to their story"],
  "proposal_angles": [
    "sales angles for a business proposal based on the audit AND their story"
  ],
  "content_suggestions": [
    {
      "area": "Hero headline | Hero subcopy | Primary CTA | About | Services | etc.",
      "current": "what the site roughly says now, or empty",
      "suggested": "rewritten copy ready to paste",
      "why": "why this helps conversion or clarity"
    }
  ],
  "mockup_prompts": [
    "image prompts for an improved homepage that match their industry and story"
  ]
}

Rules:
- Use site_story excerpts first to infer business type, audience, and promise.
- If story evidence is thin, say so in gaps; do not invent a fake brand story.
- Prefer findings with higher severity, but phrase recommendations in their domain language.
- Be specific to the evidence; do not invent tech that is not in the pack.
- Keep priority_actions to at most 8 items, ordered by impact then effort.
- Keep lists concise.
- Always include 4-6 content_suggestions with concrete rewritten copy (not audit jargon).
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def shrink_pack_for_prompt(pack: dict, max_findings: int = 25) -> dict:
    """Reduce the pack further for small local models / context windows."""
    findings = pack.get("findings") or {}
    top = list(findings.get("top") or [])[:max_findings]
    for item in top:
        item.pop("detail", None)

    story = pack.get("site_story") or {}
    story_pages = []
    for page in (story.get("pages") or [])[:4]:
        story_pages.append(
            {
                "url": page.get("url"),
                "role": page.get("role"),
                "title": page.get("title"),
                "h1": (page.get("h1") or [])[:2],
                "meta_description": page.get("meta_description"),
                "body_excerpt": (page.get("body_excerpt") or "")[:700],
                "ctas": (page.get("ctas") or [])[:4],
            }
        )

    return {
        "website": pack.get("website"),
        "crawl": {
            "id": (pack.get("crawl") or {}).get("id"),
            "pages_crawled": (pack.get("crawl") or {}).get("pages_crawled"),
        },
        "scores": pack.get("scores"),
        "site_story": {
            "likely_business_name": story.get("likely_business_name"),
            "headlines": (story.get("headlines") or [])[:8],
            "value_prop_candidates": (story.get("value_prop_candidates") or [])[:3],
            "calls_to_action": (story.get("calls_to_action") or [])[:5],
            "roles_present": story.get("roles_present"),
            "pages": story_pages,
        },
        "content_seo": pack.get("content_seo"),
        "conversion_path": pack.get("conversion_path"),
        "upgrades": {
            "opportunities": (
                ((pack.get("upgrades") or {}).get("opportunities") or [])[:6]
            )
        },
        "findings": {
            "total": findings.get("total"),
            "by_severity": findings.get("by_severity"),
            "by_category": findings.get("by_category"),
            "top": top,
        },
        "ssl": pack.get("ssl"),
        "seo": pack.get("seo"),
        "technologies": {
            "detections": (
                ((pack.get("technologies") or {}).get("detections") or [])[:15]
            )
        },
        "performance": pack.get("performance"),
        "accessibility": pack.get("accessibility"),
    }


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Model response did not contain JSON")
    return json.loads(match.group(0))


def _normalize_site_story_summary(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    gaps = raw.get("gaps")
    if isinstance(gaps, str):
        gaps = [gaps]
    if not isinstance(gaps, list):
        gaps = []
    return {
        "business_type": str(raw.get("business_type") or "").strip(),
        "audience": str(raw.get("audience") or "").strip(),
        "story": str(raw.get("story") or "").strip(),
        "offer": str(raw.get("offer") or "").strip(),
        "tone": str(raw.get("tone") or "").strip(),
        "gaps": [str(x) for x in gaps[:6]],
    }


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


_JARGON_RE = re.compile(
    r"(?i)\b(wcag|axe|lighthouse|playwright|siteone|elements must|"
    r"a11y_[a-z0-9_-]+|definition-list|landmark-|color-contrast)\b|"
    r"`[a-z0-9_-]+`|<dl>|<dt>|<dd>"
)


def _is_jargon_action(item: dict) -> bool:
    blob = " ".join(
        str(item.get(k) or "") for k in ("title", "why", "how")
    )
    return bool(_JARGON_RE.search(blob))


def normalize_recommendations(raw: dict) -> dict:
    actions = []
    for item in _as_list(raw.get("priority_actions")):
        if not isinstance(item, dict):
            continue
        if _is_jargon_action(item):
            continue
        actions.append(
            {
                "title": str(item.get("title") or "Untitled action"),
                "category": str(item.get("category") or "technical"),
                "impact": str(item.get("impact") or "medium"),
                "effort": str(item.get("effort") or "medium"),
                "why": str(item.get("why") or ""),
                "how": str(item.get("how") or ""),
                "opportunity_theme": str(item.get("opportunity_theme") or ""),
            }
        )

    out = {
        "site_story_summary": _normalize_site_story_summary(
            raw.get("site_story_summary")
        ),
        "executive_summary": str(raw.get("executive_summary") or "").strip(),
        "priority_actions": actions[:8],
        "quick_wins": [
            str(x)
            for x in _as_list(raw.get("quick_wins"))[:10]
            if not _JARGON_RE.search(str(x))
        ],
        "strategic_improvements": [
            str(x) for x in _as_list(raw.get("strategic_improvements"))[:10]
        ],
        "proposal_angles": [
            str(x) for x in _as_list(raw.get("proposal_angles"))[:8]
        ],
        "content_suggestions": _normalize_content_suggestions(
            raw.get("content_suggestions")
        ),
        "mockup_prompts": [
            str(x) for x in _as_list(raw.get("mockup_prompts"))[:5]
        ],
    }
    if isinstance(raw.get("design_direction"), dict):
        out["design_direction"] = raw["design_direction"]
    if isinstance(raw.get("content_metadata"), dict):
        out["content_metadata"] = raw["content_metadata"]
    if isinstance(raw.get("social_content"), dict):
        out["social_content"] = raw["social_content"]
    return out


def _normalize_content_suggestions(raw: Any) -> list[dict]:
    items = _as_list(raw)
    out: list[dict] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append(
                {
                    "area": "Copy",
                    "current": "",
                    "suggested": item.strip()[:280],
                    "why": "Clearer messaging for visitors.",
                }
            )
        elif isinstance(item, dict):
            suggested = str(item.get("suggested") or item.get("copy") or "").strip()
            if not suggested:
                continue
            out.append(
                {
                    "area": str(item.get("area") or item.get("section") or "Copy")[:80],
                    "current": str(item.get("current") or "")[:180],
                    "suggested": suggested[:320],
                    "why": str(item.get("why") or "")[:200],
                }
            )
        if len(out) >= 8:
            break
    return out


def _pack_mentions_about(pack: dict) -> bool:
    story = pack.get("site_story") or {}
    if story.get("about_present"):
        return True
    for page in story.get("pages") or []:
        url = str(page.get("url") or "").lower()
        if "about" in url or "our-story" in url or "who-we-are" in url:
            return True
    for page in ((pack.get("pages") or {}).get("pages") or []):
        url = str(page.get("url") or "").lower()
        if "about" in url or "our-story" in url or "who-we-are" in url:
            return True
    seo = pack.get("seo") or {}
    for loc in seo.get("sample_urls") or []:
        if "about" in str(loc).lower():
            return True
    for entry in seo.get("sitemaps") or []:
        parsed = (entry or {}).get("parsed") or {}
        for loc in (parsed.get("urls") or parsed.get("sample_urls") or []):
            if "about" in str(loc).lower():
                return True
    return False


def _infer_business_type(name: str, value: list, headlines: list) -> str:
    blob = " ".join(
        [name or ""] + [str(v) for v in value[:2]] + [str(h) for h in headlines[:3]]
    ).lower()
    if any(w in blob for w in ("video", "broadcast", "streaming", "film", "production")):
        return "Video production / broadcast agency"
    if any(w in blob for w in ("solar", "photovoltaic", "pv ")):
        return "Solar energy company"
    if any(w in blob for w in ("dentist", "dental", "clinic", "medical")):
        return "Local healthcare practice"
    if any(w in blob for w in ("lawyer", "attorney", "legal", "law firm")):
        return "Law firm"
    if any(w in blob for w in ("restaurant", "cafe", "bistro", "catering")):
        return "Hospitality business"
    if name and name.lower() not in {"unknown", "home", "welcome"}:
        return name
    return "Local business"


def _infer_audience(value: list, headlines: list) -> str:
    blob = " ".join([str(v) for v in value[:2]] + [str(h) for h in headlines[:3]]).lower()
    if any(w in blob for w in ("corporate", "enterprise", "b2b", "broadcast")):
        return "Corporate and broadcast clients"
    if any(w in blob for w in ("homeowner", "home owner", "residential")):
        return "Homeowners"
    if any(w in blob for w in ("wedding", "event")):
        return "Event organizers and private clients"
    if any(w in blob for w in ("malta", "gozo", "local")):
        return "Local customers in their service area"
    return "People searching for their services"


def _fallback_site_story_summary(pack: dict, profile: dict | None = None) -> dict:
    if profile and isinstance(profile.get("story_for_brain"), dict):
        story = dict(profile["story_for_brain"])
        # Ensure required keys exist
        return {
            "business_type": str(story.get("business_type") or "").strip(),
            "audience": str(story.get("audience") or "").strip(),
            "story": str(story.get("story") or "").strip(),
            "offer": str(story.get("offer") or "").strip(),
            "tone": str(story.get("tone") or "professional").strip(),
            "gaps": [str(x) for x in (story.get("gaps") or [])[:6]],
        }

    story = pack.get("site_story") or {}
    domain = (pack.get("website") or {}).get("domain") or "the website"
    name = story.get("likely_business_name") or domain
    headlines = story.get("headlines") or []
    value = story.get("value_prop_candidates") or []
    pages = story.get("pages") or []
    excerpts = [p.get("body_excerpt") for p in pages if p.get("body_excerpt")]

    gaps = []
    if not _pack_mentions_about(pack):
        gaps.append("No dedicated About page found in the crawl sample.")
    rich_excerpt = max((len(e or "") for e in excerpts), default=0)
    if (not excerpts or rich_excerpt < 120) and not value:
        gaps.append("Very little on-page copy to infer a clear brand story.")
    if not value and not headlines:
        gaps.append("Missing or weak meta descriptions for messaging.")

    story_text = ""
    if value:
        story_text = value[0]
    elif headlines:
        story_text = (
            f"{name} presents itself around: "
            + "; ".join(headlines[:3])
            + "."
        )
    elif excerpts:
        story_text = excerpts[0][:280]
    else:
        story_text = (
            f"Insufficient public copy was captured to describe {name}'s story."
        )

    offer = headlines[0] if headlines else (value[0][:80] if value else name)

    return {
        "business_type": _infer_business_type(name, value, headlines),
        "audience": _infer_audience(value, headlines),
        "story": story_text,
        "offer": offer,
        "tone": "professional" if value or headlines else "unclear",
        "gaps": gaps
        or [
            "Story signals are thin — lean on conversion gaps, performance, and opportunities for the plan."
        ],
    }


def _merge_recommendations(baseline: dict, ollama: dict) -> dict:
    """Fill gaps when the local model returns empty or thin JSON."""
    merged = dict(baseline)
    thin_story = {
        "",
        "unknown",
        "unknown — inferred only from limited crawl copy",
        "not clearly stated",
        "not clearly stated in captured pages",
        "unclear",
    }

    for key, value in (ollama or {}).items():
        if key == "site_story_summary" and isinstance(value, dict):
            base_story = dict(baseline.get("site_story_summary") or {})
            for field, val in value.items():
                text = str(val or "").strip()
                if not text or text.lower() in thin_story:
                    continue
                base_story[field] = val
            merged[key] = base_story
        elif isinstance(value, list):
            if value:
                merged[key] = value
        elif isinstance(value, str):
            if value.strip():
                merged[key] = value.strip()
        elif value:
            merged[key] = value
    return merged


def _client_action_from_finding(f: dict) -> dict | None:
    """Map a raw finding to client-facing language; skip pure scanner jargon."""
    code = str(f.get("code") or "").lower()
    cat = str(f.get("category") or "technical").lower()
    title = str(f.get("title") or "")
    if _is_jargon_action({"title": title, "why": f.get("description") or "", "how": code}):
        # Rewrite known themes instead of dropping high-impact issues.
        theme_map = {
            "a11y_color-contrast": (
                "Make text and buttons easier to read",
                "accessibility",
                "Low contrast slows reading and weakens trust on key pages.",
                "Raise contrast on body text and primary CTAs to meet readable AA levels.",
            ),
            "color-contrast": (
                "Make text and buttons easier to read",
                "accessibility",
                "Low contrast slows reading and weakens trust on key pages.",
                "Raise contrast on body text and primary CTAs to meet readable AA levels.",
            ),
            "very_large_page_weight": (
                "Make key pages load lighter and faster",
                "performance",
                "Heavy pages hurt first impression and mobile enquiry rates.",
                "Compress hero media, defer non-critical scripts, and trim transfer size on home/services.",
            ),
            "siteone_security": (
                "Strengthen security and visitor trust signals",
                "security",
                "Security warnings and weak HTTPS posture reduce credibility.",
                "Fix critical security findings and surface clear trust cues on contact paths.",
            ),
        }
        mapped = None
        for key, values in theme_map.items():
            if key in code or key.replace("_", "-") in title.lower():
                mapped = values
                break
        if not mapped and cat == "accessibility":
            mapped = (
                "Improve accessibility and readability across the website",
                "accessibility",
                "Hard-to-use pages exclude visitors and create compliance risk.",
                "Fix landmark structure, contrast, and form labels on high-traffic templates.",
            )
        if not mapped:
            return None
        t, category, why, how = mapped
        severity = f.get("severity") or "medium"
        return {
            "title": t,
            "category": category,
            "impact": "high" if severity == "high" else "medium",
            "effort": "medium",
            "why": why,
            "how": how,
            "opportunity_theme": "",
        }

    severity = f.get("severity") or "medium"
    impact = {"high": "high", "medium": "medium", "low": "low", "info": "low"}.get(
        severity, "medium"
    )
    return {
        "title": title or "Improve site quality",
        "category": cat or "technical",
        "impact": impact,
        "effort": "low" if severity in {"low", "info"} else "medium",
        "why": str(f.get("description") or "")[:280],
        "how": "Implement the recommended fix on the affected templates, then re-verify.",
        "opportunity_theme": "",
    }


# Categories that are "already good" above this score should not lead the plan.
_STRONG_SCORE = 8.5

# Map opportunity theme / action category → scoreboard key.
_THEME_SCORE_KEYS = {
    "performance": "performance",
    "accessibility": "accessibility",
    "security": "security",
    "seo": "seo",
    "seo_basics": "seo",
    "technical": "technical",
    "stack": "technical",
    "best-practices": "technical",
    "best_practices": "technical",
}

# Commercial themes are never skipped for a high score — they drive revenue.
_ALWAYS_KEEP_THEMES = {
    "conversion",
    "content",
    "ux",
    "messaging",
    "trust",
}


def _category_score(scores: dict | None, theme_or_category: str) -> float | None:
    """Return the numeric score for a theme/category, or None if unknown."""
    by = (scores or {}).get("by_category") or {}
    key = _THEME_SCORE_KEYS.get((theme_or_category or "").lower())
    if not key:
        return None
    val = by.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _is_strong_category(scores: dict | None, theme_or_category: str) -> bool:
    theme = (theme_or_category or "").lower()
    if theme in _ALWAYS_KEEP_THEMES:
        return False
    score = _category_score(scores, theme)
    return score is not None and score >= _STRONG_SCORE


def _actions_from_opportunities(
    opportunities: list | None,
    *,
    scores: dict | None = None,
) -> list[dict]:
    """Turn opportunities into actions, demoting themes the site already scores well on."""
    kept: list[dict] = []
    demoted: list[dict] = []
    seen: set[str] = set()
    for o in opportunities or []:
        if (o.get("status") or "").lower() == "rejected":
            continue
        title = o.get("client_title") or o.get("title")
        if not title or title in seen:
            continue
        seen.add(title)
        theme = str(o.get("theme_key") or o.get("category") or "content")
        pri = o.get("priority")
        if isinstance(pri, str):
            impact = "high" if pri.lower() in {"high", "1", "2", "p1", "p2"} else "medium"
        elif isinstance(pri, (int, float)):
            impact = "high" if pri <= 2 else "medium"
        else:
            impact = "high"
        action = {
            "title": str(title),
            "category": str(o.get("category") or theme or "content"),
            "impact": impact,
            "effort": "medium",
            "why": str(o.get("business_impact") or o.get("problem") or "")[:280],
            "how": str(o.get("recommendation") or "")[:280],
            "opportunity_theme": str(o.get("theme_key") or ""),
        }
        if _is_strong_category(scores, theme) or _is_strong_category(
            scores, action["category"]
        ):
            # Keep as a low-priority note only if we later need filler.
            action["impact"] = "low"
            demoted.append(action)
        else:
            kept.append(action)
        if len(kept) >= 8:
            break
    # Prefer real gaps; only append demoted items when the plan is thin.
    out = kept
    if len(out) < 4:
        for item in demoted:
            if len(out) >= 6:
                break
            out.append(item)
    return out[:8]


def _story_led_actions(
    pack: dict,
    profile: dict | None,
    *,
    brand: str,
) -> list[dict]:
    """Commercial actions grounded in company profile / site story — not scanner themes."""
    actions: list[dict] = []
    services = list((profile or {}).get("services") or [])
    use_cases = list((profile or {}).get("use_cases") or [])
    proof = list((profile or {}).get("proof_points") or [])
    location = (profile or {}).get("location") or ""
    cta = (profile or {}).get("primary_cta") or ""
    pack_story = pack.get("site_story") or {}
    home_title = ""
    pages = pack_story.get("pages") or []
    if pages:
        home_title = str(pages[0].get("title") or "")
        h1 = pages[0].get("h1") or []
        if isinstance(h1, list) and h1:
            home_title = home_title or str(h1[0])
    current_ctas = [str(c) for c in (pack_story.get("calls_to_action") or [])[:4]]
    weak_cta = not cta or cta.lower() in {
        "contact",
        "learn more",
        "get started",
        "read more",
        "click here",
    }
    if current_ctas and all(
        c.lower() in {"contact", "learn more", "get started", "read more"}
        for c in current_ctas
    ):
        weak_cta = True

    if _looks_seo_title(home_title) or not home_title:
        actions.append(
            {
                "title": "Lead with a benefit promise, not the SEO page title",
                "category": "content",
                "impact": "high",
                "effort": "low",
                "why": (
                    f"First-time buyers for {brand} decide in seconds whether this is "
                    "the right fit — browser titles do not sell."
                ),
                "how": (
                    "Replace SEO-title heroes with a benefit-led H1 plus one primary CTA "
                    f"({cta or 'Start a project'})."
                ),
                "opportunity_theme": "messaging",
            }
        )

    if services:
        sample = ", ".join(services[:4])
        actions.append(
            {
                "title": "Make services scannable as buyer jobs",
                "category": "ux",
                "impact": "high",
                "effort": "medium",
                "why": (
                    f"Prospects hire {brand} for concrete jobs"
                    + (f" in {location}" if location else "")
                    + " — not dense paragraphs."
                ),
                "how": f"Feature cards for: {sample}. Each card: who it is for + deep link.",
                "opportunity_theme": "conversion",
            }
        )
    elif use_cases:
        sample = ", ".join(use_cases[:3])
        actions.append(
            {
                "title": "Show the jobs clients hire you for",
                "category": "content",
                "impact": "high",
                "effort": "medium",
                "why": f"Buyers recognise their project faster when use cases are explicit ({sample}).",
                "how": "Add a use-case strip or cards near the hero with a path to enquire.",
                "opportunity_theme": "content",
            }
        )

    if weak_cta:
        actions.append(
            {
                "title": "Replace vague Contact CTAs with a specific next step",
                "category": "ux",
                "impact": "high",
                "effort": "low",
                "why": "Specific CTAs convert; Contact / Learn more alone do not.",
                "how": f"Use one primary CTA — {cta or 'Start a project'} — above the fold and in the sticky nav.",
                "opportunity_theme": "conversion",
            }
        )

    if proof:
        actions.append(
            {
                "title": "Put proof next to the offer",
                "category": "ux",
                "impact": "medium",
                "effort": "low",
                "why": "Trust signals close the gap between interest and enquiry.",
                "how": (
                    "Surface proof near the hero: "
                    + ", ".join(str(p) for p in proof[:3])
                    + "."
                ),
                "opportunity_theme": "trust",
            }
        )

    return actions[:6]


def _merge_action_lists(*lists: list[dict], limit: int = 8) -> list[dict]:
    """Merge action lists, preferring earlier entries. Deduplicate by title only.

    Scanner themes (performance/a11y/…) are capped to one entry so story-led
    commercial actions are not crowded out by repeated remediation themes.
    """
    out: list[dict] = []
    seen_titles: set[str] = set()
    seen_scanner_themes: set[str] = set()
    scanner_themes = set(_THEME_SCORE_KEYS) | {"technical"}
    for group in lists:
        for item in group or []:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            key = title.lower()
            if key in seen_titles:
                continue
            theme = str(item.get("opportunity_theme") or item.get("category") or "").lower()
            if theme in scanner_themes:
                if theme in seen_scanner_themes:
                    continue
                seen_scanner_themes.add(theme)
            seen_titles.add(key)
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def _filter_strong_score_actions(recommendations: dict, scores: dict) -> dict:
    """Drop or demote remediation actions for categories that already score well."""
    actions = list(recommendations.get("priority_actions") or [])
    if not actions:
        return recommendations
    kept: list[dict] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        theme = str(item.get("opportunity_theme") or item.get("category") or "")
        if _is_strong_category(scores, theme):
            # Keep only if the plan would otherwise be empty of commercial items.
            continue
        kept.append(item)
    if len(kept) < 3:
        # Fall back to original order but force strong-score items to low impact.
        kept = []
        for item in actions:
            if not isinstance(item, dict):
                continue
            theme = str(item.get("opportunity_theme") or item.get("category") or "")
            row = dict(item)
            if _is_strong_category(scores, theme):
                row["impact"] = "low"
            kept.append(row)
    out = dict(recommendations)
    out["priority_actions"] = kept[:8]
    # Quick wins should not lead with demoted scanner themes.
    quick = [
        q
        for q in (out.get("quick_wins") or [])
        if not any(
            str(q).strip().lower() == str(a.get("title") or "").strip().lower()
            and _is_strong_category(
                scores, str(a.get("opportunity_theme") or a.get("category") or "")
            )
            for a in actions
            if isinstance(a, dict)
        )
    ]
    if quick:
        out["quick_wins"] = quick[:6]
    return out


def _commercial_executive_summary(
    *,
    brand: str,
    domain: str,
    site_story_summary: dict,
    profile: dict | None,
    overall: Any,
    weak: list[tuple[str, Any]],
    target: float | None,
) -> str:
    """Pitch-shaped summary for profile-first Brain (not a score dump)."""
    story = (site_story_summary.get("story") or "").strip()
    offer = (site_story_summary.get("offer") or "").strip()
    services = (profile or {}).get("services") or []
    location = (profile or {}).get("location") or ""
    usecase = (profile or {}).get("usecase_summary") or ""
    weak_real = [(c, s) for c, s in weak if isinstance(s, (int, float)) and s < _STRONG_SCORE]
    weak_bit = ", ".join(f"{c} {s}/10" for c, s in weak_real[:2])

    if profile and (story or services):
        parts = [
            f"{brand} already has a clear offer"
            + (f" ({', '.join(services[:3])})" if services else (f" ({offer})" if offer else ""))
            + (f" for {location}" if location else "")
            + "."
        ]
        if usecase:
            parts.append(usecase if usecase.endswith(".") else usecase + ".")
        elif story:
            parts.append(story if story.endswith(".") else story + ".")
        parts.append(
            "The commercial gap is first-screen clarity: who they hire for, "
            "what form of work fits, and one decisive CTA."
        )
        if weak_bit and overall is not None:
            parts.append(
                f"Keep the craft; tighten messaging and close the {weak_bit} gap"
                + (f" to beat {overall}/10" if overall is not None else "")
                + (f" toward {target}/10." if target is not None else ".")
            )
        else:
            parts.append(
                "Pitch a Growth engagement that tightens hero messaging, service cards, "
                "and enquiry conversion — not a scanner-led rebuild."
            )
        return " ".join(parts)

    # Thin-profile fallback
    return (
        f"{brand} ({domain}): {story or 'Limited story captured from the crawl.'} "
        + (f"Weaker areas: {weak_bit}. " if weak_bit else "")
        + "Prioritise conversion messaging and the weakest score categories."
    )


def rule_based_recommendations(
    pack: dict,
    *,
    opportunities: list | None = None,
    profile: dict | None = None,
) -> dict:
    """Deterministic baseline — company-profile + opportunity-led, client-facing."""
    findings = (pack.get("findings") or {}).get("top") or []
    scores = pack.get("scores") or {}
    overall = scores.get("overall")
    by_cat = scores.get("by_category") or {}
    website = pack.get("website") or {}
    domain = website.get("domain") or "the website"
    site_story_summary = _fallback_site_story_summary(pack, profile=profile)
    conv = pack.get("conversion_path") or {}
    perf_pages = (pack.get("performance") or {}).get("pages") or []
    brand = (
        ((profile or {}).get("brand") or {}).get("display_name")
        or (pack.get("site_story") or {}).get("likely_business_name")
        or domain
    )

    story_actions = _story_led_actions(pack, profile, brand=brand)
    opp_actions = _actions_from_opportunities(opportunities, scores=scores)

    finding_actions: list[dict] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        mapped = _client_action_from_finding(f)
        if not mapped:
            continue
        if _is_strong_category(scores, mapped.get("category") or ""):
            continue
        finding_actions.append(mapped)

    # Score / evidence driven actions when still thin
    evidence_actions: list[dict] = []
    heavy = [
        p
        for p in perf_pages
        if isinstance(p, dict)
        and isinstance(p.get("total_transfer_bytes"), (int, float))
        and p["total_transfer_bytes"] > 2_500_000
    ]
    # Only pitch performance when the scoreboard agrees it is weak, or pages are very heavy.
    perf_score = _category_score(scores, "performance")
    if heavy and (perf_score is None or perf_score < _STRONG_SCORE):
        evidence_actions.append(
            {
                "title": "Make key pages load lighter and faster",
                "category": "performance",
                "impact": "high",
                "effort": "medium",
                "why": (
                    f"Home/services transfer ~{heavy[0]['total_transfer_bytes'] / 1_000_000:.1f} MB "
                    "— slows first impression."
                ),
                "how": "Compress hero media, lazy-load below-fold assets, and cut unused scripts.",
                "opportunity_theme": "performance",
            }
        )
    for gap in (conv.get("gaps") or [])[:3]:
        title = str(gap).strip()
        if title:
            evidence_actions.append(
                {
                    "title": title[:120],
                    "category": "ux",
                    "impact": "high",
                    "effort": "medium",
                    "why": "Conversion path gaps leave money on the table.",
                    "how": "Clarify the next step on homepage and service pages.",
                    "opportunity_theme": "conversion",
                }
            )

    # Story/commercial first, then real score gaps from opportunities, then findings.
    actions = _merge_action_lists(
        story_actions, opp_actions, evidence_actions, finding_actions, limit=8
    )

    quick = []
    for a in actions:
        if a.get("effort") == "low" or a.get("impact") == "high":
            quick.append(a["title"])
        if len(quick) >= 5:
            break
    for f in findings:
        code = f.get("code") or ""
        if code in {
            "missing_meta_description",
            "missing_title",
            "missing_h1",
            "images_missing_alt",
            "thin_content",
        }:
            cat = str(f.get("category") or "seo")
            if _is_strong_category(scores, cat):
                continue
            t = f.get("title") or code
            if t not in quick and not _JARGON_RE.search(str(t)):
                quick.append(t)
        if len(quick) >= 6:
            break

    weak = sorted(
        (
            (c, s)
            for c, s in by_cat.items()
            if isinstance(s, (int, float)) and s < _STRONG_SCORE
        ),
        key=lambda kv: kv[1],
    )[:3]
    # If everything is strong, still surface the relative weakest for strategy.
    if not weak and by_cat:
        weak = sorted(
            ((c, s) for c, s in by_cat.items() if isinstance(s, (int, float))),
            key=lambda kv: kv[1],
        )[:2]
    target = (
        min(10.0, round(float(overall) + 0.8, 1))
        if isinstance(overall, (int, float))
        else None
    )
    strategic = [
        "Clarify homepage story: who you serve, what you offer, and why to act now.",
        "Rebuild the hero around a benefit-led promise (not the SEO page title).",
    ]
    for cat, score in weak:
        if isinstance(score, (int, float)) and score >= _STRONG_SCORE:
            continue
        if target is not None:
            strategic.append(
                f"Lift {cat} from {score}/10 toward the {target}/10 overall target with a focused sprint."
            )
        else:
            strategic.append(
                f"Raise {cat} (currently {score}/10) with a focused improvement sprint."
            )
    strategic = strategic[:6]

    name = brand
    services = (profile or {}).get("services") or []
    use_cases = (profile or {}).get("use_cases") or []
    summary = _commercial_executive_summary(
        brand=name,
        domain=domain,
        site_story_summary=site_story_summary,
        profile=profile,
        overall=overall,
        weak=weak,
        target=target,
    )

    content_suggestions = _rule_content_suggestions(
        pack, site_story_summary, name, profile=profile
    )

    from backend.app.services.content_metadata import decide_content_metadata
    from backend.app.services.design_direction import decide_design_direction
    from backend.app.services.social_content import decide_social_content

    design_direction = decide_design_direction(pack, profile)
    content_metadata = decide_content_metadata(
        pack,
        profile,
        content_suggestions=content_suggestions,
        design_direction=design_direction,
    )
    social_content = decide_social_content(
        pack,
        profile,
        design_direction=design_direction,
        content_metadata=content_metadata,
    )

    service_bit = ", ".join(services[:3]) if services else "core offers"
    use_bit = ", ".join(use_cases[:2]) if use_cases else "priority use cases"
    proposal_angles = [
        (
            f"Growth package for {name}: messaging + conversion path so buyers recognise "
            f"{service_bit} and enquire faster"
            + (f" (e.g. {use_bit})." if use_cases else ".")
        ),
        (
            f"Fixed-scope engagement: hero rewrite, service cards, proof, and CTA — "
            f"aimed above {overall}/10."
            if overall is not None
            else f"Fixed-scope engagement: hero rewrite, service cards, proof, and CTA for {name}."
        ),
    ]
    if weak:
        weak_names = ", ".join(c for c, _ in weak[:2])
        proposal_angles.append(
            f"Optional remediation sprint on weaker areas ({weak_names}) after the conversion pass."
        )
    else:
        proposal_angles.append(
            f"Optional Redesign: cinematic homepage grounded in {name}'s real offers."
        )

    theme_label = design_direction.get("theme_label") or design_direction.get("theme")
    mockup_style = design_direction.get("style_notes") or "premium brand aesthetic"
    return {
        "site_story_summary": site_story_summary,
        "executive_summary": summary.strip(),
        "priority_actions": actions[:8],
        "quick_wins": quick
        or ["Clarify the homepage offer in one screen", "Add a single primary CTA"],
        "strategic_improvements": strategic,
        "proposal_angles": proposal_angles[:4],
        "content_suggestions": content_suggestions,
        "design_direction": design_direction,
        "content_metadata": content_metadata,
        "social_content": social_content,
        "mockup_prompts": [
            (
                f"{theme_label} homepage for {name}, {design_direction.get('hero_variant')} hero, "
                f"benefit-led headline, clear CTA — {mockup_style[:80]}"
            ),
            f"Mobile homepage for {name} with readable contrast and primary enquiry CTA above the fold",
        ],
        "company_profile": {
            "brand": ((profile or {}).get("brand") or {}).get("display_name"),
            "industry": (profile or {}).get("industry_label"),
            "services": services[:6],
            "use_cases": ((profile or {}).get("use_cases") or [])[:6],
            "location": (profile or {}).get("location"),
        }
        if profile
        else None,
    }


def _looks_seo_title(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "|" in t or " – " in t:
        return True
    low = t.lower()
    if low in {"home", "homepage", "welcome"}:
        return True
    return False


def _benefit_headline_for_pack(pack: dict, brand: str, offer_bits: list[str], value: str) -> str:
    narrative = (value or "").lower()
    if any(k in narrative for k in ("broadcast", "stream", "film", "video", "camera")):
        return "Broadcast-ready production — clearer offer, stronger first call."
    if offer_bits:
        first = offer_bits[0][:1].upper() + offer_bits[0][1:]
        return f"{first} — clearer story, stronger first impression"
    return f"{brand} — clearer story, stronger first impression"


def _rule_content_suggestions(
    pack: dict,
    story: dict,
    name: str,
    *,
    profile: dict | None = None,
) -> list[dict]:
    from backend.app.services.site_design import short_brand_name

    pack_story = pack.get("site_story") or {}
    domain = ((pack.get("website") or {}).get("domain")) or ""
    brand = (
        ((profile or {}).get("brand") or {}).get("display_name")
        or short_brand_name(name, domain)
    )
    current_title = ""
    pages = pack_story.get("pages") or []
    if pages:
        current_title = (pages[0].get("title") or pages[0].get("h1") or [""])
        if isinstance(current_title, list):
            current_title = current_title[0] if current_title else ""
    value = (
        (profile or {}).get("one_liner")
        or (pack_story.get("value_prop_candidates") or [None])[0]
        or story.get("story")
        or ""
    )
    services = (profile or {}).get("services") or []
    offer_bits = services or _split_offers(value)
    location = (
        (profile or {}).get("location")
        or (
            "Malta & Gozo"
            if "malta" in value.lower() or "gozo" in value.lower()
            else "your market"
        )
    )
    cta = (profile or {}).get("primary_cta") or "Start a project"
    headline = _benefit_headline_for_pack(pack, brand, offer_bits, value)
    if (profile or {}).get("industry") == "video_production_broadcast":
        # Voice inspired by EVP + OB studio sites (outcome first, not SEO title).
        headline = "Stories worth watching — broadcast-ready from brief to screen."

    # Performance-aware why lines when pages are heavy
    heavy = False
    for p in (pack.get("performance") or {}).get("pages") or []:
        if isinstance(p, dict) and isinstance(p.get("total_transfer_bytes"), (int, float)):
            if p["total_transfer_bytes"] > 2_500_000:
                heavy = True
                break

    suggestions = [
        {
            "area": "Hero headline",
            "current": str(current_title)[:120],
            "suggested": headline,
            "why": "Lead with a cinematic promise, not a browser/SEO title.",
        },
        {
            "area": "Hero subcopy",
            "current": str(value)[:160],
            "suggested": (
                f"Outside broadcast, live streaming, corporate film, and commercials — "
                f"one crew across {location}."
                if (profile or {}).get("industry") == "video_production_broadcast"
                else (
                    f"{', '.join(str(b)[:1].upper() + str(b)[1:] for b in offer_bits[:3])} "
                    f"— clear next step for buyers in {location}."
                    if offer_bits
                    else f"One clear sentence on who {brand} helps and what happens next."
                )
            ),
            "why": "Name the forms of work buyers hire for (studio-site pattern).",
        },
        {
            "area": "Primary CTA",
            "current": ((pack_story.get("calls_to_action") or [None])[0] or "Missing / weak"),
            "suggested": cta if cta.lower() not in {"contact", "learn more", "get started"} else "Start a project",
            "why": "Specific CTAs convert; Learn more / Contact alone do not.",
        },
        {
            "area": "Services section",
            "current": ", ".join(offer_bits[:4]) if offer_bits else "Not clearly listed",
            "suggested": (
                "Feature cards: "
                + ", ".join(str(b)[:1].upper() + str(b)[1:] for b in offer_bits[:4])
                + ("." if offer_bits else "Three outcome-led service lines.")
            ),
            "why": "Scannable services beat a dense paragraph.",
        },
        {
            "area": "About blurb",
            "current": "",
            "suggested": (
                (profile or {}).get("one_liner")
                or (
                    f"{brand} is a technology & visual agency for outside broadcast, "
                    f"live streaming, corporate film, and commercials."
                    if offer_bits
                    else f"Two sentences: who {brand} is, who you serve, and proof."
                )
            ),
            "why": "Trust rises when the story is explicit on-page.",
        },
    ]
    if heavy:
        suggestions.append(
            {
                "area": "Hero media",
                "current": "Very large page transfer on home/services",
                "suggested": "Compressed hero still + optional short reel; defer heavy video until interaction.",
                "why": "Lighter media raises performance score and mobile conversion.",
            }
        )
    else:
        suggestions.append(
            {
                "area": "Search title",
                "current": str(current_title)[:120],
                "suggested": f"{brand} — {_title_case_bits(offer_bits)}",
                "why": "Keep SEO titles for search; keep the on-page H1 benefit-led.",
            }
        )
    return suggestions


def _title_case_bits(bits: list[str]) -> str:
    if not bits:
        return "Clear offer, stronger first impression"
    return ", ".join(b[:1].upper() + b[1:] for b in bits[:3])


def _split_offers(text: str) -> list[str]:
    raw = (text or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    raw = raw.replace(" & ", ", ").replace(" and ", ", ")
    parts = []
    for chunk in raw.split(","):
        item = chunk.strip(" .;")
        lower = item.lower()
        if " in malta" in lower or lower.startswith("in "):
            continue
        if len(item) < 4:
            continue
        parts.append(item)
    return parts[:6]


class OllamaError(RuntimeError):
    """Backward-compatible alias for LLM failures."""


def ollama_available(
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    timeout: float = 3.0,
) -> dict:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [m.get("name") for m in data.get("models") or []]
            return {"ok": True, "models": models, "base_url": base_url}
    except Exception as exc:
        return {
            "ok": False,
            "models": [],
            "base_url": base_url,
            "error": str(exc),
        }


def generate_with_ollama(
    pack: dict,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """Legacy helper — prefers the configured brain provider via llm_client."""
    return generate_with_llm(pack, model=model, provider="ollama")


def _ollama_model_on_gpu(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> bool | None:
    """Return True if a loaded model reports VRAM, False if CPU-only, None unknown."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/ps")
            resp.raise_for_status()
            models = resp.json().get("models") or []
            if not models:
                return None
            # Any loaded model with VRAM counts as GPU-backed.
            return any(int(m.get("size_vram") or 0) > 0 for m in models if isinstance(m, dict))
    except Exception:
        return None


def _prefer_fast_brain_model(
    configured: str | None,
    *,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    prefer_fast: bool = True,
) -> str | None:
    """Pick a small local model when 7B is CPU-bound (common laptop case)."""
    if not prefer_fast:
        return configured
    on_gpu = _ollama_model_on_gpu(base_url)
    # If clearly on GPU, keep the configured (usually 7b) model.
    if on_gpu is True:
        return configured
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            names = [m.get("name") for m in (resp.json().get("models") or [])]
    except Exception:
        return configured

    for candidate in ("llama3.2:3b", "qwen2.5:3b", "phi3:mini", "llama3.2"):
        if candidate in names or any((n or "").startswith(candidate.split(":")[0]) for n in names):
            # Prefer exact tag when present
            if candidate in names:
                return candidate
            for n in names:
                if (n or "").startswith(candidate.split(":")[0]):
                    return n
    return configured


def _llm_json_step(
    *,
    system: str,
    user: str,
    provider: str,
    model: str | None,
    timeout: float,
    max_tokens: int = 700,
) -> dict:
    from backend.app.services.llm_client import LLMError, chat_json

    try:
        parsed, provider_used, model_used = chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            provider=provider,
            model=model,
            temperature=0.25,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    except LLMError as exc:
        raise OllamaError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise OllamaError("Model returned non-object JSON")
    parsed["_provider"] = provider_used
    parsed["_model"] = model_used
    return parsed


def generate_with_llm(
    pack: dict,
    *,
    model: str | None = None,
    provider: str | None = None,
    opportunities: list | None = None,
    sell_recommendation: dict | None = None,
    agency: dict | None = None,
    root: Path | None = None,
    timeout: float | None = None,
) -> dict:
    """Multi-step Brain: story → priorities → copy, then merge.

    Small local models (7B on CPU) fail a single mega-JSON request. Staging
    the work makes the same model meaningfully smarter.
    """
    from backend.app.services.agent_context import build_agent_context, shrink_for_brain
    from backend.app.services.agent_prompts import brain_system_prompt
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.llm_client import resolve_provider

    agency = agency or load_agency_settings()
    agent_cfg = agency.get("agent") or {}
    active = resolve_provider(provider)

    ctx = build_agent_context(
        evidence_pack=pack,
        opportunities=opportunities,
        sell_recommendation=sell_recommendation,
        agency=agency,
        root=root,
        include_few_shot=True,
    )
    compact = shrink_for_brain(ctx, pack)
    profile_for_baseline = None
    if root is not None:
        try:
            from backend.app.services.company_profile import ensure_company_profile

            profile_for_baseline = ensure_company_profile(root, pack)
        except Exception:
            profile_for_baseline = None
    baseline = rule_based_recommendations(
        pack, opportunities=opportunities, profile=profile_for_baseline
    )
    training_block = ctx.get("agency_examples") or ""

    brain_model = model
    if active == "ollama":
        prefer_fast = bool(agent_cfg.get("prefer_fast_brain_model", False))
        if prefer_fast:
            brain_model = _prefer_fast_brain_model(model, prefer_fast=True)
        if timeout is None:
            # Per-step budget; three steps ≈ still interactive on CPU 7B.
            timeout = float(agent_cfg.get("brain_timeout_seconds") or 90)
        if prefer_fast and _ollama_model_on_gpu() is False:
            raise OllamaError(
                "Local model is running on CPU (no GPU VRAM). "
                "Using the full-evidence baseline for speed. "
                "Add Anthropic/OpenAI credits, or run Ollama on GPU."
            )
    elif timeout is None:
        timeout = 90.0

    system = brain_system_prompt(agency)
    if training_block:
        system = (
            system
            + "\n\n### Agency training examples (imitate voice; adapt to THIS client)\n"
            + training_block
        )
    score_gaps = compact.get("score_gaps") or {}
    target = score_gaps.get("target_overall")
    slim = {
        "website": compact.get("website"),
        "scores": compact.get("scores"),
        "score_gaps": score_gaps,
        "company_profile": compact.get("company_profile") or ctx.get("company_profile"),
        "site_story": compact.get("site_story"),
        "opportunities": compact.get("opportunities"),
        "sell_recommendation": compact.get("sell_recommendation"),
        "performance": compact.get("performance"),
        "accessibility": compact.get("accessibility"),
        "seo_signals": compact.get("seo_signals"),
        "conversion_path": compact.get("conversion_path"),
        "ssl": compact.get("ssl"),
        "findings_top": compact.get("findings_top"),
    }
    context_json = json.dumps(slim, ensure_ascii=True)

    # --- Pass 1: understand the business + design direction + metadata ---
    story_pass = _llm_json_step(
        system=system
        + "\nThis turn: ONLY return site_story_summary, executive_summary,"
        " design_direction, and content_metadata."
        " Match the training-example pitch voice (commercial, not scanner dump)."
        " design_direction.theme MUST be one of: dark_cinematic, warm_romance,"
        " light_editorial, clean_corporate, warm_hospitality, bold_tech."
        " design_direction.hero_variant MUST be one of: cinematic, split, centered."
        " Pick the theme that fits THIS business (wedding ≠ broadcast ≠ clinic)."
        " content_metadata must include page_title, meta_description, primary_keywords,"
        " tone_words, avoid_words, cta_primary — specific to THIS client.",
        user=(
            "Pass 1/3 — understand the client, decide the demo look, and best words.\n"
            "Return JSON with site_story_summary, executive_summary, design_direction,"
            " content_metadata.\n"
            f"Aim the summary at beating overall {target}/10 when present.\n"
            f"Baseline design_direction (refine if wrong):\n"
            f"{json.dumps(baseline.get('design_direction') or {}, ensure_ascii=True)}\n"
            f"Baseline content_metadata (refine words if wrong):\n"
            f"{json.dumps(baseline.get('content_metadata') or {}, ensure_ascii=True)}\n"
            f"Context:\n{context_json}"
        ),
        provider=active,
        model=brain_model,
        timeout=timeout,
        max_tokens=900,
    )

    # --- Pass 2: commercial priority actions ---
    actions_pass = _llm_json_step(
        system=system
        + "\nThis turn: ONLY return priority_actions, quick_wins, strategic_improvements, "
        "proposal_angles. Client language. No axe/WCAG codes. "
        "Follow training-example action style (outcome titles, specific how).",
        user=(
            "Pass 2/3 — commercial priorities.\n"
            "Map to opportunities when present. Max 6 priority_actions.\n"
            f"Story so far: {json.dumps(story_pass.get('site_story_summary') or {}, ensure_ascii=True)}\n"
            f"Context:\n{context_json}"
        ),
        provider=active,
        model=brain_model,
        timeout=timeout,
        max_tokens=700,
    )

    # --- Pass 3: benefit-led content / redesign copy ---
    copy_pass = _llm_json_step(
        system=system
        + "\nThis turn: ONLY return content_suggestions + mockup_prompts. "
        "Hero headline must be benefit-led — never an SEO page title with | or –. "
        "Imitate training-example CTAs (Start a project / Start building — not Learn more).",
        user=(
            "Pass 3/3 — redesign copy for the live demo.\n"
            "Return 4-6 content_suggestions (Hero headline, subcopy, CTA, Services, About).\n"
            f"Business: {json.dumps(story_pass.get('site_story_summary') or {}, ensure_ascii=True)}\n"
            f"Top actions: {json.dumps((actions_pass.get('priority_actions') or [])[:4], ensure_ascii=True)}\n"
            f"Site signals: {json.dumps(slim.get('site_story') or {}, ensure_ascii=True)}"
        ),
        provider=active,
        model=brain_model,
        timeout=timeout,
        max_tokens=700,
    )

    from backend.app.services.content_metadata import decide_content_metadata
    from backend.app.services.design_direction import decide_design_direction
    from backend.app.services.social_content import decide_social_content

    llm_direction = story_pass.get("design_direction")
    design_direction = decide_design_direction(
        pack,
        profile_for_baseline,
        llm_override=llm_direction if isinstance(llm_direction, dict) else None,
    )
    llm_meta = story_pass.get("content_metadata") or copy_pass.get("content_metadata")
    content_metadata = decide_content_metadata(
        pack,
        profile_for_baseline,
        content_suggestions=copy_pass.get("content_suggestions")
        or baseline.get("content_suggestions"),
        design_direction=design_direction,
        llm_override=llm_meta if isinstance(llm_meta, dict) else None,
    )
    llm_social = story_pass.get("social_content") or copy_pass.get("social_content")
    social_content = decide_social_content(
        pack,
        profile_for_baseline,
        design_direction=design_direction,
        content_metadata=content_metadata,
        llm_override=llm_social if isinstance(llm_social, dict) else None,
    )

    merged_raw = {
        **baseline,
        "site_story_summary": story_pass.get("site_story_summary")
        or baseline.get("site_story_summary"),
        "executive_summary": story_pass.get("executive_summary")
        or baseline.get("executive_summary"),
        "design_direction": design_direction,
        "content_metadata": content_metadata,
        "social_content": social_content,
        "priority_actions": actions_pass.get("priority_actions")
        or baseline.get("priority_actions"),
        "quick_wins": actions_pass.get("quick_wins") or baseline.get("quick_wins"),
        "strategic_improvements": actions_pass.get("strategic_improvements")
        or baseline.get("strategic_improvements"),
        "proposal_angles": actions_pass.get("proposal_angles")
        or baseline.get("proposal_angles"),
        "content_suggestions": copy_pass.get("content_suggestions")
        or baseline.get("content_suggestions"),
        "mockup_prompts": copy_pass.get("mockup_prompts")
        or baseline.get("mockup_prompts"),
        "agent_next_steps": actions_pass.get("agent_next_steps")
        or [
            "Approve the top commercial opportunities",
            "Ask Design chat: Build me a homepage that implements the hero suggestion",
        ],
    }
    out = normalize_recommendations(merged_raw)
    out = _merge_recommendations(baseline, out)
    if isinstance(merged_raw.get("agent_next_steps"), list):
        out["agent_next_steps"] = [str(x) for x in merged_raw["agent_next_steps"][:6]]
    out["_provider"] = (
        story_pass.get("_provider")
        or actions_pass.get("_provider")
        or copy_pass.get("_provider")
        or active
    )
    out["_model"] = (
        story_pass.get("_model")
        or actions_pass.get("_model")
        or copy_pass.get("_model")
        or brain_model
    )
    out["_mode"] = "multi_step"
    return out


def generate_recommendations(
    pack: dict,
    *,
    model: str | None = None,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    prefer_ollama: bool = True,
    allow_fallback: bool = True,
    provider: str | None = None,
    opportunities: list | None = None,
    sell_recommendation: dict | None = None,
    agency: dict | None = None,
    root: Path | None = None,
) -> dict:
    """Generate recommendations — company profile first, LLM optional polish."""
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.company_profile import (
        build_company_profile,
        ensure_company_profile,
        write_company_profile,
    )
    from backend.app.services.llm_client import resolve_model, resolve_provider

    agency = agency or load_agency_settings()
    agent_cfg = agency.get("agent") or {}

    # Fast company intelligence from the crawl (no LLM required).
    if root is not None:
        profile = ensure_company_profile(root, pack)
    else:
        profile = build_company_profile(pack)

    source = "company_profile"
    error = None
    recommendations = None
    used_model = None
    used_provider = None

    baseline = rule_based_recommendations(
        pack, opportunities=opportunities, profile=profile
    )
    # When opportunities exist, bias proposal angles toward them
    if opportunities:
        titles = [
            o.get("client_title") or o.get("title")
            for o in opportunities
            if (o.get("status") or "").lower() not in {"rejected"}
        ][:5]
        if titles:
            baseline["proposal_angles"] = [
                f"Scope a fixed engagement around: {', '.join(t for t in titles if t)}."
            ] + list(baseline.get("proposal_angles") or [])[:3]

    active_provider = resolve_provider(provider)
    active_model = model or resolve_model(active_provider)

    llm_kwargs = dict(
        opportunities=opportunities,
        sell_recommendation=sell_recommendation,
        agency=agency,
        root=root,
    )

    # Local CPU cannot be Base44-fast and Base44-smart via 7B. Default: ship the
    # crawl-grounded company profile + commercial plan immediately. LLM polish
    # only when cloud credits exist, GPU is available, or profile_first is off.
    profile_first = bool(agent_cfg.get("profile_first_brain", True))
    on_gpu = _ollama_model_on_gpu() if active_provider == "ollama" else True
    use_llm = prefer_ollama and active_provider in {"openai", "anthropic", "ollama"}
    if profile_first and active_provider == "ollama" and on_gpu is not True:
        use_llm = False
        recommendations = baseline
        source = "company_profile"
        if root is not None:
            write_company_profile(root, profile)

    # prefer_ollama=False forces the deterministic full-evidence baseline
    # (still opportunity/score aware). Used for offline runs and tests.
    if use_llm and prefer_ollama and active_provider in {"openai", "anthropic", "ollama"}:
        try:
            recommendations = generate_with_llm(
                pack, model=active_model, provider=active_provider, **llm_kwargs
            )
            used_provider = recommendations.pop("_provider", active_provider)
            used_model = recommendations.pop("_model", active_model)
            recommendations = _merge_recommendations(baseline, recommendations)
            # If the model returned jargon-heavy actions, keep opportunity baseline.
            if not recommendations.get("priority_actions"):
                recommendations["priority_actions"] = baseline.get("priority_actions")
            source = used_provider
        except OllamaError as exc:
            error = str(exc)
            # If local Ollama is too slow / CPU-bound, prefer cloud when configured.
            cloud_tried = False
            if allow_fallback and active_provider == "ollama":
                from backend.app.database import settings as app_settings
                from backend.app.services.llm_client import cloud_provider_usable

                cloud = None
                if app_settings.anthropic_api_key and cloud_provider_usable("anthropic"):
                    cloud = "anthropic"
                elif app_settings.openai_api_key and cloud_provider_usable("openai"):
                    cloud = "openai"
                if cloud:
                    cloud_tried = True
                    try:
                        recommendations = generate_with_llm(
                            pack, model=None, provider=cloud, **llm_kwargs
                        )
                        used_provider = recommendations.pop("_provider", cloud)
                        used_model = recommendations.pop("_model", None)
                        recommendations = _merge_recommendations(
                            baseline, recommendations
                        )
                        source = f"{cloud}_fallback"
                        error = f"{error} (fell back to {cloud})"
                    except OllamaError as exc2:
                        error = f"{error}; {cloud} fallback failed: {exc2}"
                        recommendations = baseline
                        source = "rule_based_fallback"
                elif app_settings.anthropic_api_key or app_settings.openai_api_key:
                    # Key present but unusable (e.g. Anthropic no credits) —
                    # skip the failing cloud call and ship the crawl baseline.
                    recommendations = baseline
                    source = "company_profile"
                    error = None
            if allow_fallback and active_provider != "ollama" and not cloud_tried:
                try:
                    recommendations = generate_with_llm(
                        pack, model=None, provider="ollama", **llm_kwargs
                    )
                    used_provider = recommendations.pop("_provider", "ollama")
                    used_model = recommendations.pop("_model", None)
                    recommendations = _merge_recommendations(
                        baseline, recommendations
                    )
                    source = f"{used_provider}_fallback"
                    error = f"{error} (fell back to Ollama)"
                except OllamaError as exc2:
                    error = f"{error}; Ollama fallback failed: {exc2}"
                    if not allow_fallback:
                        raise
                    recommendations = baseline
                    source = "rule_based_fallback"
            elif not allow_fallback:
                raise
            elif recommendations is None:
                recommendations = baseline
                source = "rule_based_fallback"
    elif recommendations is None:
        recommendations = baseline

    # Ensure story block is always present for the UI / proposal.
    story = (recommendations or {}).get("site_story_summary") or {}
    if not (story.get("story") or story.get("business_type")):
        recommendations = {
            **recommendations,
            "site_story_summary": _fallback_site_story_summary(pack, profile=profile),
        }
    if not recommendations.get("content_suggestions"):
        recommendations["content_suggestions"] = baseline.get("content_suggestions")
    if not recommendations.get("company_profile") and baseline.get("company_profile"):
        recommendations["company_profile"] = baseline["company_profile"]
    if not recommendations.get("design_direction"):
        from backend.app.services.design_direction import decide_design_direction

        recommendations["design_direction"] = (
            baseline.get("design_direction")
            or decide_design_direction(pack, profile)
        )
    if not recommendations.get("content_metadata"):
        from backend.app.services.content_metadata import decide_content_metadata

        recommendations["content_metadata"] = (
            baseline.get("content_metadata")
            or decide_content_metadata(
                pack,
                profile,
                content_suggestions=recommendations.get("content_suggestions"),
                design_direction=recommendations.get("design_direction"),
            )
        )
    if not recommendations.get("social_content"):
        from backend.app.services.social_content import decide_social_content

        recommendations["social_content"] = (
            baseline.get("social_content")
            or decide_social_content(
                pack,
                profile,
                design_direction=recommendations.get("design_direction"),
                content_metadata=recommendations.get("content_metadata"),
            )
        )

    # Soft-train baseline / LLM merge with curated external-reference examples.
    try:
        from backend.app.services.feedback_store import enrich_recommendations_from_examples

        industry = (
            profile.get("industry")
            or profile.get("industry_label")
            or ((recommendations.get("company_profile") or {}).get("industry"))
        )
        recommendations = enrich_recommendations_from_examples(
            recommendations, industry=str(industry or "")
        )
    except Exception:
        pass

    # Even gold templates can pitch perf/a11y on already-strong scoreboards — demote them.
    recommendations = _filter_strong_score_actions(
        recommendations, pack.get("scores") or {}
    )
    # Re-attach real score-gap actions (e.g. technical 6.9) after gold commercial merge.
    if opportunities:
        gap_actions = _actions_from_opportunities(
            opportunities, scores=pack.get("scores") or {}
        )
        recommendations["priority_actions"] = _merge_action_lists(
            list(recommendations.get("priority_actions") or []),
            gap_actions,
            limit=8,
        )

    return {
        "version": 3,
        "generated_at": _now(),
        "source": source,
        "provider": used_provider or active_provider,
        "model": used_model
        if source
        not in {"rule_based", "rule_based_fallback", "company_profile"}
        else None,
        "error": error,
        "agent_mode": True,
        "opportunities_used": len(opportunities or []),
        "company_profile": {
            "brand": (profile.get("brand") or {}).get("display_name"),
            "legal_name": (profile.get("brand") or {}).get("legal_name"),
            "industry": profile.get("industry_label") or profile.get("industry"),
            "location": profile.get("location"),
            "services": profile.get("services") or [],
            "use_cases": profile.get("use_cases") or [],
            "one_liner": profile.get("one_liner"),
            "usecase_summary": profile.get("usecase_summary"),
            "primary_cta": profile.get("primary_cta"),
            "proof_points": profile.get("proof_points") or [],
        },
        "website": pack.get("website"),
        "crawl": pack.get("crawl"),
        "scores": pack.get("scores"),
        "recommendations": recommendations,
    }


def write_recommendations(root: Path, payload: dict) -> Path:
    path = root / RECOMMENDATIONS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_recommendations(root: Path) -> dict | None:
    path = root / RECOMMENDATIONS_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
