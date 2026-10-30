"""Company intelligence from crawl evidence — fast, local, no cloud required.

Base44-feel for "what does this company do?" comes from structured extraction
of the crawl, not from hoping a CPU 7B rediscovers the business every Ask Brain.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_FILENAME = "evidence/company_profile.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any, limit: int = 240) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:limit]


def _uniq(items: list[str], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def _extract_brand_names(story: dict, domain: str) -> dict[str, str]:
    """Prefer real studio names over SEO niche titles like 'Video Production Malta'."""
    values = [str(v) for v in (story.get("value_prop_candidates") or []) if v]
    excerpts = []
    for page in story.get("pages") or []:
        if isinstance(page, dict):
            excerpts.append(str(page.get("body_excerpt") or page.get("excerpt") or ""))
            excerpts.append(str(page.get("meta_description") or ""))
    blob = " ".join(values + excerpts + [str(story.get("likely_business_name") or "")])

    legal = ""
    # "Exclusive Video Productions (Technology & Visual Agency)"
    m = re.search(
        r"\b([A-Z][A-Za-z0-9&'’.-]*(?:\s+[A-Z][A-Za-z0-9&'’.-]*){1,5})\s*\((?:Technology|Visual|Agency|Studio|Productions)",
        blob,
    )
    if m:
        legal = m.group(1).strip()
    if not legal:
        m = re.search(
            r"\b(Exclusive Video Productions|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3}\s+Productions)\b",
            blob,
        )
        if m:
            legal = m.group(1).strip()

    short = ""
    m = re.search(r"\b([A-Z]{2,6}\s+Malta)\b", blob)
    if m:
        short = m.group(1).strip()
    if not short and legal:
        initials = "".join(w[0] for w in legal.split() if w[:1].isupper())
        if len(initials) >= 2:
            # EVP from Exclusive Video Productions + location hint
            if re.search(r"\bMalta\b", blob):
                short = f"{initials} Malta"
            else:
                short = initials

    seo_name = _clean(story.get("likely_business_name") or "", 80)
    # Reject SEO keyword titles when we have a real brand
    if seo_name and legal and seo_name.lower() != legal.lower():
        if "|" in seo_name or seo_name.lower().startswith(
            ("video production", "web design", "seo ", "digital marketing")
        ):
            display = short or legal
        else:
            display = short or legal or seo_name
    else:
        display = short or legal or seo_name or domain.split(".")[0]

    return {
        "display_name": display[:60],
        "legal_name": (legal or display)[:80],
        "short_name": (short or display.split()[0])[:40],
        "seo_title_name": seo_name[:80],
    }


def _extract_location(blob: str) -> str:
    patterns = [
        r"\bin\s+(Il-Ħamrun|Hamrun|Valletta|Sliema|Malta(?:\s+and\s+Gozo)?)",
        r"\bacross\s+(Malta(?:\s+and\s+Gozo)?)",
        r"\bfrom\s+(Il-Ħamrun|Hamrun|Valletta|Sliema)",
        r"\b(Malta(?:\s+&\s+Gozo)?|Malta(?:\s+and\s+Gozo)?)\b",
        r"\b(London|Dubai|Gozo)\b",
    ]
    stop = {"you", "our", "the", "this", "that", "your", "we", "us"}
    for pat in patterns:
        m = re.search(pat, blob, re.I)
        if m:
            val = _clean(m.group(1) if m.lastindex else m.group(0), 60)
            if val.lower() in stop or len(val) < 3:
                continue
            return val
    return ""


def _extract_services(story: dict, blob: str) -> list[str]:
    known = [
        "Outside Broadcasting",
        "Live Streaming",
        "Corporate Video",
        "Corporate Events",
        "TV Commercials",
        "Television Commercials",
        "Digitization",
        "Video Digitization",
        "Weddings",
        "Wedding Films",
        "Engagement Films",
        "Highlight Films",
        "Tape Digitization",
        "Live Broadcast",
    ]
    found = []
    low = blob.lower()
    for svc in known:
        if svc.lower() in low:
            found.append(svc)
    # From "We get called for X Y Z"
    m = re.search(
        r"We get called for\s+([^\.]+)",
        blob,
        re.I,
    )
    if m:
        chunk = m.group(1)
        for part in re.split(r"[·|,;/]| and ", chunk):
            part = part.strip(" .-")
            if 3 < len(part) < 40:
                found.append(part[:1].upper() + part[1:])

    # Service page titles
    for page in story.get("pages") or []:
        if not isinstance(page, dict):
            continue
        if (page.get("role") or "") != "services":
            continue
        for h in page.get("h1") or []:
            t = _clean(h, 60)
            if t and "guide" not in t.lower() and "|" not in t:
                found.append(t)

    # Normalize commercials naming
    normalized = []
    for item in found:
        if "commercial" in item.lower() and "tv" not in item.lower():
            item = "TV Commercials"
        if item.lower() in {"digitization", "video digitization", "tape digitization"}:
            item = "Digitization"
        if item.lower() in {"live-streaming", "live streaming services"}:
            item = "Live Streaming"
        if item.lower().startswith("outside broadcast"):
            item = "Outside Broadcasting"
        normalized.append(item)
    return _uniq(normalized, limit=8)


def _extract_use_cases(blob: str, services: list[str]) -> list[str]:
    cues = [
        (r"sports", "Sports and stadium coverage"),
        (r"concerts?", "Concerts and live events"),
        (r"conferences?", "Conferences and product launches"),
        (r"gala", "Gala dinners and brand moments"),
        (r"weddings?", "Weddings and celebrations"),
        (r"corporate", "Corporate film and internal communications"),
        (r"commercials?", "TV commercials and campaigns"),
        (r"digitization|tape", "Archive / tape digitization"),
    ]
    out = []
    low = blob.lower()
    for pat, label in cues:
        if re.search(pat, low):
            out.append(label)
    if not out and services:
        out = [f"{s} engagements" for s in services[:4]]
    return _uniq(out, limit=8)


def _extract_audience(blob: str, industry: str) -> str:
    low = blob.lower()
    if "broadcast" in low or "corporate" in low:
        return "Brands, broadcasters, and event organisers who need production-grade video and live delivery"
    if industry == "restaurant":
        return "Diners booking tables and discovering the menu"
    if "agency" in low:
        return "Businesses that need a clear digital presence and conversion path"
    return "Prospective customers evaluating the offer on the website"


def _extract_proof(blob: str) -> list[str]:
    proof = []
    for pat in [
        r"Est\.?\s*20\+?\s*yrs?",
        r"Over\s+20\s+years",
        r"20\+\s+years",
        r"Up to 8K",
        r"8K",
        r"broadcast-quality",
        r"same people, whole way through",
        r"Three desks",
    ]:
        m = re.search(pat, blob, re.I)
        if m:
            proof.append(_clean(m.group(0), 60))
    return _uniq(proof, limit=6)


def _infer_industry(services: list[str], blob: str, *, brand: str = "") -> str:
    low = blob.lower()
    joined = " ".join(services).lower()
    brand_low = (brand or "").lower()
    broadcastish = any(
        k in low or k in joined
        for k in ("broadcast", "outside broadcast", "live streaming", "ob ", "corporate video")
    )
    # Wedding studios only when the brand/offer is wedding-led — not when
    # a broadcast shop merely lists weddings among many services.
    wedding_led = any(
        k in brand_low for k in ("wedding", "bridal")
    ) or any(
        k in low or k in joined
        for k in ("wedding film", "wedding films", "bridal film", "engagement film")
    )
    if wedding_led and not broadcastish:
        return "wedding_films"
    if wedding_led and "wedding" in brand_low:
        return "wedding_films"
    if broadcastish or any(
        k in low or k in joined for k in ("video production", "streaming")
    ):
        return "video_production_broadcast"
    if any(k in low for k in ("restaurant", "bistro", "menu", "dining")):
        return "restaurant"
    if any(k in low for k in ("saas", "software", "platform")):
        return "saas"
    if "agency" in low:
        return "agency"
    return "services"


def _primary_offer(services: list[str], values: list[str]) -> str:
    if services:
        return ", ".join(services[:4])
    if values:
        # Take clause after colon if present
        v = values[0]
        if ":" in v:
            v = v.split(":", 1)[1]
        return _clean(v, 140)
    return "Core services described on the website"


def _usecase_summary(brand: str, services: list[str], location: str, use_cases: list[str]) -> str:
    where = f" in {location}" if location else ""
    if services:
        offer = ", ".join(services[:3])
        extra = f" Typical jobs: {', '.join(use_cases[:3])}." if use_cases else ""
        return (
            f"{brand} is hired{where} for {offer.lower()}. "
            f"Prospects use the site to understand capability and start a project.{extra}"
        )
    return f"{brand} uses the website to explain its offer{where} and convert visitors into enquiries."


def build_company_profile(pack: dict | None) -> dict[str, Any]:
    """Deterministic company profile — milliseconds, grounded in crawl text."""
    pack = pack or {}
    website = pack.get("website") or {}
    domain = website.get("domain") or "the website"
    story = pack.get("site_story") or {}
    conv = pack.get("conversion_path") or {}
    scores = pack.get("scores") or {}

    values = [str(v) for v in (story.get("value_prop_candidates") or []) if v]
    pages = [p for p in (story.get("pages") or []) if isinstance(p, dict)]
    excerpts = [
        str(p.get("body_excerpt") or p.get("excerpt") or "") for p in pages
    ]
    metas = [str(p.get("meta_description") or "") for p in pages]
    blob = "\n".join(values + excerpts + metas + [str(h) for h in (story.get("headlines") or [])])

    names = _extract_brand_names(story, domain)
    location = _extract_location(blob)
    services = _extract_services(story, blob)
    use_cases = _extract_use_cases(blob, services)
    industry = _infer_industry(
        services,
        blob,
        brand=str(names.get("display_name") or names.get("legal_name") or ""),
    )
    proof = _extract_proof(blob)
    audience = _extract_audience(blob, industry)
    offer = _primary_offer(services, values)
    ctas = _uniq([str(c) for c in (story.get("calls_to_action") or []) if c], limit=6)
    # Prefer action CTAs over bare Contact
    primary_cta = next(
        (c for c in ctas if c.lower() not in {"contact", "learn more", "home"}),
        (ctas[0] if ctas else "Start a project"),
    )

    one_liner = ""
    if values:
        one_liner = _clean(values[0], 220)
        # Prefer the EVP Malta studio line when present
        for v in values:
            if re.search(r"\bEVP\b|\bstudio\b|20\+", v, re.I):
                one_liner = _clean(v, 220)
                break
    elif excerpts:
        one_liner = _clean(excerpts[0], 220)

    about_page = next((p for p in pages if (p.get("role") or "") == "about"), None)
    home_page = next((p for p in pages if (p.get("role") or "") == "home"), None)

    profile = {
        "version": 1,
        "generated_at": _now(),
        "source": "crawl_extraction",
        "domain": domain,
        "brand": names,
        "industry": industry,
        "industry_label": {
            "wedding_films": "Wedding films / cinematic storytelling",
            "video_production_broadcast": "Video production & live broadcast",
            "restaurant": "Restaurant / hospitality",
            "saas": "Software / SaaS",
            "agency": "Agency / studio",
            "services": "Service business",
        }.get(industry, industry),
        "location": location,
        "one_liner": one_liner,
        "offer": offer,
        "services": services,
        "use_cases": use_cases,
        "audience": audience,
        "proof_points": proof,
        "primary_cta": primary_cta,
        "ctas": ctas,
        "usecase_summary": _usecase_summary(
            names["display_name"], services, location, use_cases
        ),
        "pages": {
            "roles": story.get("roles_present") or [],
            "about_url": (about_page or {}).get("url"),
            "home_url": (home_page or {}).get("url"),
            "contact_strength": conv.get("strength"),
            "conversion_gaps": (conv.get("gaps") or [])[:6],
        },
        "scores": {
            "overall": scores.get("overall"),
            "by_category": scores.get("by_category") or {},
        },
        "story_for_brain": {
            "business_type": {
                "wedding_films": "Wedding film studio",
                "video_production_broadcast": "Video production / broadcast agency",
                "restaurant": "Restaurant",
                "saas": "SaaS product",
                "agency": "Creative / digital agency",
                "services": "Service business",
            }.get(industry, "Business website"),
            "audience": audience,
            "story": one_liner
            or f"{names['display_name']} — {offer}",
            "offer": offer,
            "tone": (
                "romantic, cinematic"
                if industry == "wedding_films"
                else "professional, production-grade"
                if industry == "video_production_broadcast"
                else "professional"
            ),
            "gaps": (conv.get("gaps") or [])[:4]
            or (
                []
                if one_liner and services
                else ["Story signals were thin in the crawl sample."]
            ),
        },
    }
    return profile


def write_company_profile(root: Path, profile: dict) -> Path:
    path = root / PROFILE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return path


def load_company_profile(root: Path) -> dict | None:
    path = root / PROFILE_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def ensure_company_profile(root: Path, pack: dict | None = None) -> dict:
    existing = load_company_profile(root)
    if existing and existing.get("brand") and existing.get("one_liner"):
        return existing
    if pack is None:
        try:
            pack = json.loads((root / "evidence" / "evidence_pack.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pack = {}
    profile = build_company_profile(pack)
    write_company_profile(root, profile)
    return profile


def profile_for_prompt(profile: dict | None, *, limit: int = 1800) -> str:
    if not profile:
        return ""
    slim = {
        "brand": (profile.get("brand") or {}).get("display_name"),
        "legal_name": (profile.get("brand") or {}).get("legal_name"),
        "industry": profile.get("industry_label") or profile.get("industry"),
        "location": profile.get("location"),
        "one_liner": profile.get("one_liner"),
        "offer": profile.get("offer"),
        "services": profile.get("services"),
        "use_cases": profile.get("use_cases"),
        "audience": profile.get("audience"),
        "proof_points": profile.get("proof_points"),
        "primary_cta": profile.get("primary_cta"),
        "usecase_summary": profile.get("usecase_summary"),
    }
    return json.dumps(slim, ensure_ascii=True)[:limit]
