"""Brain design decisions — pick a look per company, then demos follow it.

Profile-first / rule-based path decides instantly from industry + crawl signals.
LLM Brain may refine the same schema when available.
"""

from __future__ import annotations

from typing import Any

# Themes the demo renderer understands.
THEMES = (
    "dark_cinematic",
    "warm_romance",
    "light_editorial",
    "clean_corporate",
    "warm_hospitality",
    "bold_tech",
)

HERO_VARIANTS = ("cinematic", "split", "centered")

THEME_PRESETS: dict[str, dict[str, Any]] = {
    "dark_cinematic": {
        "label": "Dark cinematic",
        "hero_variant": "cinematic",
        "fonts": {
            "display": "Syne",
            "body": "Instrument Sans",
            "google": "Syne:wght@500;600;700;800&family=Instrument+Sans:wght@400;500;600",
        },
        "palette": {
            "bg": "#0a0f14",
            "panel": "#121a22",
            "accent": "#e11d48",
            "accent_2": "#fbbf24",
            "text": "#f8fafc",
            "muted": "#94a3b8",
            "mode": "dark",
        },
        "section_labels": {
            "services": "Capabilities",
            "services_title": "What we make happen",
            "about": "About",
            "process": "Process",
        },
        "style_notes": "Cinematic dark landing, bold display type, high-contrast CTAs.",
    },
    "warm_romance": {
        "label": "Warm romance",
        "hero_variant": "split",
        "fonts": {
            "display": "Cormorant Garamond",
            "body": "DM Sans",
            "google": "Cormorant+Garamond:wght@500;600;700&family=DM+Sans:wght@400;500;600",
        },
        "palette": {
            "bg": "#1a1412",
            "panel": "#2a211c",
            "accent": "#c4a484",
            "accent_2": "#e8d5c4",
            "text": "#faf6f1",
            "muted": "#b5a59a",
            "mode": "dark",
        },
        "section_labels": {
            "services": "Films",
            "services_title": "Stories we capture",
            "about": "The studio",
            "process": "How we work",
        },
        "style_notes": "Romantic editorial for wedding/film studios — champagne accents, serif display, split hero.",
    },
    "light_editorial": {
        "label": "Light editorial",
        "hero_variant": "centered",
        "fonts": {
            "display": "Fraunces",
            "body": "Source Sans 3",
            "google": "Fraunces:wght@500;600;700&family=Source+Sans+3:wght@400;500;600",
        },
        "palette": {
            "bg": "#f7f4ef",
            "panel": "#ffffff",
            "accent": "#0f3d3e",
            "accent_2": "#c45c26",
            "text": "#14201f",
            "muted": "#5c6b6a",
            "mode": "light",
        },
        "section_labels": {
            "services": "Work",
            "services_title": "What we offer",
            "about": "About",
            "process": "Approach",
        },
        "style_notes": "Light editorial magazine feel — calm cream ground, serif headlines, centered hero.",
    },
    "clean_corporate": {
        "label": "Clean corporate",
        "hero_variant": "split",
        "fonts": {
            "display": "Outfit",
            "body": "Source Sans 3",
            "google": "Outfit:wght@500;600;700&family=Source+Sans+3:wght@400;500;600",
        },
        "palette": {
            "bg": "#f8fafc",
            "panel": "#ffffff",
            "accent": "#0f766e",
            "accent_2": "#0369a1",
            "text": "#0f172a",
            "muted": "#64748b",
            "mode": "light",
        },
        "section_labels": {
            "services": "Services",
            "services_title": "How we help",
            "about": "About",
            "process": "Engagement",
        },
        "style_notes": "Clean corporate trust site — light panels, clear hierarchy, split hero with proof.",
    },
    "warm_hospitality": {
        "label": "Warm hospitality",
        "hero_variant": "centered",
        "fonts": {
            "display": "Libre Baskerville",
            "body": "Nunito Sans",
            "google": "Libre+Baskerville:wght@400;700&family=Nunito+Sans:wght@400;500;600;700",
        },
        "palette": {
            "bg": "#1c1410",
            "panel": "#2c211a",
            "accent": "#d97706",
            "accent_2": "#fbbf24",
            "text": "#fff7ed",
            "muted": "#d6c3b0",
            "mode": "dark",
        },
        "section_labels": {
            "services": "Menu",
            "services_title": "What to expect",
            "about": "Our story",
            "process": "Visit",
        },
        "style_notes": "Warm hospitality — amber accents, inviting type, centered reservation-led hero.",
    },
    "bold_tech": {
        "label": "Bold tech",
        "hero_variant": "cinematic",
        "fonts": {
            "display": "Space Grotesk",
            "body": "Inter",
            "google": "Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600",
        },
        "palette": {
            "bg": "#020617",
            "panel": "#0f172a",
            "accent": "#38bdf8",
            "accent_2": "#a78bfa",
            "text": "#e2e8f0",
            "muted": "#64748b",
            "mode": "dark",
        },
        "section_labels": {
            "services": "Product",
            "services_title": "Built for momentum",
            "about": "Why us",
            "process": "Get started",
        },
        "style_notes": "Bold SaaS/tech — deep slate, electric accents, product-led cinematic hero.",
    },
}


def _blob_from(pack: dict | None, profile: dict | None) -> str:
    parts: list[str] = []
    if profile:
        parts.append(str(profile.get("industry") or ""))
        parts.append(str(profile.get("industry_label") or ""))
        parts.append(str(profile.get("one_liner") or ""))
        parts.extend(str(s) for s in (profile.get("services") or [])[:8])
        parts.extend(str(u) for u in (profile.get("use_cases") or [])[:6])
        brand = profile.get("brand") or {}
        if isinstance(brand, dict):
            parts.append(str(brand.get("display_name") or ""))
            parts.append(str(brand.get("legal_name") or ""))
    story = (pack or {}).get("site_story") or {}
    parts.append(str(story.get("likely_business_name") or ""))
    parts.extend(str(h) for h in (story.get("headlines") or [])[:6])
    parts.extend(str(v) for v in (story.get("value_prop_candidates") or [])[:3])
    for page in (story.get("pages") or [])[:3]:
        if isinstance(page, dict):
            parts.append(str(page.get("title") or ""))
            parts.append(str(page.get("body_excerpt") or "")[:400])
    return " ".join(parts).lower()


def pick_theme_key(pack: dict | None = None, profile: dict | None = None) -> str:
    """Choose a theme key from company profile / crawl story."""
    industry = str((profile or {}).get("industry") or "").lower()
    blob = _blob_from(pack, profile)

    # Explicit industry from company profile wins when present.
    if industry in {"wedding", "wedding_films"}:
        return "warm_romance"
    if industry == "restaurant":
        return "warm_hospitality"
    if industry == "saas":
        return "bold_tech"
    if industry in {"healthcare", "dental", "legal", "finance"}:
        return "clean_corporate"
    if industry == "video_production_broadcast":
        return "dark_cinematic"
    if industry == "agency":
        return "light_editorial"

    # Crawl fallbacks when profile industry is generic/missing.
    brandish = " ".join(
        [
            str(((profile or {}).get("brand") or {}).get("display_name") or ""),
            str(((pack or {}).get("site_story") or {}).get("likely_business_name") or ""),
        ]
    ).lower()
    if any(k in brandish for k in ("wedding", "bridal")) or any(
        k in blob for k in ("wedding film", "wedding films", "engagement film")
    ):
        return "warm_romance"
    if any(k in blob for k in ("restaurant", "bistro", "menu", "dining", "café", "cafe")):
        return "warm_hospitality"
    if any(k in blob for k in ("saas", "software", "platform", "api", "devtools")):
        return "bold_tech"
    if any(
        k in blob
        for k in ("dentist", "dental", "clinic", "lawyer", "attorney", "accounting")
    ):
        return "clean_corporate"
    if any(
        k in blob
        for k in (
            "broadcast",
            "outside broadcast",
            "live streaming",
            "ob unit",
            "corporate video",
        )
    ):
        return "dark_cinematic"
    if "studio" in blob or "agency" in blob:
        return "light_editorial"
    return "light_editorial"


def decide_design_direction(
    pack: dict | None = None,
    profile: dict | None = None,
    *,
    llm_override: dict | None = None,
) -> dict[str, Any]:
    """Return a structured design decision for brief + demo build."""
    theme = pick_theme_key(pack, profile)
    if isinstance(llm_override, dict):
        candidate = str(llm_override.get("theme") or "").strip()
        if candidate in THEME_PRESETS:
            theme = candidate

    preset = THEME_PRESETS[theme]
    hero = preset["hero_variant"]
    if isinstance(llm_override, dict):
        hv = str(llm_override.get("hero_variant") or "").strip()
        if hv in HERO_VARIANTS:
            hero = hv

    brand = ""
    if profile and isinstance(profile.get("brand"), dict):
        brand = str(profile["brand"].get("display_name") or "")
    if not brand:
        brand = str(((pack or {}).get("site_story") or {}).get("likely_business_name") or "Brand")

    industry_label = (
        (profile or {}).get("industry_label")
        or (profile or {}).get("industry")
        or "business"
    )
    reasoning = (
        f"For {brand} ({industry_label}), choose {preset['label'].lower()} "
        f"with a {hero} hero — fits how buyers evaluate this kind of offer."
    )
    if isinstance(llm_override, dict) and llm_override.get("reasoning"):
        reasoning = str(llm_override.get("reasoning"))[:320]

    palette = dict(preset["palette"])
    if isinstance(llm_override, dict) and isinstance(llm_override.get("palette"), dict):
        for key in ("bg", "panel", "accent", "accent_2", "text", "muted"):
            val = llm_override["palette"].get(key)
            if isinstance(val, str) and val.startswith("#") and len(val) in {4, 7}:
                palette[key] = val

    from backend.app.services.visual_assets import select_visual_pack

    visuals = select_visual_pack(theme)
    if isinstance(llm_override, dict) and isinstance(llm_override.get("visuals"), dict):
        v = llm_override["visuals"]
        if v.get("query"):
            visuals["query"] = str(v["query"])[:120]
        if v.get("accent_3d") in {"rings", "camera", "cube", "plate", "orb"}:
            visuals["accent_3d"] = str(v["accent_3d"])

    return {
        "theme": theme,
        "theme_label": preset["label"],
        "hero_variant": hero,
        "layout": f"{theme}_{hero}",
        "fonts": dict(preset["fonts"]),
        "palette": palette,
        "section_labels": dict(preset["section_labels"]),
        "style_notes": preset["style_notes"],
        "reasoning": reasoning,
        "visuals": {
            "query": visuals.get("query"),
            "accent_3d": visuals.get("accent_3d"),
            "license": visuals.get("license"),
            "source": visuals.get("source"),
            "hero_alt": (visuals.get("hero") or {}).get("alt"),
        },
        "source": "llm" if llm_override else "company_profile",
    }


def normalize_design_direction(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    theme = str(raw.get("theme") or "").strip()
    if theme not in THEME_PRESETS:
        return None
    return decide_design_direction(
        None,
        None,
        llm_override=raw,
    )
