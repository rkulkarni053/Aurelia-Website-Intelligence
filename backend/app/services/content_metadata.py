"""Content & SEO metadata decisions — best words for titles, metas, CTAs.

Produced by Brain (rule-based always; LLM can refine). Consumed by design brief,
demo <head>, and design/metadata.json for the agency handoff.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METADATA_FILENAME = "design/metadata.json"

# Industry → seed keyword / voice cues (expanded from crawl services).
_INDUSTRY_SEEDS: dict[str, dict[str, Any]] = {
    "wedding_films": {
        "primary": ["wedding films", "cinematic wedding video", "wedding videographer"],
        "secondary": ["highlight film", "engagement film", "bridal story"],
        "tone": ["romantic", "cinematic", "intimate", "timeless"],
        "avoid": ["cheap", "package deal", "budget", "SEO", "best wedding videographer near me"],
        "cta": ["Enquire about your date", "Start your film", "Book a discovery call"],
        "schema": "VideoObject",
    },
    "video_production_broadcast": {
        "primary": ["video production", "live streaming", "outside broadcast"],
        "secondary": ["corporate film", "OB services", "broadcast production"],
        "tone": ["confident", "production-grade", "precise", "cinematic"],
        "avoid": ["cheap video", "viral", "content mill", "Learn more"],
        "cta": ["Start a project", "Request a quote", "Brief the crew"],
        "schema": "ProfessionalService",
    },
    "restaurant": {
        "primary": ["restaurant", "dining", "reservations"],
        "secondary": ["seasonal menu", "private dining", "chef’s table"],
        "tone": ["warm", "inviting", "crafted", "local"],
        "avoid": ["cheap eats", "fast food", "Click here"],
        "cta": ["Reserve a table", "Book tonight", "View the menu"],
        "schema": "Restaurant",
    },
    "saas": {
        "primary": ["software", "platform", "product"],
        "secondary": ["integrations", "automation", "onboarding"],
        "tone": ["clear", "confident", "modern", "helpful"],
        "avoid": ["synergy", "disrupt", "revolutionary", "Learn more"],
        "cta": ["Start free", "Book a demo", "See how it works"],
        "schema": "SoftwareApplication",
    },
    "agency": {
        "primary": ["creative agency", "brand studio", "design agency"],
        "secondary": ["branding", "digital design", "campaigns"],
        "tone": ["sharp", "editorial", "craft-led"],
        "avoid": ["full-service solutions", "synergy", "Click here"],
        "cta": ["Start a project", "Talk to the studio", "See the work"],
        "schema": "Organization",
    },
    "services": {
        "primary": ["services", "local experts"],
        "secondary": ["consultation", "support"],
        "tone": ["clear", "trustworthy", "practical"],
        "avoid": ["best in town", "Click here", "Learn more"],
        "cta": ["Get in touch", "Request a quote", "Book a call"],
        "schema": "LocalBusiness",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any, limit: int = 160) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:limit]


def _uniq(items: list[str], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _clean(item, 80).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(_clean(item, 80))
        if len(out) >= limit:
            break
    return out


_LOCATION_STOP = {"you", "our", "the", "this", "that", "your", "we", "us", "home"}


def _location_phrase(profile: dict | None, pack: dict | None) -> str:
    loc = str((profile or {}).get("location") or "").strip()
    if loc and loc.lower() not in _LOCATION_STOP and len(loc) >= 3:
        return loc
    blob = " ".join(
        str(x)
        for x in (
            ((pack or {}).get("site_story") or {}).get("value_prop_candidates") or []
        )[:2]
    ).lower()
    for place in ("malta", "gozo", "london", "dubai", "valletta", "sliema"):
        if place in blob:
            return place.title()
    return ""


def decide_content_metadata(
    pack: dict | None = None,
    profile: dict | None = None,
    *,
    content_suggestions: list | None = None,
    design_direction: dict | None = None,
    llm_override: dict | None = None,
) -> dict[str, Any]:
    """Build the best-words metadata pack for this company."""
    pack = pack or {}
    profile = profile or {}
    industry = str(profile.get("industry") or "services")
    seeds = _INDUSTRY_SEEDS.get(industry) or _INDUSTRY_SEEDS["services"]

    brand = ""
    if isinstance(profile.get("brand"), dict):
        brand = str(profile["brand"].get("display_name") or "")
    story = pack.get("site_story") or {}
    if not brand:
        brand = str(story.get("likely_business_name") or pack.get("website", {}).get("domain") or "Brand")

    location = _location_phrase(profile, pack)
    services = [str(s) for s in (profile.get("services") or [])[:6]]
    use_cases = [str(u) for u in (profile.get("use_cases") or [])[:6]]

    primary = _uniq(
        list(seeds["primary"])
        + [s.lower() for s in services[:3]]
        + ([f"{services[0]} {location}".strip()] if services and location else []),
        limit=6,
    )
    secondary = _uniq(
        list(seeds["secondary"]) + [u.lower() for u in use_cases[:4]],
        limit=8,
    )

    # Pull benefit headline / CTA from content suggestions when present.
    hero = ""
    sub = ""
    weak_ctas = {"contact", "contact us", "learn more", "get started", "click here", "read more"}
    cta = str(profile.get("primary_cta") or seeds["cta"][0])
    if cta.lower() in weak_ctas:
        cta = seeds["cta"][0]
    for item in content_suggestions or []:
        if not isinstance(item, dict):
            continue
        area = str(item.get("area") or "").lower()
        sug = _clean(item.get("suggested"), 120)
        if not sug:
            continue
        if "headline" in area and not hero:
            hero = sug
        elif "sub" in area and not sub:
            sub = sug
        elif "cta" in area and sug.lower() not in weak_ctas:
            cta = sug

    if not hero:
        offer = services[0] if services else primary[0]
        hero = f"{brand} — {offer}" if offer else brand
    if not sub:
        sub = _clean(profile.get("one_liner") or profile.get("usecase_summary") or "", 160)
        if not sub and primary:
            where = f" in {location}" if location else ""
            sub = f"{primary[0].capitalize()}{where} — clearer story, stronger next step."

    # SEO title: brand + primary intent + location (not a stuffed keyword list).
    title_bits = [brand]
    if primary:
        intent = primary[0]
        if (
            len(intent) >= 4
            and intent.lower() not in _LOCATION_STOP
            and intent.lower() not in brand.lower()
        ):
            title_bits.append(intent.title() if intent.islower() else intent)
    if (
        location
        and len(location) >= 3
        and location.lower() not in _LOCATION_STOP
        and location.lower() not in " ".join(title_bits).lower()
    ):
        title_bits.append(location)
    page_title = " | ".join(title_bits[:3])
    if len(page_title) > 60:
        safe_intent = next(
            (p for p in primary if len(p) >= 4 and p.lower() not in brand.lower()),
            "",
        )
        page_title = (
            f"{brand} | {safe_intent.title()}"[:60]
            if safe_intent
            else brand[:60]
        )

    meta_description = _clean(sub or hero, 155)
    if len(meta_description) < 70 and primary:
        meta_description = _clean(
            f"{brand}: {primary[0]}{f' in {location}' if location else ''}. {cta}.",
            155,
        )

    og_title = hero if len(hero) <= 70 else page_title
    h1 = hero

    tone_words = list(seeds["tone"])
    avoid_words = list(seeds["avoid"])
    cta_options = _uniq([cta] + list(seeds["cta"]), limit=4)

    # Theme-aware voice note
    theme = (design_direction or {}).get("theme_label") or (design_direction or {}).get("theme") or ""
    voice_note = (
        f"Write like a {industry.replace('_', ' ')} brand"
        + (f" with a {str(theme).lower()} visual system" if theme else "")
        + f" — prefer {', '.join(tone_words[:3])}; avoid {', '.join(avoid_words[:3])}."
    )

    meta = {
        "version": 1,
        "generated_at": _now(),
        "brand": brand,
        "industry": industry,
        "location": location or None,
        "page_title": page_title,
        "meta_description": meta_description,
        "og_title": og_title,
        "og_description": meta_description,
        "h1": h1,
        "primary_keywords": primary,
        "secondary_keywords": secondary,
        "cta_primary": cta_options[0],
        "cta_alternates": cta_options[1:],
        "tone_words": tone_words,
        "avoid_words": avoid_words,
        "voice_note": voice_note,
        "schema_type": seeds.get("schema") or "Organization",
        "source": "company_profile",
    }

    if isinstance(llm_override, dict):
        for key in (
            "page_title",
            "meta_description",
            "og_title",
            "og_description",
            "h1",
            "cta_primary",
            "voice_note",
            "schema_type",
        ):
            val = llm_override.get(key)
            if isinstance(val, str) and val.strip():
                limit = 60 if key == "page_title" else 155 if "description" in key else 120
                meta[key] = _clean(val, limit)
        for key in ("primary_keywords", "secondary_keywords", "tone_words", "avoid_words", "cta_alternates"):
            val = llm_override.get(key)
            if isinstance(val, list) and val:
                meta[key] = _uniq([str(x) for x in val], limit=10)
        meta["source"] = "llm"

    return meta


def write_content_metadata(root: Path, payload: dict) -> Path:
    path = root / METADATA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_content_metadata(root: Path) -> dict | None:
    path = root / METADATA_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
