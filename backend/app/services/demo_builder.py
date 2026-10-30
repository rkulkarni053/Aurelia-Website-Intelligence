"""Generative demo builder — Base44-style local loop.

User prompt
  → Qwen creates a site specification (sections)
  → Select components from a registry
  → Generate HTML
  → Playwright screenshot + page extract
  → Qwen examines result (VL if available, else DOM text)
  → Fix problems
  → Done
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.database import settings
from backend.app.services.demo_site import DEMO_DIR, INDEX_FILENAME, MANIFEST_FILENAME, load_demo
from backend.app.services.llm_client import LLMError, chat_json, chat_text
from backend.app.services.playwright_env import ensure_playwright_browsers_path

BUILD_DIR = "demo"
SPEC_FILENAME = "demo/site_spec.json"
PREVIEW_FILENAME = "demo/preview-desktop.png"
BUILD_LOG = "demo/build_log.json"

SECTION_TYPES = (
    "hero",
    "menu",
    "services",
    "about",
    "gallery",
    "process",
    "reservations",
    "testimonials",
    "contact",
    "footer",
)

COMPONENT_VARIANTS: dict[str, list[str]] = {
    "hero": ["cinematic", "split", "centered"],
    "menu": ["cards", "list"],
    "services": ["cards", "mosaic"],
    "about": ["split", "stack"],
    "gallery": ["grid", "strip"],
    "process": ["rail", "steps"],
    "reservations": ["form", "cta_band"],
    "testimonials": ["quotes"],
    "contact": ["form_split", "simple"],
    "footer": ["minimal"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def looks_like_build_prompt(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    starters = (
        "build me",
        "build a",
        "create a",
        "create me",
        "make me a",
        "make a website",
        "generate a",
        "design a website",
        "new website for",
        "scaffold",
    )
    return any(text.startswith(s) or f" {s} " in f" {text} " for s in starters)


def prompt_to_site_spec(
    prompt: str,
    *,
    context: dict | None = None,
    model: str | None = None,
) -> dict:
    """Step 1: Qwen turns the user request into a structured site specification."""
    model = model or settings.ollama_model
    system = (
        "You are a website product designer. Return ONLY valid JSON for a one-page "
        "marketing site specification. No markdown.\n"
        "Schema:\n"
        "{"
        '"brand":"string","tagline":"string","industry":"string",'
        '"palette":{"bg":"#hex","panel":"#hex","accent":"#hex","accent_2":"#hex","text":"#hex","muted":"#hex"},'
        '"sections":[{"type":"hero|menu|services|about|gallery|process|reservations|testimonials|contact|footer",'
        '"variant":"string","headline":"string","body":"string","cta":"string",'
        '"items":[{"title":"string","body":"string","price":"string"}]}]'
        "}\n"
        "Rules: 5-8 sections. Always include hero + contact (or reservations). "
        "Benefit-led headlines. Hex colors only. Match the user's industry."
    )
    user = f"Build this website:\n{prompt.strip()}"
    if context:
        user += "\n\nOptional crawl context (do not invent contradictions):\n"
        user += json.dumps(context, ensure_ascii=True)[:2500]

    try:
        parsed, _provider, _model = chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            provider="ollama",
            model=model,
            temperature=0.35,
            max_tokens=1600,
            timeout=float(getattr(settings, "ollama_timeout_seconds", 180) or 180),
        )
    except LLMError:
        parsed = _fallback_spec(prompt)

    return normalize_spec(parsed, prompt=prompt)


def _fallback_spec(prompt: str) -> dict:
    low = (prompt or "").lower()
    if any(k in low for k in ("restaurant", "cafe", "bistro", "dining", "menu")):
        brand = "Harbor Table"
        industry = "restaurant"
        sections = [
            {
                "type": "hero",
                "variant": "cinematic",
                "headline": "Seasonal plates. Warm light. Open late.",
                "body": "A neighborhood restaurant for long dinners and easy reservations.",
                "cta": "Reserve a table",
            },
            {
                "type": "menu",
                "variant": "cards",
                "headline": "Tonight’s menu",
                "items": [
                    {"title": "Wood-fired catch", "body": "Citrus, herbs, charcoal.", "price": "€24"},
                    {"title": "Garden pasta", "body": "Tomato, ricotta, basil.", "price": "€18"},
                    {"title": "Chocolate tart", "body": "Sea salt, olive oil.", "price": "€10"},
                ],
            },
            {
                "type": "about",
                "variant": "split",
                "headline": "Cooked with patience",
                "body": "We source from local boats and farms, and keep the room intimate.",
            },
            {
                "type": "gallery",
                "variant": "grid",
                "headline": "From the pass",
                "items": [{"title": "Grill"}, {"title": "Wine"}, {"title": "Room"}],
            },
            {
                "type": "reservations",
                "variant": "form",
                "headline": "Book your table",
                "body": "Evenings Thu–Sun. Parties of 6+ on request.",
                "cta": "Request a reservation",
            },
            {
                "type": "contact",
                "variant": "simple",
                "headline": "Find us",
                "body": "Open kitchen · Harbor street · +00 000 000",
            },
        ]
    else:
        brand = "Studio North"
        industry = "agency"
        sections = [
            {
                "type": "hero",
                "variant": "cinematic",
                "headline": "Clearer story. Stronger first impression.",
                "body": "A modern one-page presence built from your brief.",
                "cta": "Start a project",
            },
            {
                "type": "services",
                "variant": "cards",
                "headline": "What we deliver",
                "items": [
                    {"title": "Brand", "body": "Positioning and visual direction."},
                    {"title": "Web", "body": "Conversion-led pages that ship."},
                    {"title": "Launch", "body": "QA, go-live, and iteration."},
                ],
            },
            {
                "type": "about",
                "variant": "split",
                "headline": "Built for clarity",
                "body": "We turn messy briefs into calm, persuasive sites.",
            },
            {
                "type": "process",
                "variant": "rail",
                "headline": "How we work",
                "items": [
                    {"title": "Discover", "body": "Goals and constraints."},
                    {"title": "Design", "body": "Structure and craft."},
                    {"title": "Build", "body": "Ship and verify."},
                ],
            },
            {
                "type": "contact",
                "variant": "form_split",
                "headline": "Let’s talk",
                "body": "Tell us about the project.",
                "cta": "Send message",
            },
        ]

    # Light brand guess from prompt quotes / trailing phrase
    m = re.search(r"(?:for|called)\s+[\"']?([A-Z][\w\s&-]{2,40})", prompt or "")
    if m:
        brand = m.group(1).strip()

    return {
        "brand": brand,
        "tagline": "Built with Aurelia demo builder",
        "industry": industry,
        "palette": {
            "bg": "#0f1412" if industry == "restaurant" else "#0b1020",
            "panel": "#1a211c" if industry == "restaurant" else "#11192d",
            "accent": "#c45c26" if industry == "restaurant" else "#e11d48",
            "accent_2": "#e8c47c" if industry == "restaurant" else "#fbbf24",
            "text": "#f7f3ea" if industry == "restaurant" else "#f8fafc",
            "muted": "#a39a8a" if industry == "restaurant" else "#94a3b8",
        },
        "sections": sections,
    }


def normalize_spec(raw: dict | None, *, prompt: str = "") -> dict:
    raw = raw if isinstance(raw, dict) else {}
    fallback = _fallback_spec(prompt)
    palette = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
    base_palette = dict(fallback["palette"])
    for k, v in palette.items():
        if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v.strip()):
            base_palette[k] = v.strip().lower()

    sections_in = raw.get("sections") if isinstance(raw.get("sections"), list) else []
    sections: list[dict] = []
    for item in sections_in:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "").strip().lower()
        if stype not in SECTION_TYPES:
            continue
        variants = COMPONENT_VARIANTS.get(stype) or ["default"]
        variant = str(item.get("variant") or variants[0]).strip().lower()
        if variant not in variants:
            variant = variants[0]
        items = []
        for row in item.get("items") or []:
            if isinstance(row, dict) and (row.get("title") or row.get("name")):
                items.append(
                    {
                        "title": str(row.get("title") or row.get("name"))[:60],
                        "body": str(row.get("body") or row.get("description") or "")[:180],
                        "price": str(row.get("price") or "")[:24],
                    }
                )
            if len(items) >= 8:
                break
        sections.append(
            {
                "type": stype,
                "variant": variant,
                "headline": str(item.get("headline") or item.get("title") or "")[:120],
                "body": str(item.get("body") or item.get("subcopy") or "")[:320],
                "cta": str(item.get("cta") or "")[:48],
                "items": items,
            }
        )

    if not sections:
        sections = list(fallback["sections"])

    # Ensure hero + closing contact/reservations
    types = {s["type"] for s in sections}
    if "hero" not in types:
        sections.insert(0, fallback["sections"][0])
    if "contact" not in types and "reservations" not in types:
        sections.append(fallback["sections"][-1])

    return {
        "brand": str(raw.get("brand") or fallback["brand"])[:60],
        "tagline": str(raw.get("tagline") or fallback["tagline"])[:120],
        "industry": str(raw.get("industry") or fallback["industry"])[:40],
        "palette": base_palette,
        "sections": sections[:10],
        "prompt": (prompt or "")[:500],
        "updated_at": _now(),
    }


def select_components(spec: dict) -> list[dict]:
    """Step 2: bind each section to a concrete component id + variant."""
    selected = []
    for section in spec.get("sections") or []:
        stype = section["type"]
        variants = COMPONENT_VARIANTS.get(stype) or ["default"]
        variant = section.get("variant") if section.get("variant") in variants else variants[0]
        selected.append(
            {
                **section,
                "variant": variant,
                "component": f"{stype}.{variant}",
            }
        )
    return selected


def _section_nav(sections: list[dict], brand: str, cta: str) -> str:
    links = []
    for s in sections:
        if s["type"] in {"hero", "footer"}:
            continue
        label = s["type"].replace("_", " ").title()
        links.append(f'<a href="#{_esc(s["type"])}">{_esc(label)}</a>')
    types = {s["type"] for s in sections}
    if "contact" in types:
        anchor = "contact"
    elif "reservations" in types:
        anchor = "reservations"
    else:
        anchor = "hero"
    return f"""
    <header class="nav">
      <div class="brand">{_esc(brand)}</div>
      <nav class="nav-links">{"".join(links)}
        <a class="nav-cta" href="#{_esc(anchor)}">{_esc(cta or "Contact")}</a>
      </nav>
    </header>
    """


def _render_hero(s: dict, brand: str, *, cta_href: str = "#contact") -> str:
    return f"""
    <section class="hero" id="hero">
      <div class="hero-bg" aria-hidden="true"></div>
      <div class="hero-copy">
        <p class="brand-mark">{_esc(brand)}</p>
        <h1>{_esc(s.get("headline") or brand)}</h1>
        <p class="lede">{_esc(s.get("body"))}</p>
        <div class="cta-row">
          <a class="btn" href="{_esc(cta_href)}">{_esc(s.get("cta") or "Get started")}</a>
        </div>
      </div>
    </section>
    """


def _render_cards(s: dict, *, price: bool = False) -> str:
    tiles = []
    for idx, item in enumerate(s.get("items") or [], start=1):
        price_html = (
            f'<span class="price">{_esc(item.get("price"))}</span>'
            if price and item.get("price")
            else ""
        )
        tiles.append(
            f'<article class="tile"><span class="tile-n">{idx:02d}</span>'
            f"<h3>{_esc(item.get('title'))}</h3>"
            f"<p>{_esc(item.get('body'))}</p>{price_html}</article>"
        )
    if not tiles:
        tiles.append(
            f'<article class="tile"><h3>{_esc(s.get("headline") or "Details")}</h3>'
            f"<p>{_esc(s.get('body'))}</p></article>"
        )
    return f"""
    <section id="{_esc(s["type"])}">
      <p class="section-kicker">{_esc(s["type"])}</p>
      <h2 class="section-title">{_esc(s.get("headline") or s["type"].title())}</h2>
      <p class="section-sub">{_esc(s.get("body"))}</p>
      <div class="mosaic">{"".join(tiles)}</div>
    </section>
    """


def _render_about(s: dict) -> str:
    return f"""
    <section id="about">
      <div class="about-split">
        <div>
          <p class="section-kicker">About</p>
          <h2>{_esc(s.get("headline") or "About")}</h2>
          <p>{_esc(s.get("body"))}</p>
        </div>
        <div class="ref-fallback" aria-hidden="true"></div>
      </div>
    </section>
    """


def _render_gallery(s: dict) -> str:
    cells = []
    for item in s.get("items") or [{"title": "One"}, {"title": "Two"}, {"title": "Three"}]:
        cells.append(
            f'<div class="gallery-cell"><span>{_esc(item.get("title") or "View")}</span></div>'
        )
    return f"""
    <section id="gallery">
      <p class="section-kicker">Gallery</p>
      <h2 class="section-title">{_esc(s.get("headline") or "Gallery")}</h2>
      <div class="gallery-grid">{"".join(cells)}</div>
    </section>
    """


def _render_process(s: dict) -> str:
    items = s.get("items") or [
        {"title": "Discover", "body": "Clarify goals."},
        {"title": "Design", "body": "Shape the page."},
        {"title": "Launch", "body": "Ship and verify."},
    ]
    row = "".join(
        f'<div class="rail-item"><span>{idx:02d}</span>'
        f"<strong>{_esc(i.get('title'))}</strong><p>{_esc(i.get('body'))}</p></div>"
        for idx, i in enumerate(items[:4], start=1)
    )
    return f"""
    <section id="process">
      <p class="section-kicker">Process</p>
      <h2 class="section-title">{_esc(s.get("headline") or "Process")}</h2>
      <div class="rail">{row}</div>
    </section>
    """


def _render_contact(s: dict, *, reservations: bool = False) -> str:
    sid = "reservations" if reservations else "contact"
    title = s.get("headline") or ("Reserve a table" if reservations else "Contact")
    cta = s.get("cta") or ("Request reservation" if reservations else "Send message")
    return f"""
    <section class="finale" id="{sid}">
      <div>
        <h2>{_esc(title)}</h2>
        <p class="pitch">{_esc(s.get("body"))}</p>
      </div>
      <form class="contact-form" action="#" method="get" onsubmit="event.preventDefault(); this.querySelector('.form-note').textContent='Demo only — not sent.';">
        <div class="row">
          <label>Name<input name="name" required placeholder="Your name" /></label>
          <label>Email<input name="email" type="email" required placeholder="you@company.com" /></label>
        </div>
        {"<label>Party size<select name='party'><option>2</option><option>4</option><option>6</option><option>8+</option></select></label>" if reservations else ""}
        <label>Message<textarea name="message" placeholder="Tell us more…"></textarea></label>
        <button class="btn" type="submit">{_esc(cta)}</button>
        <p class="form-note">Demo form — show only.</p>
      </form>
    </section>
    """


def generate_code(spec: dict, *, domain: str = "demo.local") -> str:
    """Step 3: turn selected components into a single HTML document."""
    sections = select_components(spec)
    palette = spec.get("palette") or {}
    brand = spec.get("brand") or "Brand"
    hero = next((s for s in sections if s["type"] == "hero"), {})
    primary_cta = hero.get("cta") or "Get started"
    types = {s["type"] for s in sections}
    cta_href = (
        "#reservations"
        if "reservations" in types and "contact" not in types
        else "#contact"
    )
    body_parts = [_section_nav(sections, brand, primary_cta)]
    for s in sections:
        if s["type"] == "hero":
            body_parts.append(_render_hero(s, brand, cta_href=cta_href))
        elif s["type"] == "menu":
            body_parts.append(_render_cards(s, price=True))
        elif s["type"] in {"services", "testimonials"}:
            body_parts.append(_render_cards(s))
        elif s["type"] == "about":
            body_parts.append(_render_about(s))
        elif s["type"] == "gallery":
            body_parts.append(_render_gallery(s))
        elif s["type"] == "process":
            body_parts.append(_render_process(s))
        elif s["type"] == "reservations":
            body_parts.append(_render_contact(s, reservations=True))
        elif s["type"] == "contact":
            body_parts.append(_render_contact(s))
        elif s["type"] == "footer":
            body_parts.append(
                f'<footer class="footer"><span>{_esc(spec.get("brand"))}</span>'
                f"<span>{_esc(s.get('body') or spec.get('tagline'))}</span></footer>"
            )
    if not any(s["type"] == "footer" for s in sections):
        body_parts.append(
            f'<footer class="footer"><span>Demo for {_esc(domain)}</span>'
            f"<span>{_esc(spec.get('tagline') or 'Aurelia generative demo')}</span></footer>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(brand)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: {_esc(palette.get("bg") or "#0b1020")};
      --panel: {_esc(palette.get("panel") or "#11192d")};
      --accent: {_esc(palette.get("accent") or "#e11d48")};
      --accent-2: {_esc(palette.get("accent_2") or "#fbbf24")};
      --text: {_esc(palette.get("text") or "#f8fafc")};
      --muted: {_esc(palette.get("muted") or "#94a3b8")};
      --line: color-mix(in srgb, var(--text) 14%, transparent);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0; color: var(--text);
      font-family: "Instrument Sans", system-ui, sans-serif;
      background: var(--bg); line-height: 1.5;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .nav {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 20px clamp(18px, 4vw, 48px); position: sticky; top: 0; z-index: 10;
      backdrop-filter: blur(14px);
      background: color-mix(in srgb, var(--bg) 75%, transparent);
    }}
    .brand {{ font-family: "Syne", sans-serif; font-weight: 800; letter-spacing: -0.04em; }}
    .nav-links {{ display: flex; gap: 16px; align-items: center; flex-wrap: wrap; font-size: 0.92rem; }}
    .nav-cta, .btn {{
      display: inline-flex; padding: 11px 18px; border-radius: 999px;
      background: var(--text); color: var(--bg); font-weight: 600; border: 0; cursor: pointer;
    }}
    .btn {{ background: var(--accent); color: #fff; }}
    .hero {{
      min-height: 88vh; display: grid; align-content: end;
      padding: clamp(28px, 6vw, 72px) clamp(18px, 4vw, 48px) 48px; position: relative;
    }}
    .hero-bg {{
      position: absolute; inset: 10% 6% 20% 40%; border-radius: 32px;
      background:
        radial-gradient(circle at 30% 30%, color-mix(in srgb, var(--accent) 55%, transparent), transparent 55%),
        linear-gradient(145deg, var(--panel), color-mix(in srgb, var(--accent-2) 35%, var(--bg)));
    }}
    .hero-copy {{ position: relative; max-width: 720px; }}
    .brand-mark {{
      font-family: "Syne", sans-serif; font-size: clamp(2.8rem, 8vw, 5.5rem);
      font-weight: 800; letter-spacing: -0.06em; margin: 0 0 12px; line-height: 0.95;
    }}
    h1 {{
      font-family: "Syne", sans-serif; font-size: clamp(2rem, 5vw, 3.4rem);
      letter-spacing: -0.045em; margin: 0 0 14px; line-height: 1.05; max-width: 16ch;
    }}
    .lede {{ color: var(--muted); font-size: 1.1rem; max-width: 40ch; }}
    .cta-row {{ display: flex; gap: 12px; margin-top: 22px; }}
    section {{ padding: 48px clamp(18px, 4vw, 48px); }}
    .section-kicker {{
      text-transform: uppercase; letter-spacing: .12em; font-size: .72rem;
      color: var(--accent-2); margin: 0 0 8px;
    }}
    .section-title, section h2 {{
      font-family: "Syne", sans-serif; letter-spacing: -0.04em;
      font-size: clamp(1.8rem, 4vw, 2.8rem); margin: 0 0 10px;
    }}
    .section-sub {{ color: var(--muted); max-width: 48ch; }}
    .mosaic {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px; margin-top: 22px;
    }}
    .tile {{
      padding: 20px; border: 1px solid var(--line); border-radius: 22px;
      background: color-mix(in srgb, var(--panel) 80%, transparent);
    }}
    .tile-n {{ color: var(--accent-2); font-size: .75rem; font-weight: 700; }}
    .tile h3 {{ font-family: "Syne", sans-serif; margin: 8px 0; letter-spacing: -0.03em; }}
    .tile p {{ color: var(--muted); margin: 0; }}
    .price {{ display: inline-block; margin-top: 12px; font-weight: 700; color: var(--accent-2); }}
    .about-split {{
      display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 28px; align-items: center;
    }}
    .ref-fallback {{
      min-height: 280px; border-radius: 28px;
      background: linear-gradient(160deg, var(--accent), color-mix(in srgb, var(--accent-2) 70%, var(--accent)));
    }}
    .gallery-grid {{
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px;
    }}
    .gallery-cell {{
      aspect-ratio: 4/3; border-radius: 20px; display: grid; place-items: end start;
      padding: 14px; border: 1px solid var(--line);
      background:
        linear-gradient(180deg, transparent, color-mix(in srgb, var(--bg) 70%, transparent)),
        linear-gradient(135deg, var(--panel), color-mix(in srgb, var(--accent) 40%, var(--panel)));
    }}
    .rail {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .rail-item {{ padding: 18px; border-top: 2px solid var(--accent); }}
    .rail-item span {{ color: var(--accent-2); font-size: .75rem; font-weight: 700; }}
    .rail-item strong {{ display: block; margin: 8px 0 6px; font-family: "Syne", sans-serif; }}
    .rail-item p {{ margin: 0; color: var(--muted); }}
    .finale {{
      margin: 12px clamp(18px, 4vw, 48px) 48px; padding: clamp(28px, 5vw, 56px);
      border-radius: 36px; background: var(--text); color: var(--bg);
      display: grid; grid-template-columns: 1.1fr 1fr; gap: 28px;
    }}
    .finale h2 {{
      font-family: "Syne", sans-serif; font-size: clamp(2rem, 4vw, 3rem);
      letter-spacing: -0.05em; margin: 0 0 12px; max-width: 14ch; line-height: 1.05;
    }}
    .pitch {{ opacity: .78; }}
    .contact-form {{
      display: grid; gap: 12px; padding: 20px; border-radius: 24px;
      border: 1px solid color-mix(in srgb, var(--bg) 16%, transparent);
      background: color-mix(in srgb, var(--bg) 8%, transparent);
    }}
    .contact-form label {{
      display: grid; gap: 6px; font-size: .75rem; text-transform: uppercase;
      letter-spacing: .04em; opacity: .7; font-weight: 600;
    }}
    .contact-form input, .contact-form textarea, .contact-form select {{
      border-radius: 12px; border: 1px solid color-mix(in srgb, var(--bg) 22%, transparent);
      padding: 12px 14px; background: color-mix(in srgb, var(--bg) 6%, transparent);
      color: inherit; font: inherit;
    }}
    .contact-form textarea {{ min-height: 100px; }}
    .contact-form .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .form-note {{ font-size: .78rem; opacity: .55; margin: 0; }}
    .footer {{
      display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
      padding: 0 clamp(18px, 4vw, 48px) 40px; color: var(--muted); font-size: .8rem;
    }}
    @media (max-width: 900px) {{
      .about-split, .finale, .gallery-grid, .contact-form .row {{ grid-template-columns: 1fr; }}
      .hero-bg {{ inset: auto 12px 12px 12px; height: 34vh; }}
      .hero {{ padding-bottom: 40vh; }}
    }}
  </style>
</head>
<body>
  {"".join(body_parts)}
</body>
</html>
"""


def write_demo_artifacts(
    root: Path,
    *,
    domain: str,
    spec: dict,
    html_doc: str,
) -> dict:
    out_dir = root / BUILD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (root / INDEX_FILENAME).write_text(html_doc, encoding="utf-8")
    (root / SPEC_FILENAME).write_text(json.dumps(spec, indent=2), encoding="utf-8")
    manifest = {
        "version": 4,
        "builder": "generative",
        "generated_at": _now(),
        "domain": domain,
        "path": INDEX_FILENAME,
        "url_path": f"/data/websites/{domain}/crawls/{root.name}/{INDEX_FILENAME}",
        "headline": next(
            (s.get("headline") for s in spec.get("sections") or [] if s.get("type") == "hero"),
            spec.get("brand"),
        ),
        "cta": next(
            (s.get("cta") for s in spec.get("sections") or [] if s.get("type") == "hero"),
            "Get started",
        ),
        "sections": [s.get("component") or s.get("type") for s in select_components(spec)],
        "brand": spec.get("brand"),
        "industry": spec.get("industry"),
        "palette": spec.get("palette"),
        "preview": PREVIEW_FILENAME,
        "notes": "Generative demo: prompt → spec → components → HTML → Playwright QA loop.",
    }
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def screenshot_and_extract(html_path: Path, shot_path: Path) -> dict:
    """Step 4: Playwright renders local HTML, screenshots, extracts page text."""
    ensure_playwright_browsers_path()
    from playwright.sync_api import sync_playwright

    shot_path.parent.mkdir(parents=True, exist_ok=True)
    extract: dict[str, Any] = {
        "title": "",
        "h1": [],
        "headings": [],
        "links": [],
        "text_sample": "",
        "errors": [],
    }
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=45000)
            page.screenshot(path=str(shot_path), full_page=True)
            extract["title"] = page.title()
            extract["h1"] = page.eval_on_selector_all(
                "h1", "els => els.map(e => e.innerText.trim()).slice(0,3)"
            )
            extract["headings"] = page.eval_on_selector_all(
                "h1,h2,h3", "els => els.map(e => e.innerText.trim()).slice(0,20)"
            )
            extract["links"] = page.eval_on_selector_all(
                "a", "els => els.map(e => e.innerText.trim()).filter(Boolean).slice(0,20)"
            )
            extract["text_sample"] = page.inner_text("body")[:1800]
            browser.close()
    except Exception as exc:
        extract["errors"].append(str(exc))
    extract["screenshot"] = str(shot_path.name)
    return extract


def examine_result(
    *,
    prompt: str,
    spec: dict,
    extract: dict,
    root: Path,
    model: str | None = None,
) -> dict:
    """Step 5: Qwen examines Playwright output (VL screenshot if available)."""
    from backend.app.services.vision_review import pick_vision_model, review_screenshot

    model = model or settings.ollama_model
    issues: list[str] = []
    vision_notes = ""

    # Prefer vision model when installed
    if pick_vision_model() and (root / PREVIEW_FILENAME).is_file():
        try:
            vision = review_screenshot(
                root,
                PREVIEW_FILENAME,
                question=(
                    "Review this generated website screenshot for layout, hierarchy, "
                    "contrast, and whether it matches a polished one-page marketing site. "
                    "List concrete fixes only."
                ),
            )
            vision_notes = str((vision or {}).get("review") or "")[:1200]
        except Exception as exc:
            vision_notes = f"Vision unavailable: {exc}"

    system = (
        "You QA a generated one-page website. Return ONLY JSON: "
        '{"ok": false, "issues": ["..."], "spec_patch": {"sections": []}, '
        '"assistant_message": "short summary"}. '
        "If the page is good enough, ok=true and issues=[]. "
        "spec_patch may include palette and section headline/body/cta/items edits only."
    )
    user = {
        "user_prompt": prompt,
        "brand": spec.get("brand"),
        "industry": spec.get("industry"),
        "sections": [s.get("type") for s in spec.get("sections") or []],
        "playwright": {
            "title": extract.get("title"),
            "h1": extract.get("h1"),
            "headings": extract.get("headings"),
            "links": extract.get("links"),
            "text_sample": (extract.get("text_sample") or "")[:1200],
            "errors": extract.get("errors"),
        },
        "vision_notes": vision_notes,
    }
    try:
        parsed, _, _ = chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=True)},
            ],
            provider="ollama",
            model=model,
            temperature=0.2,
            max_tokens=900,
            timeout=120.0,
        )
    except LLMError:
        # Deterministic checks when model fails
        if not extract.get("h1"):
            issues.append("Missing H1 in hero")
        if extract.get("errors"):
            issues.append("Playwright could not fully render the page")
        if len(extract.get("headings") or []) < 3:
            issues.append("Too few section headings — page feels thin")
        return {
            "ok": not issues,
            "issues": issues,
            "spec_patch": {},
            "assistant_message": "Fallback QA from Playwright extract.",
            "vision_notes": vision_notes,
        }

    return {
        "ok": bool(parsed.get("ok")),
        "issues": [str(x) for x in (parsed.get("issues") or [])[:8]],
        "spec_patch": parsed.get("spec_patch") if isinstance(parsed.get("spec_patch"), dict) else {},
        "assistant_message": str(parsed.get("assistant_message") or "")[:400],
        "vision_notes": vision_notes,
    }


def apply_spec_patch(spec: dict, patch: dict | None) -> dict:
    """Step 6 helper: merge QA patch into spec."""
    if not isinstance(patch, dict) or not patch:
        return spec
    out = json.loads(json.dumps(spec))
    if isinstance(patch.get("palette"), dict):
        pal = dict(out.get("palette") or {})
        for k, v in patch["palette"].items():
            if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v.strip()):
                pal[k] = v.strip().lower()
        out["palette"] = pal
    for key in ("brand", "tagline"):
        if patch.get(key):
            out[key] = str(patch[key])[:80]
    patched_sections = patch.get("sections")
    if isinstance(patched_sections, list) and patched_sections:
        # Replace by type when provided, else append-normalized
        by_type = {s["type"]: s for s in out.get("sections") or []}
        for row in patched_sections:
            if not isinstance(row, dict):
                continue
            stype = str(row.get("type") or "").lower()
            if stype not in by_type:
                continue
            base = dict(by_type[stype])
            for field in ("headline", "body", "cta", "variant"):
                if row.get(field):
                    base[field] = str(row[field])[:320]
            if isinstance(row.get("items"), list) and row["items"]:
                base["items"] = row["items"][:8]
            by_type[stype] = base
        out["sections"] = list(by_type.values())
    return normalize_spec(out, prompt=str(out.get("prompt") or ""))


def build_demo_from_prompt(
    root: Path,
    prompt: str,
    *,
    domain: str,
    context: dict | None = None,
    max_fix_iters: int = 2,
    model: str | None = None,
) -> dict:
    """Full loop: prompt → spec → components → code → Playwright → examine → fix."""
    model = model or settings.ollama_model
    log: list[dict] = []

    spec = prompt_to_site_spec(prompt, context=context, model=model)
    log.append({"step": "specification", "at": _now(), "sections": [s["type"] for s in spec["sections"]]})

    components = select_components(spec)
    log.append(
        {
            "step": "select_components",
            "at": _now(),
            "components": [c["component"] for c in components],
        }
    )

    html_doc = generate_code(spec, domain=domain)
    manifest = write_demo_artifacts(root, domain=domain, spec=spec, html_doc=html_doc)
    log.append({"step": "generate_code", "at": _now(), "path": INDEX_FILENAME})

    html_path = root / INDEX_FILENAME
    shot_path = root / PREVIEW_FILENAME
    extract = screenshot_and_extract(html_path, shot_path)
    log.append(
        {
            "step": "playwright",
            "at": _now(),
            "screenshot": PREVIEW_FILENAME,
            "h1": extract.get("h1"),
            "errors": extract.get("errors"),
        }
    )

    for i in range(max(0, max_fix_iters)):
        qa = examine_result(
            prompt=prompt, spec=spec, extract=extract, root=root, model=model
        )
        log.append(
            {
                "step": "examine",
                "at": _now(),
                "iter": i + 1,
                "ok": qa.get("ok"),
                "issues": qa.get("issues"),
            }
        )
        if qa.get("ok") or not qa.get("issues"):
            break
        spec = apply_spec_patch(spec, qa.get("spec_patch"))
        # If model returned issues but empty patch, apply light deterministic fixes
        if not qa.get("spec_patch"):
            hero = next((s for s in spec["sections"] if s["type"] == "hero"), None)
            if hero and (not extract.get("h1") or not hero.get("headline")):
                hero["headline"] = hero.get("headline") or f"{spec['brand']} — built for clarity"
        html_doc = generate_code(spec, domain=domain)
        manifest = write_demo_artifacts(root, domain=domain, spec=spec, html_doc=html_doc)
        extract = screenshot_and_extract(html_path, shot_path)
        log.append({"step": "fix", "at": _now(), "iter": i + 1})

    (root / BUILD_LOG).write_text(json.dumps({"steps": log}, indent=2), encoding="utf-8")
    manifest = load_demo(root) or manifest
    manifest["build_steps"] = log
    manifest["preview_url"] = f"/data/websites/{domain}/crawls/{root.name}/{PREVIEW_FILENAME}"
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    section_names = ", ".join(s["type"] for s in spec.get("sections") or [])
    assistant = (
        f"Built a generative demo for **{spec.get('brand')}** "
        f"({spec.get('industry')}) with sections: {section_names}. "
        f"Ran Playwright preview"
        + (" and applied QA fixes." if any(s.get("step") == "fix" for s in log) else ".")
    )
    return {
        "demo": manifest,
        "site_spec": spec,
        "build_steps": log,
        "assistant_message": assistant,
        "preview": PREVIEW_FILENAME,
        "source": "demo_builder",
        "model": model,
    }
