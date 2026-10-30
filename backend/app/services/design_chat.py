"""Interactive design chat — brief edits + optional mockup regeneration.

Persists per-crawl under design/chat.json and design/brief.json.
Uses local Ollama when available; rule-based color/text patches otherwise.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.app.services.brain import OllamaError

CHAT_DIR = "design"
CHAT_FILENAME = "design/chat.json"
BRIEF_FILENAME = "design/brief.json"

DEFAULT_BRIEF = {
    "version": 1,
    "palette": {
        "bg": "#0b1020",
        "panel": "#11192d",
        "accent": "#6366f1",
        "accent_2": "#34d399",
        "text": "#f5f7fb",
        "muted": "#8d98b5",
    },
    "headline": "",
    "subheadline": "",
    "cta": "Get started",
    "style_notes": "Clean modern homepage, strong hero, clear CTA",
    "image_prompt": "",
}

COLOR_ALIASES = {
    "navy": "#0b1f3a",
    "blue": "#2563eb",
    "indigo": "#6366f1",
    "purple": "#7c3aed",
    "teal": "#0d9488",
    "green": "#16a34a",
    "emerald": "#34d399",
    "gold": "#f59e0b",
    "orange": "#f97316",
    "red": "#ef4444",
    "pink": "#ec4899",
    "black": "#0b1020",
    "white": "#f8fafc",
    "gray": "#64748b",
    "grey": "#64748b",
    "cream": "#f5f0e6",
}

# Legacy fallbacks — prefer agent_prompts.chat_*_system_prompt(agency)
SYSTEM_PROMPT = """You are the generative design + strategy agent for Aurelia.
Return ONLY valid JSON with assistant_message, suggestions, design_brief_patch, regenerate_mockups.
Answer from audit context. Prefer opportunities over raw findings. No tooling jargon.
"""

ADVISORY_TEXT_PROMPT = """You are the generative AI strategist for Aurelia.
Answer using ONLY the audit context. Plain language. Business outcomes first.
Do not return JSON.
"""


QUESTION_HINTS = (
    "what",
    "why",
    "how",
    "should",
    "could",
    "would",
    "can we",
    "do we",
    "is there",
    "are there",
    "about",
    "improve",
    "priority",
    "priorit",
    "suggest",
    "recommend",
    "feedback",
    "review",
    "audit",
    "finding",
    "score",
    "seo",
    "problem",
    "issue",
    "chance",
    "change",
    "fix",
    "tell me",
    "explain",
    "summary",
    "overview",
)


def _is_advisory_message(message: str) -> bool:
    text = (message or "").lower().strip()
    if not text:
        return False
    if text.endswith("?"):
        return True
    return any(h in text for h in QUESTION_HINTS)


def _looks_design_message(message: str) -> bool:
    text = (message or "").lower()
    return any(
        w in text
        for w in (
            "accent",
            "color",
            "colour",
            "palette",
            "headline",
            "cta",
            "button",
            "background",
            "mockup",
            "font",
            "layout",
            "navy",
            "gold",
            "teal",
            "redesign",
        )
    )


# Tooling / unverified SPA-shell signals — do not surface as client priorities.
_INFRA_FINDING_CODES = {
    "browser_tooling_unavailable",
    "page_render_failed",
    "thin_content_unverified",
    "missing_h1_unverified",
    "a11y_scan_failed",
    "screenshot_failed",
}

_INFRA_TITLE_HINTS = (
    "could not be rendered",
    "browser capture unavailable",
    "accessibility scan could not",
    "not visible in static html",
    "thin in static html",
)

# Useful for engineers, weak as "improve first" business advice.
_TECH_NOISE_HINTS = (
    "brotli",
    "webp",
    "avif",
    "ipv6",
    "robots.txt",
    "skipped url",
    "external url",
    "cache policy",
    "html report saved",
    "dns ",
    "loaded robots",
    "security -",
    "critical finding",
    "main landmark",
    "missing an h1",
    "missing a h1",
    "without a main landmark",
    "color contrast",
    "contrast ratio",
    "elements must meet",
)


def _is_client_facing_finding(item: dict) -> bool:
    code = str(item.get("code") or "").lower()
    if code in _INFRA_FINDING_CODES:
        return False
    title = str(item.get("title") or "").lower()
    if any(h in title for h in _INFRA_TITLE_HINTS):
        return False
    detail = item.get("detail") or {}
    err = str(detail.get("error") or "").lower()
    if "playwright" in err or "executable doesn't exist" in err:
        return False
    return True


def _is_business_priority(item: dict | str) -> bool:
    if isinstance(item, str):
        title = item.lower()
        code = ""
    else:
        if not _is_client_facing_finding(item):
            return False
        title = str(item.get("title") or "").lower()
        code = str(item.get("code") or "").lower()
    if any(h in title for h in _TECH_NOISE_HINTS):
        return False
    if code.startswith("siteone_") and any(
        h in code for h in ("brotli", "webp", "avif", "ipv6", "robots", "cache")
    ):
        return False
    return True


def _business_default_suggestions(story: dict, domain: str) -> list[str]:
    name = _clean_label(story.get("business_type") or "") or domain
    ctas = [str(c) for c in (story.get("calls_to_action") or []) if c]
    primary_cta = next(
        (
            c
            for c in ctas
            if any(w in c.lower() for w in ("quote", "project", "contact", "book"))
        ),
        ctas[0] if ctas else "Get a quote",
    )
    gaps = [str(g) for g in (story.get("gaps") or []) if g]
    suggestions = [
        f"Put a one-line offer for {name} in the hero (who you help + outcome)",
        f"Make the primary CTA unmistakable above the fold (e.g. “{primary_cta}”)",
        "Lead with 3 clear service cards so visitors know what to buy in 5 seconds",
    ]
    for g in gaps[:2]:
        low = g.lower()
        if "about" in low:
            suggestions[2] = (
                "Strengthen the About page with team, location, and trust signals"
            )
        elif "story" in low or "copy" in low:
            suggestions[0] = (
                "Rewrite homepage copy so the brand story is obvious in the first screen"
            )
    return suggestions[:3]


def _clean_label(value: str, *, bad_prefixes: tuple[str, ...] = ()) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    low = text.lower()
    if low in {"unknown", "unclear", "n/a", "none", "not clearly stated"}:
        return ""
    if any(low.startswith(p) for p in bad_prefixes):
        return ""
    if (
        "not clearly" in low
        or "inferred only" in low
        or "unclear from" in low
        or low.startswith("unknown")
    ):
        return ""
    return text


def _compact_audit_context(
    *,
    evidence_pack: dict | None,
    recommendations: dict | None,
    opportunities: list | None = None,
    sell_recommendation: dict | None = None,
    agency: dict | None = None,
    root: Path | None = None,
) -> dict:
    """Build generative-agent context (opportunities + agency + evidence)."""
    from backend.app.services.agent_context import build_agent_context

    ctx = build_agent_context(
        evidence_pack=evidence_pack,
        recommendations=recommendations,
        opportunities=opportunities,
        sell_recommendation=sell_recommendation,
        agency=agency,
        root=root,
        include_few_shot=True,
    )
    # Enrich story with service extraction from crawl pages (generic, no demo hardcoding)
    pack = evidence_pack or {}
    raw = pack.get("site_story") or {}
    story = dict(ctx.get("site_story") or {})
    pack_story = _clean_label(
        (raw.get("value_prop_candidates") or [None])[0]
        or (raw.get("headlines") or [None])[0]
        or story.get("story")
        or ""
    )
    pack_biz = _clean_label(raw.get("likely_business_name") or "")
    story["business_type"] = _extract_brand_name(
        pack_story or story.get("story") or "",
        story.get("business_type") or pack_biz or "",
    )
    pack_pages_block = pack.get("pages") or {}
    pack_page_rows = (
        pack_pages_block.get("pages")
        if isinstance(pack_pages_block, dict)
        else pack_pages_block
    )
    story["services"] = _extract_services(
        story_line=story.get("story") or pack_story or "",
        value_props=story.get("value_props") or raw.get("value_prop_candidates"),
        story_pages=raw.get("pages") or [],
        pack_pages=pack_page_rows if isinstance(pack_page_rows, list) else [],
    )
    story["story_pages"] = (raw.get("pages") or [])[:8]
    ctx["site_story"] = story

    # Prefer crawl-extracted company profile for "what do they do?" answers.
    if root is not None:
        try:
            from backend.app.services.company_profile import ensure_company_profile

            profile = ensure_company_profile(root, evidence_pack)
            ctx["company_profile"] = {
                "brand": (profile.get("brand") or {}).get("display_name"),
                "legal_name": (profile.get("brand") or {}).get("legal_name"),
                "industry": profile.get("industry_label") or profile.get("industry"),
                "location": profile.get("location"),
                "one_liner": profile.get("one_liner"),
                "services": profile.get("services") or [],
                "use_cases": profile.get("use_cases") or [],
                "audience": profile.get("audience"),
                "primary_cta": profile.get("primary_cta"),
                "usecase_summary": profile.get("usecase_summary"),
                "proof_points": profile.get("proof_points") or [],
            }
            # Override thin SEO brand with real studio name when available.
            if ctx["company_profile"].get("brand"):
                story["business_type"] = ctx["company_profile"]["brand"]
            if ctx["company_profile"].get("services"):
                story["services"] = ctx["company_profile"]["services"]
            if ctx["company_profile"].get("one_liner"):
                story["story"] = ctx["company_profile"]["one_liner"]
            if ctx["company_profile"].get("audience"):
                story["audience"] = ctx["company_profile"]["audience"]
            ctx["site_story"] = story
        except Exception:
            pass
    return ctx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def default_brief_from_context(
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
) -> dict:
    brief = json.loads(json.dumps(DEFAULT_BRIEF))
    recs = (recommendations or {}).get("recommendations") or {}
    story = (recs.get("site_story_summary") or {})
    if not story and evidence_pack:
        story = {}
    pack_story = (evidence_pack or {}).get("site_story") or {}

    domain = (
        ((recommendations or {}).get("website") or {}).get("domain")
        or ((evidence_pack or {}).get("website") or {}).get("domain")
        or "your-site.com"
    )
    headline = (
        (pack_story.get("likely_business_name") and story.get("offer")
            and f"{pack_story.get('likely_business_name')}: {story.get('offer')}")
        or story.get("offer")
        or (pack_story.get("headlines") or [None])[0]
        or (pack_story.get("likely_business_name") and f"{pack_story.get('likely_business_name')} — clearer story, stronger first impression")
        or f"A clearer website for {domain}"
    )
    # Prefer content suggestions from brain when present.
    for item in recs.get("content_suggestions") or []:
        if isinstance(item, dict) and str(item.get("area", "")).lower().startswith("hero headline") and item.get("suggested"):
            headline = item["suggested"]
            break
    sub = story.get("story") or (
        (pack_story.get("value_prop_candidates") or [None])[0]
        or recs.get("executive_summary")
        or ""
    )
    for item in recs.get("content_suggestions") or []:
        if isinstance(item, dict) and "sub" in str(item.get("area", "")).lower() and item.get("suggested"):
            sub = item["suggested"]
            break
    brief["headline"] = str(headline)[:120]
    brief["subheadline"] = str(sub)[:220]
    cta = "Book a discovery call"
    for item in recs.get("content_suggestions") or []:
        if isinstance(item, dict) and "cta" in str(item.get("area", "")).lower() and item.get("suggested"):
            cta = item["suggested"]
            break
    brief["cta"] = str(cta)[:60]
    prompts = recs.get("mockup_prompts") or []
    if prompts:
        brief["image_prompt"] = str(prompts[0])[:120]
    else:
        brief["image_prompt"] = f"modern homepage for {domain}, clear hero CTA"
    if story.get("tone"):
        brief["style_notes"] = f"Tone: {story['tone']}. Clean modern homepage, strong hero, clear CTA"
    brief["updated_at"] = _now()
    return brief


def load_brief(root: Path) -> dict:
    data = _load_json(root / BRIEF_FILENAME)
    if data:
        return data
    return json.loads(json.dumps(DEFAULT_BRIEF))


def save_brief(root: Path, brief: dict) -> Path:
    path = root / BRIEF_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    brief = dict(brief)
    brief["updated_at"] = _now()
    path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
    return path


def load_chat(root: Path) -> dict:
    data = _load_json(root / CHAT_FILENAME)
    if data and isinstance(data.get("messages"), list):
        return data
    return {"version": 1, "messages": [], "updated_at": None}


def save_chat(root: Path, chat: dict) -> Path:
    path = root / CHAT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    chat = dict(chat)
    chat["updated_at"] = _now()
    path.write_text(json.dumps(chat, indent=2), encoding="utf-8")
    return path


# Small local models sometimes echo the schema example verbatim.
_PLACEHOLDER_VALUES = {
    "optional",
    "short prompt for homepage mockup image gen",
    "short reply confirming what you changed",
}


def merge_brief(base: dict, patch: dict | None) -> dict:
    out = json.loads(json.dumps(base or DEFAULT_BRIEF))
    if not isinstance(patch, dict):
        return out
    for key in (
        "headline",
        "subheadline",
        "cta",
        "style_notes",
        "image_prompt",
        "brand_name",
    ):
        value = str(patch.get(key) or "").strip()
        if value and value.lower() not in _PLACEHOLDER_VALUES:
            out[key] = value
    if isinstance(patch.get("palette"), dict):
        palette = dict(out.get("palette") or {})
        for k, v in patch["palette"].items():
            if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v.strip()):
                palette[k] = v.strip().lower()
        out["palette"] = palette
    if isinstance(patch.get("services"), list) and patch["services"]:
        cleaned: list[Any] = []
        for item in patch["services"][:8]:
            if isinstance(item, str) and item.strip():
                cleaned.append({"title": item.strip()[:60], "body": ""})
            elif isinstance(item, dict) and (item.get("title") or item.get("name")):
                cleaned.append(
                    {
                        "title": str(item.get("title") or item.get("name")).strip()[:60],
                        "body": str(item.get("body") or item.get("description") or "").strip()[
                            :220
                        ],
                    }
                )
        if cleaned:
            out["services"] = cleaned
    if isinstance(patch.get("content_suggestions"), list) and patch["content_suggestions"]:
        suggestions = []
        for item in patch["content_suggestions"][:8]:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip()
            suggested = str(item.get("suggested") or "").strip()
            if area and suggested:
                suggestions.append(
                    {
                        "area": area[:80],
                        "suggested": suggested[:220],
                        "why": str(item.get("why") or "").strip()[:180],
                    }
                )
        if suggestions:
            out["content_suggestions"] = suggestions
    if isinstance(patch.get("layout"), dict):
        layout = dict(out.get("layout") or {})
        layout.update({k: v for k, v in patch["layout"].items() if v is not None})
        out["layout"] = layout
    out["updated_at"] = _now()
    return out


def brief_patch_nonempty(patch: dict | None) -> bool:
    if not isinstance(patch, dict) or not patch:
        return False
    for key, value in patch.items():
        if key == "palette" and isinstance(value, dict) and value:
            return True
        if key in ("services", "content_suggestions") and isinstance(value, list) and value:
            return True
        if key == "layout" and isinstance(value, dict) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False



def _clean_assistant_message(text: str) -> str:
    msg = str(text or "").strip()
    # Small models sometimes append schema leftovers into the prose.
    msg = re.sub(
        r"(?is)\s*(?:regenerate_mockups|design_brief_patch)\s*[:=].*$",
        "",
        msg,
    ).strip()
    msg = re.sub(r"(?is)\s*\{[^{}]*regenerate_mockups[^{}]*\}\s*$", "", msg).strip()
    return msg


def _priority_suggestions(audit: dict) -> list[str]:
    story = audit.get("site_story") or {}
    website = audit.get("website") or {}
    domain = (website.get("domain") if isinstance(website, dict) else None) or "this site"
    findings = audit.get("findings_summary") or {}
    actions = audit.get("priority_actions") or []
    quick = audit.get("quick_wins") or []

    client_findings = [
        f
        for f in (findings.get("top") or [])
        if isinstance(f, dict) and _is_business_priority(f) and f.get("title")
    ]
    action_titles = []
    for a in actions[:5]:
        title = a.get("title") if isinstance(a, dict) else str(a)
        title = str(title or "").strip()
        if not title:
            continue
        fake = {
            "title": title,
            "code": (a.get("code") if isinstance(a, dict) else "") or "",
            "detail": a.get("detail") if isinstance(a, dict) else {},
        }
        if _is_business_priority(fake):
            action_titles.append(title)

    quick_titles = []
    for x in quick[:5]:
        title = x.get("title") if isinstance(x, dict) else str(x)
        title = str(title or "").strip()
        if title and _is_business_priority({"title": title}):
            quick_titles.append(title)

    defaults = _business_default_suggestions(story, domain)
    suggestions: list[str] = []
    for title in defaults + action_titles + quick_titles + [
        f["title"] for f in client_findings
    ]:
        if title and title not in suggestions and _is_business_priority({"title": title}):
            suggestions.append(title)
        if len(suggestions) >= 3:
            break
    return suggestions or defaults[:3]


def _story_identity(audit: dict) -> dict[str, str]:
    story = audit.get("site_story") or {}
    website = audit.get("website") or {}
    domain = (website.get("domain") if isinstance(website, dict) else None) or "this site"
    story_line = (
        _clean_label(story.get("story") or "")
        or _clean_label(story.get("offer") or "")
        or _clean_label(audit.get("executive_summary") or "")
        or f"Public copy on {domain} is still thin in this crawl."
    )
    biz = _extract_brand_name(
        story_line,
        _clean_label(story.get("business_type") or "") or domain,
    )
    audience = (
        _clean_label(story.get("audience") or "")
        or "corporate and broadcast clients"
    )
    services = list(story.get("services") or [])
    if not services:
        services = _extract_services(
            story_line=story_line,
            value_props=story.get("value_props"),
            story_pages=story.get("story_pages"),
        )
    return {
        "domain": domain,
        "biz": biz,
        "audience": audience,
        "story_line": story_line,
        "services": services,
        "location": _extract_location(story_line, story.get("headlines") or []),
    }


def _extract_location(story_line: str, headlines: list[str] | None = None) -> str:
    """Pull a place name from crawl copy (e.g. Il-Ħamrun, Malta and Gozo)."""
    blob = " ".join([story_line or ""] + list(headlines or []))
    if not blob.strip():
        return ""

    # Town/city often appears as "… in Malta and Gozo. Il-Ħamrun."
    m = re.search(
        r"\b(Il-[\wĦħĊċĠġŻż'-]+|Valletta|Sliema|Birkirkara|Mosta|Mdina)\b",
        blob,
        re.I,
    )
    town = m.group(1) if m else ""

    regions: list[str] = []
    if re.search(r"\bmalta\b", blob, re.I):
        regions.append("Malta")
    if re.search(r"\bgozo\b", blob, re.I):
        regions.append("Gozo")

    if town and regions:
        return f"{town}, {' & '.join(regions)}"
    if town:
        return town
    if regions:
        return " & ".join(regions)
    return ""


def _extract_brand_name(story_line: str, fallback: str = "") -> str:
    """Prefer a real company name over SEO keyword titles."""
    text = story_line or ""
    # "Welcome to Acme Dental" / "About Bright Solar"
    m = re.search(
        r"(?:welcome to|about)\s+([A-Z][\w&'.]*(?:\s+[A-Z][\w&'.]*){0,4})",
        text,
        re.I,
    )
    if m:
        return _clean_label(m.group(1)) or fallback or "this business"
    # "Acme Dental | Dentist in Austin" → Acme Dental
    if re.search(r"[|\u2013\u2014]", text):
        pipe = re.split(r"\s*[|\u2013\u2014]\s*", text, maxsplit=1)
        if pipe and len(pipe[0].strip()) >= 3:
            candidate = _clean_label(pipe[0])
            words = candidate.split()
            if words and words[0][:1].isupper() and len(words) <= 6:
                return candidate
    clean = _clean_label(fallback or "")
    return clean or fallback or "this business"


def _extract_services(
    *,
    story_line: str,
    value_props: list[str] | None = None,
    story_pages: list[dict] | None = None,
    pack_pages: list[dict] | None = None,
) -> list[str]:
    """Build a clean service list from /services/ URLs + value props — site-agnostic."""
    found: list[str] = []

    def add(label: str) -> None:
        text = re.sub(r"\s+", " ", (label or "").strip())
        # Drop trailing brand pipes: "Live Streaming | Acme"
        text = re.sub(r"\s*[|\u2013\u2014]\s*.*$", "", text).strip(" -–|")
        text = re.sub(r"\s{2,}", " ", text).strip(" -–|,")
        if len(text) < 4:
            return
        low = text.lower()
        if low in {"services", "service", "about", "contact", "home", "blog", "portfolio"}:
            return
        if any(low == x.lower() for x in found):
            return
        found.append(text.title() if text.islower() else text)

    # 1) Explicit service pages from crawl
    for page in list(story_pages or []) + list(pack_pages or []):
        url = str(page.get("url") or "")
        path = url.lower()
        if "/services/" not in path and "/service/" not in path and "/solutions/" not in path:
            continue
        slug = url.rstrip("/").split("/")[-1].replace("-", " ")
        title = page.get("title") or (page.get("h1") or [None])[0] or slug
        if isinstance(title, list):
            title = title[0] if title else slug
        add(str(title))

    # 2) Comma-separated offers in value props / story line
    blobs = [story_line or ""] + [str(v) for v in (value_props or []) if v]
    for blob in blobs:
        m = re.search(r":\s*([^.]{12,160})", blob)
        if not m:
            continue
        chunk = m.group(1)
        # Only treat as service list if it looks list-like
        if "," not in chunk and " and " not in chunk.lower():
            continue
        for part in re.split(r",|&| and ", chunk):
            add(part)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in found:
        key = re.sub(r"\s+", " ", item.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
        if len(normalized) >= 5:
            break
    return normalized


def _advisory_fallback(message: str, audit: dict) -> dict:
    """Answer the user's question briefly from crawl evidence."""
    identity = _story_identity(audit)
    scores = audit.get("scores") or {}
    findings = audit.get("findings_summary") or {}
    story = audit.get("site_story") or {}
    profile = audit.get("company_profile") or {}
    overall = scores.get("overall")
    priorities = _priority_suggestions(audit)
    top3 = "; ".join(priorities[:3])

    client_findings = [
        f
        for f in (findings.get("top") or [])
        if isinstance(f, dict) and _is_business_priority(f) and f.get("title")
    ]

    text = (message or "").lower().strip()
    domain = identity["domain"]
    biz = profile.get("brand") or identity["biz"]
    audience = profile.get("audience") or identity["audience"]
    story_line = profile.get("one_liner") or identity["story_line"]
    services = list(profile.get("services") or identity.get("services") or [])
    location = profile.get("location") or identity.get("location") or _extract_location(
        story_line, story.get("headlines") or []
    )
    use_cases = list(profile.get("use_cases") or [])
    usecase_summary = profile.get("usecase_summary") or ""
    headlines = [str(h) for h in (story.get("headlines") or []) if h][:4]
    ctas = [str(c) for c in (story.get("calls_to_action") or []) if c][:5]
    opportunities = [
        o
        for o in (audit.get("opportunities") or [])
        if isinstance(o, dict) and (o.get("status") or "").lower() != "rejected"
    ]
    sell = audit.get("sell_recommendation") or {}
    agency_name = ((audit.get("agency") or {}).get("agency_name")) or "your agency"

    # Short factual answers: chips only, no "Suggestions:" dumped into the reply.
    append_suggestions = True
    followups: list[str] = []

    # --- Question-specific answers ---
    if any(
        k in text
        for k in (
            "where",
            "located",
            "location",
            "based",
            "address",
            "which city",
            "which town",
            "which country",
        )
    ):
        assistant = (
            f"They’re based in {location}."
            if location
            else "The crawl didn’t capture a clear street address."
        )
        followups = [
            "What services do they provide?",
            "Give me a brief on what they do",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif (
        "service" in text
        or "what do they offer" in text
        or "what they offer" in text
        or "offerings" in text
    ):
        if services:
            assistant = f"{biz} provides: {', '.join(services)}."
        else:
            offer = story.get("offer") or story_line
            assistant = (
                f"{biz} appears to offer: {offer}."
                if offer
                else f"The crawl did not list clear services for {biz}."
            )
        followups = [
            "Where is the place located?",
            "Give me a brief on what they do",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif any(
        k in text
        for k in (
            "use case",
            "usecase",
            "who hires",
            "who calls",
            "who are they for",
            "who is it for",
        )
    ):
        if use_cases or usecase_summary:
            assistant = usecase_summary or (
                f"{biz} typically gets hired for: {', '.join(use_cases)}."
            )
        else:
            assistant = (
                f"{biz} serves {audience}."
                if audience
                else f"The crawl didn’t spell out clear use cases for {biz}."
            )
        followups = [
            "What services do they provide?",
            "Give me a brief on what they do",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif any(
        k in text
        for k in (
            "brief on what",
            "what they do",
            "what do they do",
            "what does it do",
            "what does this",
            "what is this website about",
            "what is this business",
            "who are they",
            "summary of",
            "overview of",
        )
    ):
        if story_line or services:
            bits = [story_line] if story_line else []
            if services:
                bits.append(f"Services: {', '.join(services[:5])}.")
            if location:
                bits.append(f"Based in {location}.")
            if use_cases:
                bits.append(f"Typical jobs: {', '.join(use_cases[:4])}.")
            if usecase_summary and usecase_summary not in " ".join(bits):
                bits.append(usecase_summary)
            assistant = " ".join(bits)
            followups = [
                "What should we improve first?",
                "What services do they provide?",
                "Build me a cinematic agency homepage",
            ]
            append_suggestions = False
            return {
                "assistant_message": assistant,
                "suggestions": followups,
                "design_brief_patch": {},
                "regenerate_mockups": False,
                "source": "company_profile",
                "append_suggestions": False,
            }
        props = [str(v) for v in (story.get("value_props") or []) if v]
        brief = next(
            (p for p in props if len(str(p)) > 40),
            story_line,
        )
        brief = re.sub(r"\s+", " ", brief).strip()
        loc_bit = ""
        if location and location.split(",")[0].lower() not in brief.lower():
            loc_bit = f" Based in {location}."
        assistant = f"{biz}: {brief}{loc_bit}"
        followups = [
            "What services do they provide?",
            "Where is the place located?",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif any(
        k in text
        for k in (
            "what is this",
            "whats this",
            "what's this",
            "about this",
            "who are they",
            "business about",
            "website about",
            "website is about",
            "company about",
            "tell me about",
        )
    ):
        assistant = f"{biz}: {story_line}"
        if location and location.split(",")[0] not in story_line:
            assistant += f" Based in {location}."
        followups = [
            "What services do they provide?",
            "Where is the place located?",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif any(k in text for k in ("audience", "who is it for", "target", "customers", "clients")):
        assistant = f"They’re aimed at {audience}."
        followups = [
            "What is this website about?",
            "Where is the place located?",
            "What should we improve first?",
        ]
        append_suggestions = False
    elif (
        any(
            k in text
            for k in (
                "improve first",
                "priorit",
                "what should we improve",
                "what should we fix",
                "what should we change",
                "where should we start",
                "next step",
                "fix first",
            )
        )
        and not any(k in text for k in ("located", "location", "address", "based"))
    ):
        if opportunities:
            titles = [
                o.get("client_title") or o.get("title")
                for o in opportunities[:3]
                if o.get("client_title") or o.get("title")
            ]
            assistant = (
                f"As {agency_name}, start with the commercial opportunities on {domain}. "
                f"For {biz}, prioritize: {'; '.join(titles)}."
            )
            if sell.get("package_name") or sell.get("recommended_package"):
                pkg = sell.get("package_name") or sell.get("recommended_package")
                price = sell.get("price")
                price_bit = f" (€{int(price)})" if price is not None else ""
                assistant += f" Recommended engagement: {pkg}{price_bit}."
            followups = [
                "Why that package?",
                "Summarize the opportunities",
                "What should the redesigned homepage say?",
            ]
        else:
            assistant = (
                f"Start with messaging and conversion on {domain}. "
                f"For {biz}, make the offer obvious above the fold for {audience}. "
                f"Do these next: {top3}."
            )
            followups = priorities[:3]
        if overall is not None:
            assistant += f" Current audit score is about {overall}/10."
    elif any(k in text for k in ("homepage suggestion", "concrete homepage", "hero", "homepage idea")):
        h1 = headlines[0] if headlines else f"{biz}"
        cta = next(
            (
                c
                for c in ctas
                if "project" in c.lower() or "quote" in c.lower() or "contact" in c.lower()
            ),
            ctas[0] if ctas else "Get in touch",
        )
        service_bit = (
            f"Show {min(3, len(services))} service cards under the hero."
            if services
            else "Add a clear services strip under the hero."
        )
        assistant = (
            f"Three concrete homepage changes for {biz}: "
            f"1) Hero headline: rewrite “{h1}” into a benefit-led line. "
            f"2) One primary button: “{cta}” above the fold. "
            f"3) {service_bit}"
        )
        followups = [
            "What should we improve first?",
            "Suggest a better hero headline",
            "make accent navy and gold",
        ]
    elif any(k in text for k in ("opportunity", "opportunities", "what should we sell", "package")):
        if opportunities:
            lines = []
            for o in opportunities[:4]:
                title = o.get("client_title") or o.get("title")
                pri = o.get("priority") or "medium"
                lines.append(f"{title} ({pri})")
            assistant = (
                f"{agency_name} has {len(opportunities)} commercial opportunities for {biz}: "
                + "; ".join(lines)
                + "."
            )
            if sell.get("package_name"):
                assistant += (
                    f" Sell recommendation: {sell.get('package_name')}"
                    + (f" (€{int(sell['price'])})" if sell.get("price") is not None else "")
                    + "."
                )
            followups = [
                "What should we improve first?",
                "Why that package?",
                "Build a proposal angle",
            ]
        else:
            assistant = (
                f"No opportunities generated yet for {domain}. "
                "Open the Opportunities tab or regenerate after the crawl."
            )
            followups = ["What should we improve first?", "What is this website about?"]
        append_suggestions = False
    elif any(k in text for k in ("headline", "tagline", "slogan")):
        h1 = headlines[0] if headlines else biz
        offer = story.get("offer") or (services[0] if services else "your core offer")
        loc = location or "your market"
        assistant = (
            f"Current hero/title signal: “{h1}”. "
            f"Stronger option: “{offer} for {audience} in {loc} — clear next step above the fold.”"
        )
        followups = [
            "Give me 3 concrete homepage suggestions",
            "What should we improve first?",
        ]
    elif "seo" in text:
        seo_bits = [
            f["title"]
            for f in client_findings
            if str(f.get("category") or "").lower() == "seo"
        ][:3]
        assistant = (
            f"SEO priorities for {domain}: "
            + ("; ".join(seo_bits) if seo_bits else top3)
            + "."
        )
        followups = seo_bits[:3] or priorities[:3]
    elif any(k in text for k in ("score", "rating", "how good")):
        assistant = f"The audit score for {domain} is about {overall}/10."
        followups = [
            "What should we improve first?",
            "Give me 3 concrete homepage suggestions",
        ]
        append_suggestions = False
    elif any(k in text for k in ("cta", "call to action", "convert", "lead")):
        cta = ctas[0] if ctas else "Get a quote"
        assistant = (
            f"CTAs on the site: {', '.join(ctas) if ctas else 'not clearly captured'}. "
            f"Best pattern: one primary CTA (“{cta}”) in the header/hero."
        )
        followups = priorities[:3]
    elif "accessib" in text or "contrast" in text or "a11y" in text:
        a11y = [
            f["title"]
            for f in client_findings
            if str(f.get("category") or "").lower() == "accessibility"
        ][:3]
        assistant = (
            f"Accessibility issues: "
            + ("; ".join(a11y) if a11y else "review contrast and landmarks")
            + "."
        )
        followups = a11y[:3] or ["What should we improve first?"]
    else:
        if location and any(k in text for k in ("place", "office", "studio", "from")):
            assistant = f"They’re based in {location}."
        else:
            assistant = f"{biz}: {story_line}"
        followups = [
            "What services do they provide?",
            "Where is the place located?",
            "Give me a brief on what they do",
        ]
        append_suggestions = False

    return {
        "assistant_message": assistant.strip(),
        "suggestions": followups[:3],
        "append_suggestions": append_suggestions,
        "design_brief_patch": {},
        "regenerate_mockups": False,
        "source": "rule_based",
    }


def _rule_based_turn(
    message: str,
    brief: dict,
    audit: dict | None = None,
) -> dict:
    text = message.lower()
    patch: dict[str, Any] = {}
    palette_patch: dict[str, str] = {}
    regenerate = False
    audit = audit or {}

    if _is_advisory_message(message) and not _looks_design_message(message):
        return _advisory_fallback(message, audit)

    # Preserve mention order so "navy and gold" → accent + accent_2.
    named_colors: list[tuple[str, str, int]] = []
    for name, hex_color in COLOR_ALIASES.items():
        idx = text.find(name)
        if idx >= 0:
            named_colors.append((name, hex_color, idx))
    named_colors.sort(key=lambda item: item[2])
    color_hexes = [hex_color for _, hex_color, _ in named_colors]

    if color_hexes:
        if any(w in text for w in ("background", "bg", "backdrop")) and len(color_hexes) == 1:
            palette_patch["bg"] = color_hexes[0]
        elif "text" in text and "accent" not in text and len(color_hexes) == 1:
            palette_patch["text"] = color_hexes[0]
        elif any(w in text for w in ("secondary", "accent 2", "accent2", "highlight")) and len(
            color_hexes
        ) == 1:
            palette_patch["accent_2"] = color_hexes[0]
        else:
            palette_patch["accent"] = color_hexes[0]
            if len(color_hexes) >= 2:
                palette_patch["accent_2"] = color_hexes[1]
        regenerate = True

    if palette_patch:
        patch["palette"] = palette_patch

    headline_match = re.search(
        r"(?:headline|title)\s*(?:to|:)\s*[\"']?(.+?)[\"']?$",
        message,
        re.I,
    )
    if headline_match:
        patch["headline"] = headline_match.group(1).strip()[:120]
        regenerate = True

    cta_match = re.search(
        r"(?:cta|button)\s*(?:to|:|say|says)\s*[\"']?(.+?)[\"']?$",
        message,
        re.I,
    )
    if cta_match:
        patch["cta"] = cta_match.group(1).strip()[:40]
        regenerate = True

    if any(w in text for w in ("regenerate", "new mockup", "new image", "render again")):
        regenerate = True

    if "hero" in text and ("stronger" in text or "bigger" in text):
        notes = str(brief.get("style_notes") or "")
        patch["style_notes"] = (notes + " Bold hero, larger CTA, clearer hierarchy.").strip()
        regenerate = True

    if regenerate and not patch.get("image_prompt"):
        notes = brief.get("style_notes") or "modern homepage"
        accent = (patch.get("palette") or {}).get("accent") or (brief.get("palette") or {}).get(
            "accent"
        )
        patch["image_prompt"] = (
            f"{notes}, accent {accent}, clear hero CTA"
        )[:120]

    if not patch and not regenerate:
        if audit:
            return _advisory_fallback(message, audit)
        return {
            "assistant_message": (
                "I can answer questions about this site from the crawl, or change the redesign. "
                "Try: “What should we improve first?”, “What is this business about?”, "
                "or “make accent navy and gold”."
            ),
            "suggestions": [
                "What should we improve first?",
                "Summarize the site story",
                "make accent navy and CTA: Book a call",
            ],
            "design_brief_patch": {},
            "regenerate_mockups": False,
            "source": "rule_based",
        }

    changed = []
    if "palette" in patch:
        changed.append("colors")
    if "headline" in patch:
        changed.append("headline")
    if "cta" in patch:
        changed.append("CTA")
    if regenerate and not changed:
        changed.append("live preview")

    return {
        "assistant_message": (
            "Updated " + ", ".join(changed) + ". "
            + ("Refreshing the live demo now." if regenerate else "")
        ).strip(),
        "suggestions": [
            "Make the headline stronger",
            "Change CTA to Book a call",
            "Make accent navy and gold",
        ],
        "design_brief_patch": patch,
        "regenerate_mockups": regenerate,
        "source": "rule_based",
    }


def _advisory_llm_turn(
    *,
    message: str,
    audit: dict,
    recent_messages: list[dict],
    model: str | None = None,
    provider: str | None = None,
    timeout: float = 35.0,
    agency: dict | None = None,
) -> dict:
    """Plain-text Q&A — generative strategist using agency playbook + context."""
    from backend.app.services.agent_prompts import chat_advisory_system_prompt
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.llm_client import LLMError, chat_text

    agency = agency or load_agency_settings()
    baseline = _advisory_fallback(message, audit)
    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in recent_messages[-6:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    # Drop bulky few-shot string from JSON payload size; keep as separate hint
    audit_for_model = {k: v for k, v in audit.items() if k != "agency_examples"}
    few = audit.get("agency_examples")
    user_payload = {
        "user_message": message,
        "audit_context": audit_for_model,
        "recent_messages": history,
        "suggested_next_steps": baseline.get("suggestions") or [],
    }
    if few:
        user_payload["agency_examples"] = few
    messages = [
        {"role": "system", "content": chat_advisory_system_prompt(agency)},
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=True),
        },
    ]
    try:
        text, provider_used, _model_used = chat_text(
            messages,
            provider=provider,
            model=model,
            temperature=0.35,
            max_tokens=280,
            timeout=timeout,
        )
    except LLMError as exc:
        raise OllamaError(str(exc)) from exc

    assistant_message = _clean_assistant_message(text)
    if not assistant_message or len(assistant_message) < 40:
        raise ValueError("Model returned a thin advisory answer")
    if "no design" in assistant_message.lower() and len(assistant_message) < 120:
        raise ValueError("Model returned non-answer for advisory question")

    return {
        "assistant_message": assistant_message,
        "suggestions": baseline.get("suggestions") or [],
        "design_brief_patch": {},
        "regenerate_mockups": False,
        "source": provider_used,
    }


def _llm_turn(
    *,
    message: str,
    brief: dict,
    audit: dict,
    recent_messages: list[dict],
    model: str | None = None,
    base_url: str | None = None,
    provider: str | None = None,
    timeout: float = 35.0,
    agency: dict | None = None,
) -> dict:
    from backend.app.services.agent_prompts import chat_design_system_prompt
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.llm_client import LLMError, chat_json

    agency = agency or load_agency_settings()

    if _is_advisory_message(message) and not _looks_design_message(message):
        return _advisory_llm_turn(
            message=message,
            audit=audit,
            recent_messages=recent_messages,
            model=model,
            provider=provider,
            timeout=timeout,
            agency=agency,
        )

    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in recent_messages[-8:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    audit_for_model = {k: v for k, v in audit.items() if k != "agency_examples"}
    payload = {
        "user_message": message,
        "audit_context": audit_for_model,
        "current_design_brief": brief,
        "recent_messages": history,
        "instructions": (
            "You are a generative agency agent. "
            "Answer using opportunities and site_story first. "
            "If it is a question, give commercial advice and suggestions. "
            "If it is a design request, update the brief."
        ),
    }
    if audit.get("agency_examples"):
        payload["agency_examples"] = audit["agency_examples"]
    messages = [
        {"role": "system", "content": chat_design_system_prompt(agency)},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=True),
        },
    ]
    try:
        parsed, provider_used, _model_used = chat_json(
            messages,
            provider=provider,
            model=model,
            temperature=0.35,
            max_tokens=1200,
            timeout=timeout,
        )
    except LLMError as exc:
        raise OllamaError(str(exc)) from exc

    suggestions = parsed.get("suggestions")
    if isinstance(suggestions, str):
        suggestions = [suggestions]
    if not isinstance(suggestions, list):
        suggestions = []

    assistant_message = str(parsed.get("assistant_message") or "").strip()
    assistant_message = _clean_assistant_message(assistant_message)

    if not assistant_message:
        raise ValueError("Model returned empty assistant_message")

    regenerate = bool(parsed.get("regenerate_mockups"))
    patch = (
        parsed.get("design_brief_patch")
        if isinstance(parsed.get("design_brief_patch"), dict)
        else {}
    )

    return {
        "assistant_message": assistant_message,
        "suggestions": [str(s) for s in suggestions[:5] if str(s).strip()],
        "design_brief_patch": patch,
        "regenerate_mockups": regenerate,
        "source": provider_used,
    }


def _ollama_turn(**kwargs) -> dict:
    """Backward-compatible alias."""
    return _llm_turn(**kwargs)


def _ollama_on_gpu(base_url: str = "http://127.0.0.1:11434") -> bool | None:
    """True if a loaded Ollama model reports VRAM, False if CPU-only, None unknown."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/ps")
            resp.raise_for_status()
            models = resp.json().get("models") or []
            if not models:
                return None
            return any(
                int(m.get("size_vram") or 0) > 0 for m in models if isinstance(m, dict)
            )
    except Exception:
        return None


def _prefer_fast_ollama_model(configured: str | None = None) -> str | None:
    """Pick a small local model for interactive chat when available."""
    from backend.app.database import settings

    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            models = [m.get("name") for m in (response.json().get("models") or [])]
    except Exception:
        return configured

    preferred = (
        "llama3.2:3b",
        "llama3.2:latest",
        "qwen2.5:3b",
        "phi3:mini",
        "gemma2:2b",
    )
    for candidate in preferred:
        if candidate in models:
            return candidate
        prefix = candidate.split(":")[0]
        for name in models:
            if (name or "").startswith(prefix + ":"):
                return name
    return configured


def ensure_brief(
    root: Path,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
) -> dict:
    from backend.app.services.site_design import build_design_brief

    existing = _load_json(root / BRIEF_FILENAME)
    if existing and existing.get("palette") and existing.get("headline"):
        return existing
    brief = build_design_brief(
        root,
        recommendations=recommendations,
        evidence_pack=evidence_pack,
    )
    save_brief(root, brief)
    return brief


def process_chat_message(
    root: Path,
    message: str,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    opportunities: list | None = None,
    sell_recommendation: dict | None = None,
    agency: dict | None = None,
    model: str | None = None,
    base_url: str = "http://127.0.0.1:11434",
    prefer_ollama: bool = True,
    provider: str | None = None,
    image_path: str | None = None,
) -> dict:
    from backend.app.services.agency_settings import load_agency_settings

    message = (message or "").strip()
    vision_meta = None
    if image_path:
        from backend.app.services.vision_review import review_screenshot

        vision_meta = review_screenshot(
            root,
            image_path,
            question=message or None,
            base_url=base_url,
        )
        review_txt = (vision_meta.get("review") or "").strip()
        label = image_path
        if message:
            message = (
                f"{message}\n\n[Screenshot review of `{label}`]\n{review_txt}"
            )
        else:
            message = (
                f"Please review this screenshot (`{label}`) and suggest design "
                f"improvements.\n\nVision notes:\n{review_txt}"
            )

    message = (message or "").strip()
    if not message:
        raise ValueError("Message is empty")

    agency = agency or load_agency_settings()
    agent_cfg = agency.get("agent") or {}
    use_ollama_advisory = agent_cfg.get("use_ollama_for_advisory", True)

    # Generative demo loop: "Build me a modern restaurant website" → spec → HTML → Playwright → QA
    from backend.app.services.demo_builder import (
        build_demo_from_prompt,
        looks_like_build_prompt,
    )

    if looks_like_build_prompt(message):
        chat = load_chat(root)
        chat.setdefault("messages", [])
        chat["messages"].append({"role": "user", "content": message, "at": _now()})
        domain = (
            ((evidence_pack or {}).get("website") or {}).get("domain")
            or root.parent.parent.name
            or "demo.local"
        )
        context = {
            "site_story": ((evidence_pack or {}).get("site_story") or {}),
            "scores": ((evidence_pack or {}).get("scores") or {}),
        }
        built = build_demo_from_prompt(
            root,
            message,
            domain=domain,
            context=context,
            max_fix_iters=1,
            model=model,
        )
        assistant_message = built.get("assistant_message") or "Demo built."
        chat["messages"].append(
            {
                "role": "assistant",
                "content": assistant_message,
                "at": _now(),
                "source": "demo_builder",
                "preview_updated": True,
            }
        )
        save_chat(root, chat)
        # Keep brief roughly in sync with generative spec
        spec = built.get("site_spec") or {}
        brief = ensure_brief(
            root, recommendations=recommendations, evidence_pack=evidence_pack
        )
        brief = merge_brief(
            brief,
            {
                "brand_name": spec.get("brand"),
                "headline": next(
                    (
                        s.get("headline")
                        for s in (spec.get("sections") or [])
                        if s.get("type") == "hero"
                    ),
                    spec.get("brand"),
                ),
                "cta": next(
                    (
                        s.get("cta")
                        for s in (spec.get("sections") or [])
                        if s.get("type") == "hero"
                    ),
                    "Get started",
                ),
                "palette": spec.get("palette"),
                "style_notes": f"Generative demo ({spec.get('industry')})",
            },
        )
        save_brief(root, brief)
        return {
            "assistant_message": assistant_message,
            "suggestions": [
                "Tweak the hero headline",
                "Make accent warmer",
                "Rebuild with a different industry angle",
            ],
            "design_brief": brief,
            "design_brief_patch": {"palette": spec.get("palette") or {}},
            "regenerate_mockups": False,
            "preview_updated": True,
            "demo": built.get("demo"),
            "site_spec": spec,
            "build_steps": built.get("build_steps"),
            "source": "demo_builder",
            "error": None,
            "messages": chat["messages"],
            "vision": None,
            "image_path": image_path,
        }

    brief = ensure_brief(
        root,
        recommendations=recommendations,
        evidence_pack=evidence_pack,
    )
    chat = load_chat(root)
    chat.setdefault("messages", [])
    user_msg = {"role": "user", "content": message, "at": _now()}
    if image_path:
        user_msg["image_path"] = image_path
    chat["messages"].append(user_msg)

    audit = _compact_audit_context(
        evidence_pack=evidence_pack,
        recommendations=recommendations,
        opportunities=opportunities,
        sell_recommendation=sell_recommendation,
        agency=agency,
        root=root,
    )

    turn = None
    error = None
    if prefer_ollama:
        from backend.app.database import settings
        from backend.app.services.llm_client import resolve_provider

        active = resolve_provider(provider)
        advisory = _is_advisory_message(message) and not _looks_design_message(
            message
        )

        chat_model = model or settings.ollama_model
        on_gpu = _ollama_on_gpu(base_url) if active == "ollama" else True
        # Interactive chat must stay snappy. On CPU always prefer a small model;
        # qwen3:8b is for Brain, not Site chat.
        prefer_fast = bool(agent_cfg.get("prefer_fast_chat_model", True))
        if active == "ollama" and (prefer_fast or on_gpu is not True):
            chat_model = _prefer_fast_ollama_model(chat_model)

        # Generative mode: try configured local model for advisory Q&A (fallback to rules).
        try_llm = True
        if active == "ollama" and advisory and not use_ollama_advisory:
            turn = _advisory_fallback(message, audit)
            try_llm = False
        # On CPU, Brain (qwen3:8b) already saturates Ollama. Advisory Site chat
        # stays instant via crawl-grounded rules; design edits still try 3b.
        elif active == "ollama" and advisory and on_gpu is not True:
            turn = _advisory_fallback(message, audit)
            try_llm = False
            error = "Skipped local LLM on CPU — used crawl-grounded advisory."

        if try_llm:
            # CPU / shared Ollama: short budget then rule fallback so the UI
            # never sits on a 150s browser abort behind a Brain run.
            default_timeout = 40.0 if on_gpu is not True else (70.0 if advisory else 90.0)
            ollama_timeout = float(
                agent_cfg.get("chat_timeout_seconds") or default_timeout
            )
            if on_gpu is not True:
                ollama_timeout = min(ollama_timeout, 45.0)
            try:
                turn = _llm_turn(
                    message=message,
                    brief=brief,
                    audit=audit,
                    recent_messages=chat["messages"],
                    model=chat_model,
                    base_url=base_url,
                    provider=active,
                    timeout=ollama_timeout if active == "ollama" else 45.0,
                    agency=agency,
                )
            except (OllamaError, ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
                if advisory:
                    turn = _advisory_fallback(message, audit)
                else:
                    turn = _rule_based_turn(message, brief, audit)
                if on_gpu is not True and turn is not None:
                    turn = dict(turn)
                    turn["source"] = turn.get("source") or "rule_based"
                    turn.setdefault(
                        "assistant_message",
                        turn.get("assistant_message") or "",
                    )
                    # Surface that we fell back so the UI can show why.
                    if error and "timeout" in error.lower():
                        note = (
                            " (Local model was busy/slow on CPU — used the "
                            "instant crawl-grounded answer.)"
                        )
                        msg = str(turn.get("assistant_message") or "")
                        if note.strip() not in msg:
                            turn["assistant_message"] = (msg + note).strip()
    else:
        turn = _rule_based_turn(message, brief, audit)

    rules = _rule_based_turn(message, brief, audit)
    if rules.get("design_brief_patch"):
        patch = dict(turn.get("design_brief_patch") or {})
        rule_patch = rules["design_brief_patch"]
        if rule_patch.get("palette"):
            merged_palette = dict(patch.get("palette") or {})
            merged_palette.update(rule_patch["palette"])
            patch["palette"] = merged_palette
        for key in (
            "headline",
            "subheadline",
            "cta",
            "style_notes",
            "image_prompt",
            "brand_name",
            "services",
            "content_suggestions",
            "layout",
        ):
            if key in rule_patch:
                patch[key] = rule_patch[key]
        turn["design_brief_patch"] = patch
        turn["regenerate_mockups"] = bool(
            turn.get("regenerate_mockups") or rules.get("regenerate_mockups")
        )
        if rules.get("suggestions") and not turn.get("suggestions"):
            turn["suggestions"] = rules["suggestions"]

    if _is_advisory_message(message) and (
        not turn.get("assistant_message")
        or "no design" in str(turn.get("assistant_message") or "").lower()
    ):
        advisory = _advisory_fallback(message, audit)
        turn["assistant_message"] = advisory["assistant_message"]
        turn["suggestions"] = advisory["suggestions"]
        turn["regenerate_mockups"] = False
        turn["design_brief_patch"] = {}

    patch = turn.get("design_brief_patch") if isinstance(turn.get("design_brief_patch"), dict) else {}
    # Any real brief edit should refresh the live HTML demo (Base44-style loop).
    if brief_patch_nonempty(patch):
        turn["regenerate_mockups"] = True

    brief = merge_brief(brief, patch)
    save_brief(root, brief)

    assistant_message = _clean_assistant_message(
        turn.get("assistant_message") or "Done."
    )
    suggestions = turn.get("suggestions") or []
    # Suggestion chips are shown in the UI. Only inline them for advice-style
    # answers — never for short factual replies like location.
    if suggestions and turn.get("append_suggestions", True):
        bullet_block = "\n".join(f"• {s}" for s in suggestions[:3])
        if bullet_block and bullet_block not in assistant_message:
            assistant_message = (
                assistant_message.rstrip() + "\n\nSuggestions:\n" + bullet_block
            )

    preview_updated = brief_patch_nonempty(patch) or bool(turn.get("regenerate_mockups"))
    chat["messages"].append(
        {
            "role": "assistant",
            "content": assistant_message,
            "at": _now(),
            "regenerate_mockups": bool(turn.get("regenerate_mockups")),
            "preview_updated": preview_updated,
            "source": turn.get("source"),
            "suggestions": suggestions[:4],
        }
    )
    save_chat(root, chat)

    return {
        "assistant_message": assistant_message,
        "suggestions": suggestions[:4],
        "design_brief": brief,
        "design_brief_patch": patch,
        "regenerate_mockups": bool(turn.get("regenerate_mockups")),
        "preview_updated": preview_updated,
        "source": turn.get("source"),
        "error": error,
        "messages": chat["messages"],
        "vision": vision_meta,
        "image_path": image_path,
    }
