"""Generate a clickable local HTML demo site from brain + design brief.

Goal: a Base44-style multi-section landing page clients can open in the
browser — real marketing copy (not audit jargon), grounded in the crawl
story, design brief, and content suggestions.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.site_design import (
    build_design_brief,
    parse_service_blocks,
    reference_screenshot_path,
)

DEMO_DIR = "demo"
MANIFEST_FILENAME = "demo/manifest.json"
INDEX_FILENAME = "demo/index.html"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_demo(root: Path) -> dict | None:
    return _load_json(root / MANIFEST_FILENAME)


def _brief_palette(brief: dict | None) -> dict[str, str]:
    palette = (brief or {}).get("palette") or {}
    return {
        "bg": palette.get("bg") or "#0a0f14",
        "panel": palette.get("panel") or "#121a22",
        "accent": palette.get("accent") or "#e11d48",
        "accent_2": palette.get("accent_2") or "#fbbf24",
        "text": palette.get("text") or "#f8fafc",
        "muted": palette.get("muted") or "#94a3b8",
        "mode": palette.get("mode") or "dark",
    }


def _short_brand_mark(brand: str) -> str:
    """Keep cinematic brand mark readable — avoid wrapping into gray slabs."""
    text = re.sub(r"\s+", " ", (brand or "").strip())
    if len(text) <= 18:
        return text
    words = text.split(" ")
    if len(words) >= 2:
        # Prefer first + distinctive word (Wedding Films → Exclusive Wedding)
        return " ".join(words[:2])[:22]
    return text[:18]


def _accent_is_light(hex_color: str | None) -> bool:
    raw = (hex_color or "").lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        return False
    try:
        r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.62


def _split_offers(text: str) -> list[str]:
    raw = (text or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    raw = raw.replace(" & ", ", ").replace(" and ", ", ")
    parts: list[str] = []
    for chunk in raw.split(","):
        item = chunk.strip(" .;")
        lower = item.lower()
        if " in malta" in lower or lower.startswith("in "):
            continue
        if len(item) < 4:
            continue
        parts.append(item)
    return parts[:6]


def _title_case_service(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return "Service"
    return cleaned[:1].upper() + cleaned[1:]


def _story_bits(recommendations: dict | None, evidence_pack: dict | None) -> dict:
    recs = (recommendations or {}).get("recommendations") or {}
    story = recs.get("site_story_summary") or {}
    pack_story = (evidence_pack or {}).get("site_story") or {}
    domain = (
        ((recommendations or {}).get("website") or {}).get("domain")
        or ((evidence_pack or {}).get("website") or {}).get("domain")
        or "your-site.com"
    )

    business = (
        pack_story.get("likely_business_name")
        or story.get("business_type")
        or domain
    )
    # Prefer a short brand, not "Unknown — inferred…"
    if str(business).lower().startswith("unknown"):
        business = pack_story.get("likely_business_name") or domain

    narrative = (
        story.get("story")
        or (pack_story.get("value_prop_candidates") or [None])[0]
        or ""
    )
    offer = story.get("offer") or (pack_story.get("calls_to_action") or [None])[0] or ""
    audience = story.get("audience") or ""
    if str(audience).lower().startswith("not clearly"):
        audience = ""
    gaps = story.get("gaps") or []
    pages = pack_story.get("pages") or []
    current_title = ""
    if pages:
        t = pages[0].get("title") or ""
        h1 = pages[0].get("h1") or []
        current_title = t or (h1[0] if h1 else "")

    return {
        "business": str(business)[:80],
        "narrative": str(narrative)[:520],
        "offer": str(offer)[:160],
        "audience": str(audience)[:140],
        "gaps": [str(g)[:140] for g in gaps[:4]],
        "domain": domain,
        "current_title": str(current_title)[:140],
        "offers": _split_offers(str(narrative) or str(offer)),
        "headlines": [str(h)[:100] for h in (pack_story.get("headlines") or [])[:4]],
    }


def _looks_seo_title(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "|" in t or " – " in t or " - " in t and t.count(" ") <= 8:
        # Browser/SEO titles often look like "X | Y – Z"
        if any(k in t.lower() for k in ("malta", "seo", "home", "official")):
            return True
        if "|" in t:
            return True
    return False


def _benefit_headline(story: dict) -> str:
    brand = story.get("business") or "Your brand"
    offers = story.get("offers") or []
    narrative = (story.get("narrative") or "").lower()
    if any(k in narrative for k in ("broadcast", "stream", "film", "video", "camera")):
        return "Broadcast-ready production — clearer offer, stronger first call."
    if offers:
        return f"{_title_case_service(offers[0])} — clearer story, stronger first impression"
    return f"{brand} — clearer story, stronger first impression"


def _pick_headline(brief: dict, content: list[dict], story: dict) -> str:
    """Prefer benefit-led copy over SEO page titles."""
    for c in content:
        area = str(c.get("area") or "").lower()
        sug = str(c.get("suggested") or "").strip()
        if area.startswith("hero headline") and sug and not _looks_seo_title(sug):
            return sug[:120]
    h = str(brief.get("headline") or "").strip()
    if h and not _looks_seo_title(h):
        return h[:120]
    # SEO titles / short category labels → rewrite into benefit-led copy
    return _benefit_headline(story)


def _pick_subheadline(brief: dict, content: list[dict], story: dict) -> str:
    for c in content:
        area = str(c.get("area") or "").lower()
        sug = str(c.get("suggested") or "").strip()
        if "subcopy" in area or "subheadline" in area:
            if sug and "audit" not in sug.lower():
                return sug[:220]
    sub = str(brief.get("subheadline") or "").strip()
    if sub and "audit" not in sub.lower() and not sub.lower().startswith("insufficient"):
        return sub[:220]
    narrative = str(story.get("narrative") or "").strip()
    if narrative and len(narrative) > 40:
        # Prefer first sentence
        cut = re.split(r"(?<=[.!?])\s+", narrative)[0]
        return cut[:220]
    brand = story.get("business") or "This business"
    return f"{brand} — a sharper offer, one clear next step, and a homepage that converts."


def _improvement_suggestions(
    recommendations: dict | None,
    opportunities: list[dict] | None = None,
) -> list[str]:
    out: list[str] = []
    for o in opportunities or []:
        if (o.get("status") or "").lower() == "rejected":
            continue
        title = o.get("client_title") or o.get("title")
        if title:
            out.append(str(title))
        if len(out) >= 5:
            return out[:5]

    recs = (recommendations or {}).get("recommendations") or {}
    for item in recs.get("quick_wins") or []:
        text = str(item)
        low = text.lower()
        if any(x in low for x in ("elements must", "wcag", "axe", "<dl>", "pages(s)")):
            continue
        out.append(text)
        if len(out) >= 3:
            break
    for item in recs.get("priority_actions") or []:
        if isinstance(item, dict) and item.get("title"):
            title = str(item["title"])
            low = title.lower()
            if low.startswith("elements must") or "<dl>" in title or "wcag" in low:
                continue
            out.append(title)
        if len(out) >= 5:
            break
    if not out:
        out = [
            "Clarify the homepage offer in the first screen",
            "Add a single primary call to action",
            "Make services scannable as cards",
        ]
    return out[:5]


def _content_suggestions(
    story: dict,
    recommendations: dict | None,
    brief: dict,
) -> list[dict]:
    recs = (recommendations or {}).get("recommendations") or {}
    existing = recs.get("content_suggestions") or []
    normalized: list[dict] = []
    for item in existing:
        if isinstance(item, dict) and item.get("suggested"):
            normalized.append(
                {
                    "area": str(item.get("area") or "Copy")[:80],
                    "current": str(item.get("current") or "")[:180],
                    "suggested": str(item["suggested"])[:320],
                    "why": str(item.get("why") or "")[:200],
                }
            )
        elif isinstance(item, str) and item.strip():
            normalized.append(
                {
                    "area": "Copy",
                    "current": "",
                    "suggested": item.strip()[:320],
                    "why": "",
                }
            )
        if len(normalized) >= 8:
            break
    if normalized:
        return normalized

    brand = story.get("business") or "Your brand"
    offers = story.get("offers") or []
    primary = _title_case_service(offers[0]) if offers else "what you do best"
    return [
        {
            "area": "Hero headline",
            "current": story.get("current_title") or "",
            "suggested": brief.get("headline")
            or f"{brand} — {primary} with clarity and craft",
            "why": "Lead with brand + outcome, not a browser title.",
        },
        {
            "area": "Hero subcopy",
            "current": (story.get("narrative") or "")[:160],
            "suggested": brief.get("subheadline")
            or (
                f"We help clients with {', '.join(offers[:3])}."
                if offers
                else f"Spell out who {brand} helps and what happens after they contact you."
            ),
            "why": "One-breath clarity beats a dense agency paragraph.",
        },
        {
            "area": "Primary CTA",
            "current": story.get("offer") or "Weak / missing",
            "suggested": brief.get("cta") or "Book a discovery call",
            "why": "A specific next step converts better than a vague link.",
        },
        {
            "area": "Services",
            "current": ", ".join(offers[:4]) if offers else "Not listed as cards",
            "suggested": (
                "Card labels: " + ", ".join(_title_case_service(o) for o in offers[:4])
                if offers
                else "Add 3–4 service cards with one-line outcomes."
            ),
            "why": "Scannable services help buyers self-qualify.",
        },
        {
            "area": "About",
            "current": "",
            "suggested": (
                f"{brand} is built around {', '.join(offers[:3])}."
                if offers
                else f"Write a 2-sentence About for {brand}: who you are, who you serve, proof."
            ),
            "why": "Trust needs an explicit on-page story.",
        },
    ]


def _marketing_services(
    story: dict,
    content: list[dict],
    brief: dict | None = None,
    pack_story: dict | None = None,
) -> list[dict[str, str]]:
    if brief and brief.get("services"):
        normalized: list[dict[str, str]] = []
        for item in brief["services"][:6]:
            if isinstance(item, dict) and item.get("title"):
                normalized.append(
                    {
                        "title": str(item["title"])[:60],
                        "body": str(item.get("body") or "")[:220],
                    }
                )
            elif isinstance(item, str) and item.strip():
                normalized.append(
                    {
                        "title": item.strip()[:60],
                        "body": "Clear offer line from the redesign brief.",
                    }
                )
        if normalized:
            return normalized
    parsed = parse_service_blocks(pack_story or {})
    if parsed:
        return parsed[:6]

    offers = story.get("offers") or []
    services: list[dict[str, str]] = []
    for offer in offers[:4]:
        services.append(
            {
                "title": _title_case_service(offer),
                "body": f"Clear delivery of {_title_case_service(offer).lower()} for clients who care about quality.",
            }
        )
    if services:
        return services

    for item in content:
        if item.get("area", "").lower().startswith("service"):
            services.append(
                {
                    "title": "Services",
                    "body": str(item.get("suggested") or "")[:180],
                }
            )
            break
    defaults = [
        ("What we do", story.get("narrative") or "A clear explanation of the offer."),
        ("Who it's for", story.get("audience") or "The customers you most want to win."),
        ("How we work", "A simple process from brief to delivery."),
    ]
    while len(services) < 3:
        title, body = defaults[len(services)]
        services.append({"title": title, "body": str(body)[:180]})
    return services[:4]


def _process_steps(story: dict) -> list[dict[str, str]]:
    brand = story.get("business") or "our team"
    narrative = (story.get("narrative") or "").lower()
    # Light industry flavour without hardcoding one demo client.
    if any(k in narrative for k in ("broadcast", "stream", "film", "video", "camera")):
        return [
            {"n": "01", "title": "Brief", "body": f"Share goals, audience, and timeline with {brand}."},
            {"n": "02", "title": "Plan", "body": "We shape the production plan, crew, and deliverables."},
            {"n": "03", "title": "Produce", "body": "On-site or remote production with tight creative direction."},
            {"n": "04", "title": "Deliver", "body": "Edited assets or live output — ready to publish."},
        ]
    return [
        {"n": "01", "title": "Discover", "body": f"We clarify goals, audience, and success metrics with {brand}."},
        {"n": "02", "title": "Design", "body": "Messaging, structure, and visual direction aligned to conversion."},
        {"n": "03", "title": "Build", "body": "Pages, content, and components implemented to the agreed scope."},
        {"n": "04", "title": "Launch", "body": "QA, go-live, and a verification pass so improvements are measurable."},
    ]


def _contact_bits(story: dict, pack_story: dict | None, opportunities: list[dict] | None) -> dict:
    pack_story = pack_story or {}
    location = ""
    for key in ("location", "region", "city"):
        if pack_story.get(key):
            location = str(pack_story[key])
            break
    if not location:
        # Light parse from narrative: "in Malta and Gozo"
        m = re.search(r"\bin\s+([A-Z][\w\s,&]{2,40})", story.get("narrative") or "")
        if m:
            location = m.group(1).strip(" .,")
    email = ""
    for page in pack_story.get("pages") or []:
        for cta in page.get("ctas") or []:
            if "@" in str(cta):
                email = str(cta)
                break
    pitch = "Tell us about the project — we’ll reply with a clear next step."
    for o in opportunities or []:
        if (o.get("category") or o.get("theme_key") or "").lower() in {
            "conversion",
            "content",
            "ux",
        }:
            pitch = (
                "Ready for a clearer homepage and a stronger path to enquiry? "
                "Share a few details and we’ll outline the recommended engagement."
            )
            break
    return {
        "location": location[:80],
        "email": email[:120],
        "pitch": pitch,
        "title": "Let’s talk about the next version of this site.",
    }


def _process_section_title(process: list[dict[str, str]]) -> str:
    titles = {p.get("title", "").lower() for p in process}
    if "produce" in titles or "broadcast" in " ".join(titles):
        return "From brief to broadcast"
    return "From brief to launch"


def _render_html(
    *,
    domain: str,
    brief: dict,
    story: dict,
    improvements: list[str],
    services: list[dict[str, str]],
    content_suggestions: list[dict],
    process: list[dict[str, str]],
    contact: dict | None = None,
    screenshot_rel: str | None = None,
) -> str:
    """Theme-led landing — Brain design_direction chooses look; copy stays site-specific."""
    palette = _brief_palette(brief)
    brand = story.get("business") or brief.get("brand_name") or domain
    headline = _pick_headline(brief, content_suggestions, story)
    sub = _pick_subheadline(brief, content_suggestions, story)
    meta_pack = brief.get("content_metadata") if isinstance(brief.get("content_metadata"), dict) else {}
    cta = (
        str(meta_pack.get("cta_primary") or brief.get("cta") or "Start a project")
    ).strip()
    theme = str(brief.get("theme") or (brief.get("design_direction") or {}).get("theme") or "dark_cinematic")
    hero_variant = str(
        brief.get("hero_variant")
        or (brief.get("design_direction") or {}).get("hero_variant")
        or "cinematic"
    )
    fonts = brief.get("fonts") or (brief.get("design_direction") or {}).get("fonts") or {}
    display_font = str(fonts.get("display") or "Syne")
    body_font = str(fonts.get("body") or "Instrument Sans")
    google_fonts = str(
        fonts.get("google")
        or "Syne:wght@500;600;700;800&family=Instrument+Sans:wght@400;500;600"
    )
    labels = brief.get("section_labels") or (brief.get("design_direction") or {}).get("section_labels") or {}
    services_kicker = labels.get("services") or "Capabilities"
    services_title = labels.get("services_title") or "What we make happen"
    about_kicker = labels.get("about") or "About"
    process_kicker = labels.get("process") or "Process"
    mode = str(palette.get("mode") or ("light" if theme.startswith("light") or theme.startswith("clean") else "dark"))
    btn_fg = "#0a0a0a" if mode == "light" and _accent_is_light(palette.get("accent")) else "#fff"
    contact = contact or {}
    contact_title = contact.get("title") or "Let’s talk about the next version of this site."
    contact_pitch = contact.get("pitch") or (
        "Tell us about the project — we’ll reply with a clear next step."
    )
    contact_location = contact.get("location") or ""
    contact_email = contact.get("email") or ""
    process_title = _process_section_title(process)
    about = next(
        (
            c.get("suggested")
            for c in content_suggestions
            if str(c.get("area", "")).lower().startswith("about")
        ),
        None,
    ) or story.get("narrative") or f"{brand} is ready for a sharper digital presence."

    marquee_items = " ".join(
        f'<span>{_esc(s["title"])}</span><span class="dot" aria-hidden="true">✦</span>'
        for s in (services or [{"title": "Design"}, {"title": "Story"}, {"title": "Craft"}])
    )
    service_tiles = "\n".join(
        (
            f'<article class="tile reveal" style="--d:{idx * 0.08:.2f}s">'
            f'<span class="tile-n">{idx:02d}</span>'
            f"<h3>{_esc(s['title'])}</h3>"
            f"<p>{_esc(s['body'])}</p>"
            f"</article>"
        )
        for idx, s in enumerate(services[:4], start=1)
    )
    process_row = "\n".join(
        (
            f'<div class="rail-item reveal" style="--d:{idx * 0.07:.2f}s">'
            f"<span>{_esc(p['n'])}</span>"
            f"<strong>{_esc(p['title'])}</strong>"
            f"<p>{_esc(p['body'])}</p>"
            f"</div>"
        )
        for idx, p in enumerate(process)
    )
    improve_items = "\n".join(
        f"<li>{_esc(item)}</li>" for item in improvements[:5]
    )
    note_rows = "\n".join(
        (
            '<div class="note">'
            f"<span>{_esc(c.get('area'))}</span>"
            f"<strong>{_esc(c.get('suggested'))}</strong>"
            f"<em>{_esc(c.get('why') or '')}</em>"
            "</div>"
        )
        for c in content_suggestions[:6]
    )
    social = brief.get("social_content") if isinstance(brief.get("social_content"), dict) else {}
    social_rows = ""
    if social.get("post_ideas") or social.get("soundtracks"):
        idea_bits = "\n".join(
            (
                '<div class="note">'
                f"<span>{_esc(idea.get('format'))}</span>"
                f"<strong>{_esc(idea.get('hook'))}</strong>"
                f"<em>{_esc(idea.get('body'))} · CTA: {_esc(idea.get('cta'))}</em>"
                "</div>"
            )
            for idea in (social.get("post_ideas") or [])[:4]
            if isinstance(idea, dict)
        )
        music_bits = "\n".join(
            (
                '<div class="note">'
                f"<span>Soundtrack</span>"
                f"<strong>{_esc(track.get('title'))} — {_esc(track.get('artist'))}</strong>"
                f"<em>{_esc(track.get('mood'))}. {_esc(track.get('why'))} "
                f"({_esc(track.get('trend_note'))})</em>"
                "</div>"
            )
            for track in (social.get("soundtracks") or [])[:4]
            if isinstance(track, dict)
        )
        social_rows = f"{idea_bits}\n{music_bits}"
    meta_bits = []
    if contact_location:
        meta_bits.append(f"<span>{_esc(contact_location)}</span>")
    if contact_email:
        meta_bits.append(
            f'<a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a>'
        )
    contact_meta = (
        f'<div class="contact-meta">{"".join(meta_bits)}</div>' if meta_bits else ""
    )
    visuals = brief.get("visuals") if isinstance(brief.get("visuals"), dict) else {}
    hero_img = (visuals.get("hero") or {}).get("path")
    hero_alt = (visuals.get("hero") or {}).get("alt") or f"{brand} visual"
    gallery_items = list(visuals.get("supporting") or [])
    accent_kind = visuals.get("accent_3d") or "orb"
    from backend.app.services.visual_assets import accent_3d_css, render_accent_3d

    accent_html = render_accent_3d(str(accent_kind))
    credits = visuals.get("credits") or []
    credit_line = " · ".join(str(c) for c in credits[:4])

    def _hero_media(extra_class: str = "") -> str:
        if hero_img:
            return (
                f'<div class="hero-bg hero-bg--photo {extra_class}">'
                f'<img src="{html.escape(hero_img, quote=True)}" alt="{_esc(hero_alt)}" />'
                f"</div>"
            )
        return f'<div class="hero-bg {extra_class}" aria-hidden="true"></div>'

    if screenshot_rel:
        shot = (
            '<div class="ref-shot reveal">'
            f'<img src="../{html.escape(screenshot_rel, quote=True)}" alt="Current site" />'
            "<span>Current site</span>"
            "</div>"
        )
    elif gallery_items:
        g0 = gallery_items[0]
        shot = (
            '<div class="ref-shot reveal">'
            f'<img src="{html.escape(str(g0.get("path") or ""), quote=True)}" alt="{_esc(g0.get("alt"))}" />'
            "<span>Open-source visual</span>"
            "</div>"
        )
    else:
        shot = '<div class="ref-fallback reveal" aria-hidden="true"></div>'

    gallery_html = ""
    if gallery_items:
        cells = "\n".join(
            (
                f'<figure class="gallery-cell">'
                f'<img src="{html.escape(str(item.get("path") or ""), quote=True)}" '
                f'alt="{_esc(item.get("alt"))}" loading="lazy" />'
                f"<figcaption>{_esc(item.get('alt'))}</figcaption>"
                f"</figure>"
            )
            for item in gallery_items[:3]
        )
        gallery_html = f"""
    <section id="gallery">
      <p class="section-kicker">Gallery</p>
      <h2 class="section-title">Mood &amp; craft</h2>
      <p class="section-sub">Open-source photography chosen to match this brand’s story (Unsplash License).</p>
      <div class="gallery-grid">
        {cells}
      </div>
    </section>"""

    hero_mod = f"hero hero--{html.escape(hero_variant, quote=True)} theme--{html.escape(theme, quote=True)}"
    if hero_variant == "split":
        hero_block = f"""
    <section class="{hero_mod}">
      <div class="hero-copy reveal">
        <p class="eyebrow">{_esc(brand)}</p>
        <h1>{_esc(headline)}</h1>
        <p class="lede">{_esc(sub)}</p>
        <div class="cta-row">
          <a class="btn" href="#contact">{_esc(cta)}</a>
          <a class="btn ghost" href="#work">Explore work</a>
        </div>
      </div>
      <div class="hero-panel">
        {_hero_media()}
        {accent_html}
      </div>
    </section>"""
    elif hero_variant == "centered":
        hero_block = f"""
    <section class="{hero_mod}">
      {_hero_media("hero-bg--wash")}
      {accent_html}
      <div class="hero-copy reveal">
        <p class="eyebrow">{_esc(brand)}</p>
        <h1>{_esc(headline)}</h1>
        <p class="lede">{_esc(sub)}</p>
        <div class="cta-row">
          <a class="btn" href="#contact">{_esc(cta)}</a>
          <a class="btn ghost" href="#work">Explore work</a>
        </div>
      </div>
    </section>"""
    else:
        # cinematic — large brand mark + floating media panel
        hero_block = f"""
    <section class="{hero_mod}">
      {_hero_media()}
      {accent_html}
      <div class="hero-copy reveal">
        <p class="brand-mark">{_esc(_short_brand_mark(brand))}</p>
        <h1>{_esc(headline)}</h1>
        <p class="lede">{_esc(sub)}</p>
        <div class="cta-row">
          <a class="btn" href="#contact">{_esc(cta)}</a>
          <a class="btn ghost" href="#work">Explore work</a>
        </div>
      </div>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{_esc(theme)}" data-hero="{_esc(hero_variant)}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(meta_pack.get("page_title") or brand)}</title>
  <meta name="description" content="{_esc(meta_pack.get("meta_description") or sub)}" />
  <meta property="og:title" content="{_esc(meta_pack.get("og_title") or headline)}" />
  <meta property="og:description" content="{_esc(meta_pack.get("og_description") or sub)}" />
  <meta name="keywords" content="{_esc(', '.join((meta_pack.get('primary_keywords') or [])[:6]))}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family={google_fonts}&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: {_esc(palette['bg'])};
      --panel: {_esc(palette['panel'])};
      --accent: {_esc(palette['accent'])};
      --accent-2: {_esc(palette['accent_2'])};
      --text: {_esc(palette['text'])};
      --muted: {_esc(palette['muted'])};
      --btn-fg: {_esc(btn_fg)};
      --line: color-mix(in srgb, var(--text) 14%, transparent);
      --display: "{_esc(display_font)}", Georgia, serif;
      --body: "{_esc(body_font)}", system-ui, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--text);
      font-family: var(--body);
      background: var(--bg);
      line-height: 1.5;
      overflow-x: hidden;
    }}
    body::before {{
      content: "";
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(60% 50% at 15% 10%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 60%),
        radial-gradient(50% 45% at 90% 0%, color-mix(in srgb, var(--accent-2) 22%, transparent), transparent 55%),
        radial-gradient(40% 40% at 70% 80%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 60%);
      animation: drift 18s ease-in-out infinite alternate;
    }}
    @keyframes drift {{
      from {{ transform: translate3d(0,0,0) scale(1); }}
      to {{ transform: translate3d(-2%, 1.5%, 0) scale(1.05); }}
    }}
    a {{ color: inherit; text-decoration: none; }}
    .wrap {{ position: relative; z-index: 1; }}
    .nav {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 22px clamp(18px, 4vw, 48px);
      position: sticky; top: 0; z-index: 20;
      backdrop-filter: blur(16px);
      background: color-mix(in srgb, var(--bg) 72%, transparent);
    }}
    .brand {{
      font-family: var(--display);
      font-weight: 700; font-size: 1.15rem; letter-spacing: -0.03em;
    }}
    .nav-links {{
      display: flex; align-items: center; gap: 18px;
      font-size: 0.92rem; font-weight: 500;
    }}
    .nav-links a {{ opacity: 0.78; }}
    .nav-links a:hover {{ opacity: 1; }}
    .nav-cta {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 11px 18px; border-radius: 999px;
      background: var(--text); color: var(--bg);
      font-weight: 600; font-size: 0.92rem;
      transition: transform .2s ease, opacity .2s ease;
      opacity: 1 !important;
    }}
    .nav-cta:hover {{ transform: translateY(-1px); opacity: .92 !important; }}
    .hero {{
      min-height: 92vh;
      display: grid;
      align-content: end;
      padding: clamp(28px, 6vw, 72px) clamp(18px, 4vw, 48px) 48px;
      position: relative;
    }}
    .hero--split {{
      align-items: center;
      align-content: center;
      grid-template-columns: 1.05fr 0.95fr;
      gap: clamp(24px, 4vw, 56px);
    }}
    .hero--centered {{
      align-content: center;
      justify-items: center;
      text-align: center;
    }}
    .hero--centered .hero-copy {{ max-width: 28ch; }}
    .hero--centered .lede {{ margin-inline: auto; }}
    .hero--centered .cta-row {{ justify-content: center; }}
    .hero-panel {{ position: relative; min-height: min(62vh, 560px); }}
    .hero--split .hero-bg {{
      position: absolute; inset: 0;
      border-radius: 28px 28px 28px 80px;
    }}
    .hero--cinematic .hero-bg {{
      position: absolute; inset: 8% 4% 18% 42%;
      border-radius: 32px;
    }}
    .hero-bg {{
      background:
        linear-gradient(145deg,
          color-mix(in srgb, var(--accent) 85%, #000),
          color-mix(in srgb, var(--accent-2) 55%, var(--accent)));
      filter: saturate(1.1);
      animation: floaty 9s ease-in-out infinite alternate;
      overflow: hidden;
    }}
    .hero-bg--photo {{
      animation: none; filter: none;
      background: var(--panel);
    }}
    .hero-bg--photo img {{
      width: 100%; height: 100%; object-fit: cover; display: block;
      transform: scale(1.03);
    }}
    .hero-bg--photo::after {{
      content: "";
      position: absolute; inset: 0;
      background:
        linear-gradient(160deg, color-mix(in srgb, var(--bg) 15%, transparent), color-mix(in srgb, var(--bg) 45%, transparent)),
        radial-gradient(circle at 30% 20%, rgba(255,255,255,.18), transparent 40%);
    }}
    .hero--centered .hero-bg--wash {{
      position: absolute; inset: 8% 10% 18% 10%;
      border-radius: 32px; opacity: .55;
    }}
    .hero-bg::after {{
      content: "";
      position: absolute; inset: -20%;
      background:
        radial-gradient(circle at 30% 20%, rgba(255,255,255,.25), transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(0,0,0,.25), transparent 45%);
    }}
    .hero-bg--photo::after {{ inset: 0; }}
    .gallery-grid {{
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px;
    }}
    .gallery-cell {{
      margin: 0; border-radius: 24px; overflow: hidden;
      border: 1px solid var(--line); background: var(--panel);
      aspect-ratio: 4/5;
    }}
    .gallery-cell img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .gallery-cell figcaption {{
      position: absolute; left: 12px; bottom: 12px;
      padding: 6px 10px; border-radius: 999px;
      background: color-mix(in srgb, var(--bg) 72%, transparent);
      font-size: 0.72rem; font-weight: 600;
    }}
    .gallery-cell {{ position: relative; }}
    {accent_3d_css()}
    @keyframes floaty {{
      from {{ transform: translateY(0) rotate(-1deg); }}
      to {{ transform: translateY(-12px) rotate(1.2deg); }}
    }}
    .hero-copy {{ position: relative; z-index: 2; max-width: 22ch; }}
    .eyebrow {{
      margin: 0 0 14px;
      font-size: 0.78rem; font-weight: 700;
      letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--accent-2);
    }}
    .brand-mark {{
      font-family: var(--display);
      font-size: clamp(2.6rem, 7vw, 5.5rem);
      font-weight: 700;
      letter-spacing: -0.04em;
      line-height: 0.92;
      margin: 0 0 18px;
      background: linear-gradient(120deg, var(--text), color-mix(in srgb, var(--accent-2) 70%, var(--text)));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }}
    .hero h1 {{
      font-family: var(--display);
      font-size: clamp(1.7rem, 3.6vw, 2.8rem);
      font-weight: 700;
      letter-spacing: -0.03em;
      line-height: 1.12;
      margin: 0 0 16px;
      max-width: 18ch;
      color: var(--text);
    }}
    .hero .lede {{
      margin: 0 0 28px;
      color: var(--muted);
      font-size: clamp(1rem, 1.5vw, 1.15rem);
      max-width: 34em;
    }}
    .cta-row {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .btn {{
      display: inline-flex; align-items: center; justify-content: center;
      padding: 14px 22px; border-radius: 999px;
      background: var(--accent); color: var(--btn-fg); font-weight: 600;
      border: 0; transition: transform .2s ease, box-shadow .2s ease;
    }}
    .btn:hover {{ transform: translateY(-2px); box-shadow: 0 18px 40px color-mix(in srgb, var(--accent) 35%, transparent); }}
    .btn.ghost {{
      background: transparent; color: var(--text);
      border: 1px solid var(--line);
    }}
    .marquee {{
      border-block: 1px solid var(--line);
      padding: 16px 0;
      overflow: hidden;
      white-space: nowrap;
      background: color-mix(in srgb, var(--panel) 40%, transparent);
    }}
    .marquee-track {{
      display: inline-flex; gap: 28px; align-items: center;
      animation: scroll 28s linear infinite;
      font-family: var(--display);
      font-weight: 700; letter-spacing: -0.02em;
      font-size: 1.05rem;
      padding-left: 100%;
    }}
    .marquee .dot {{ color: var(--accent-2); opacity: .85; }}
    @keyframes scroll {{
      from {{ transform: translateX(0); }}
      to {{ transform: translateX(-50%); }}
    }}
    section {{ padding: clamp(48px, 8vw, 96px) clamp(18px, 4vw, 48px); }}
    .section-kicker {{
      color: var(--accent-2); font-size: 0.78rem; font-weight: 700;
      letter-spacing: 0.12em; text-transform: uppercase; margin: 0 0 12px;
    }}
    .section-title {{
      font-family: var(--display);
      font-size: clamp(2rem, 4.5vw, 3.4rem);
      letter-spacing: -0.04em; line-height: 1.02;
      margin: 0 0 14px; max-width: 14ch;
    }}
    .section-sub {{ color: var(--muted); max-width: 36em; margin: 0 0 36px; }}
    .mosaic {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .tile {{
      padding: 28px;
      border-radius: 28px;
      background: color-mix(in srgb, var(--panel) 88%, transparent);
      border: 1px solid var(--line);
      min-height: 200px;
      transition: transform .25s ease, border-color .25s ease;
    }}
    .tile:hover {{ transform: translateY(-4px); border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); }}
    .tile:nth-child(2), .tile:nth-child(3) {{ background: color-mix(in srgb, var(--accent) 12%, var(--panel)); }}
    .tile-n {{ color: var(--accent-2); font-size: 0.75rem; font-weight: 700; letter-spacing: .08em; }}
    .tile h3 {{
      font-family: var(--display); margin: 14px 0 10px;
      font-size: 1.45rem; letter-spacing: -0.03em;
    }}
    .tile p {{ margin: 0; color: var(--muted); }}
    .about-split {{
      display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 28px; align-items: center;
    }}
    .about-split h2 {{
      font-family: var(--display);
      font-size: clamp(2rem, 4vw, 3.2rem);
      letter-spacing: -0.04em; margin: 0 0 16px; line-height: 1.05;
    }}
    .about-split p {{ color: var(--muted); font-size: 1.05rem; margin: 0; }}
    .ref-shot {{
      position: relative; border-radius: 28px; overflow: hidden;
      border: 1px solid var(--line); aspect-ratio: 4/3;
      background: var(--panel);
    }}
    .ref-shot img {{ width: 100%; height: 100%; object-fit: cover; display: block; opacity: .9; }}
    .ref-shot span {{
      position: absolute; left: 14px; bottom: 14px;
      padding: 6px 10px; border-radius: 999px;
      background: color-mix(in srgb, var(--bg) 75%, transparent);
      font-size: 0.75rem; font-weight: 600;
    }}
    .ref-fallback {{
      min-height: 280px; border-radius: 28px;
      background:
        linear-gradient(160deg, var(--accent), color-mix(in srgb, var(--accent-2) 70%, var(--accent)));
    }}
    .rail {{
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
    }}
    .rail-item {{
      padding: 20px; border-top: 2px solid var(--accent);
    }}
    .rail-item span {{ color: var(--accent-2); font-size: 0.75rem; font-weight: 700; }}
    .rail-item strong {{
      display: block; margin: 8px 0 6px;
      font-family: var(--display); font-size: 1.2rem; letter-spacing: -0.03em;
    }}
    .rail-item p {{ margin: 0; color: var(--muted); font-size: 0.92rem; }}
    .finale {{
      margin: 12px clamp(18px, 4vw, 48px) 48px;
      padding: clamp(36px, 6vw, 64px);
      border-radius: 36px;
      background: var(--text); color: var(--bg);
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      gap: clamp(28px, 4vw, 48px);
      align-items: start;
    }}
    .finale h2 {{
      font-family: var(--display);
      font-size: clamp(2rem, 4.5vw, 3.2rem);
      letter-spacing: -0.04em; margin: 0 0 12px; max-width: 16ch; line-height: 1.05;
    }}
    .finale .pitch {{ margin: 0 0 18px; opacity: 0.78; font-size: 1.05rem; max-width: 36ch; }}
    .contact-meta {{
      display: flex; flex-wrap: wrap; gap: 10px 18px;
      font-size: 0.9rem; margin-bottom: 20px; opacity: 0.85;
    }}
    .contact-meta a {{ color: inherit; }}
    .improve {{
      margin: 0; padding: 0; list-style: none; display: grid; gap: 8px;
    }}
    .improve li {{
      position: relative; padding-left: 18px; font-size: 0.92rem; opacity: 0.85;
    }}
    .improve li::before {{
      content: ""; position: absolute; left: 0; top: 0.55em;
      width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
    }}
    .contact-form {{
      display: grid; gap: 12px;
      padding: 22px;
      border-radius: 24px;
      background: color-mix(in srgb, var(--bg) 8%, transparent);
      border: 1px solid color-mix(in srgb, var(--bg) 16%, transparent);
    }}
    .contact-form label {{
      display: grid; gap: 6px; font-size: 0.78rem; font-weight: 600;
      letter-spacing: 0.04em; text-transform: uppercase; opacity: 0.7;
    }}
    .contact-form input,
    .contact-form textarea,
    .contact-form select {{
      width: 100%; border: 1px solid color-mix(in srgb, var(--bg) 22%, transparent);
      border-radius: 12px; padding: 12px 14px;
      background: color-mix(in srgb, var(--bg) 6%, transparent);
      color: inherit; font: inherit; outline: none;
    }}
    .contact-form textarea {{ min-height: 110px; resize: vertical; }}
    .contact-form .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .finale .btn {{
      background: var(--accent); color: var(--btn-fg); width: fit-content;
      border: 0; cursor: pointer; margin-top: 4px;
    }}
    .form-note {{ font-size: 0.78rem; opacity: 0.55; margin: 0; }}
    details.agency {{
      margin: 0 clamp(18px, 4vw, 48px) 48px;
      border: 1px solid var(--line); border-radius: 24px; padding: 18px 20px;
      background: color-mix(in srgb, var(--panel) 70%, transparent);
    }}
    details.agency summary {{
      cursor: pointer; font-weight: 600; font-family: var(--display);
      letter-spacing: -0.02em;
    }}
    .notes {{ display: grid; gap: 12px; margin-top: 16px; }}
    .note {{ display: grid; gap: 4px; padding-top: 12px; border-top: 1px solid var(--line); }}
    .note span {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: .08em; color: var(--accent-2); }}
    .note em {{ font-style: normal; color: var(--muted); font-size: 0.88rem; }}
    .footer {{
      display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
      padding: 0 clamp(18px, 4vw, 48px) 40px;
      color: var(--muted); font-size: 0.8rem;
    }}
    .reveal {{
      opacity: 0; transform: translateY(18px);
      transition: opacity .7s ease, transform .7s ease;
      transition-delay: var(--d, 0s);
    }}
    .reveal.in {{ opacity: 1; transform: none; }}
    @media (max-width: 900px) {{
      .hero--cinematic .hero-bg {{ inset: auto 12px 12px 12px; height: 38vh; }}
      .hero--cinematic {{ min-height: 100vh; padding-bottom: 44vh; }}
      .hero--split {{ grid-template-columns: 1fr; }}
      .brand-mark {{ max-width: 12ch; }}
      .mosaic, .about-split, .rail, .finale, .contact-form .row, .gallery-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="nav">
      <div class="brand">{_esc(brand)}</div>
      <nav class="nav-links" aria-label="Sections">
        <a href="#work">Work</a>
        <a href="#process">Process</a>
        <a class="nav-cta" href="#contact">{_esc(cta)}</a>
      </nav>
    </header>

    {hero_block}

    <div class="marquee" aria-hidden="true">
      <div class="marquee-track">{marquee_items} {marquee_items}</div>
    </div>

    <section id="work">
      <p class="section-kicker">{_esc(services_kicker)}</p>
      <h2 class="section-title">{_esc(services_title)}</h2>
      <p class="section-sub">Service lines from the live site story — rewritten for a modern first impression.</p>
      <div class="mosaic">
        {service_tiles}
      </div>
    </section>

    {gallery_html}

    <section>
      <div class="about-split">
        <div class="reveal">
          <p class="section-kicker">{_esc(about_kicker)}</p>
          <h2>A clearer story for {_esc(brand)}</h2>
          <p>{_esc(about)}</p>
        </div>
        {shot}
      </div>
    </section>

    <section id="process">
      <p class="section-kicker">{_esc(process_kicker)}</p>
      <h2 class="section-title">{_esc(process_title)}</h2>
      <div class="rail">
        {process_row}
      </div>
    </section>

    <section class="finale" id="contact">
      <div>
        <h2>{_esc(contact_title)}</h2>
        <p class="pitch">{_esc(contact_pitch)}</p>
        {contact_meta}
        <p class="section-kicker" style="color:inherit;opacity:.55;margin:0 0 10px">Priority improvements</p>
        <ul class="improve">
          {improve_items}
        </ul>
      </div>
      <form class="contact-form" action="#" method="get" onsubmit="event.preventDefault(); this.querySelector('.form-note').textContent='Demo only — message not sent. In a live build this would reach the studio.';">
        <div class="row">
          <label>Name<input name="name" type="text" autocomplete="name" placeholder="Your name" required /></label>
          <label>Email<input name="email" type="email" autocomplete="email" placeholder="you@company.com" required /></label>
        </div>
        <label>Project type
          <select name="type">
            <option>Website redesign</option>
            <option>New landing page</option>
            <option>Ongoing retainer</option>
            <option>Something else</option>
          </select>
        </label>
        <label>What should we help with?<textarea name="message" placeholder="Goals, timeline, anything we should know…"></textarea></label>
        <button class="btn" type="submit">{_esc(cta)}</button>
        <p class="form-note">Demo contact form — wired for show, not delivery.</p>
      </form>
    </section>

    <details class="agency">
      <summary>Agency notes · content suggestions</summary>
      <div class="notes">
        {note_rows}
      </div>
    </details>

    <details class="agency">
      <summary>Social ideas · soundtrack references</summary>
      <div class="notes">
        {social_rows or '<div class="note"><span>Social</span><strong>Ask Brain to generate social content for this brand.</strong></div>'}
        <div class="note">
          <span>Note</span>
          <em>{_esc(social.get("music_disclaimer") or "Verify Reels/TikTok audio clearance before publishing.")}</em>
        </div>
      </div>
    </details>

    <footer class="footer">
      <span>Demo for {_esc(domain)}</span>
      <span>{_esc(credit_line) if credit_line else "Open-source visuals · Unsplash License"}</span>
    </footer>
  </div>
  <script>
    const io = new IntersectionObserver((entries) => {{
      entries.forEach((e) => {{ if (e.isIntersecting) e.target.classList.add('in'); }});
    }}, {{ threshold: 0.12 }});
    document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
  </script>
</body>
</html>
"""


def generate_demo_site(
    root: Path,
    *,
    domain: str,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    design_brief: dict | None = None,
    opportunities: list[dict] | None = None,
) -> dict:
    """Write demo/index.html + manifest from brain/brief inputs."""
    out_dir = root / DEMO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not evidence_pack:
        evidence_pack = _load_json(root / "evidence" / "evidence_pack.json")
    if not recommendations:
        recommendations = _load_json(root / "evidence" / "recommendations.json")
    if opportunities is None:
        opp_doc = _load_json(root / "evidence" / "opportunities.json") or {}
        opportunities = list(opp_doc.get("opportunities") or [])

    brief = design_brief or _load_json(root / "design" / "brief.json") or {}
    if not brief.get("palette") or not brief.get("headline"):
        brief = build_design_brief(
            root,
            recommendations=recommendations,
            evidence_pack=evidence_pack,
        )

    # Brain theme → open-source photos + 3D accents, cached under demo/media/
    from backend.app.services.visual_assets import materialize_visuals

    direction = brief.get("design_direction") or {}
    if not isinstance(direction, dict):
        direction = {}
    recs_inner = (recommendations or {}).get("recommendations") or recommendations or {}
    if not direction and isinstance(recs_inner, dict):
        direction = recs_inner.get("design_direction") or {}
    theme_key = brief.get("theme") or direction.get("theme")
    visuals = materialize_visuals(
        root,
        theme=str(theme_key or ""),
        visual_override=direction.get("visuals")
        if isinstance(direction.get("visuals"), dict)
        else None,
    )

    pack_story = (evidence_pack or {}).get("site_story") or _load_json(
        root / "seo" / "site_story.json"
    ) or {}
    story = _story_bits(recommendations, evidence_pack)
    if brief.get("brand_name"):
        story["business"] = brief["brand_name"]
    improvements = _improvement_suggestions(recommendations, opportunities)
    content = brief.get("content_suggestions") or _content_suggestions(
        story, recommendations, brief
    )
    services = _marketing_services(story, content, brief=brief, pack_story=pack_story)
    process = _process_steps(story)
    contact = _contact_bits(story, pack_story, opportunities)
    screenshot_rel = reference_screenshot_path(root, evidence_pack)

    # Prefer marketing headline in brief for manifest / downstream reuse
    picked_headline = _pick_headline(brief, content, story)
    picked_sub = _pick_subheadline(brief, content, story)
    brief = {
        **brief,
        "headline": picked_headline,
        "subheadline": picked_sub,
        "visuals": visuals,
    }

    html_doc = _render_html(
        domain=domain,
        brief=brief,
        story=story,
        improvements=improvements,
        services=services,
        content_suggestions=content,
        process=process,
        contact=contact,
        screenshot_rel=screenshot_rel,
    )
    index_path = root / INDEX_FILENAME
    index_path.write_text(html_doc, encoding="utf-8")

    manifest = {
        "version": 3,
        "generated_at": _now(),
        "domain": domain,
        "path": INDEX_FILENAME,
        "url_path": f"/data/websites/{domain}/crawls/{root.name}/{INDEX_FILENAME}",
        "headline": picked_headline,
        "subheadline": picked_sub,
        "cta": brief.get("cta"),
        "suggestions": improvements,
        "content_suggestions": content,
        "services": services,
        "contact": contact,
        "palette": _brief_palette(brief),
        "theme": brief.get("theme"),
        "hero_variant": brief.get("hero_variant"),
        "design_reasoning": brief.get("design_reasoning")
        or ((brief.get("design_direction") or {}).get("reasoning")),
        "visuals": {
            "hero": (visuals.get("hero") or {}).get("path"),
            "supporting": [s.get("path") for s in (visuals.get("supporting") or [])],
            "accent_3d": visuals.get("accent_3d"),
            "credits": visuals.get("credits") or [],
            "license": visuals.get("license"),
        },
        "content_metadata": brief.get("content_metadata")
        if isinstance(brief.get("content_metadata"), dict)
        else {},
        "notes": (
            "Clickable multi-section demo driven by Brain design_direction "
            "(theme + open-source Unsplash photos + CSS 3D accents + content metadata)."
        ),
    }
    (root / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest
