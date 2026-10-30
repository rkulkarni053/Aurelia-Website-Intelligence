"""Per-site design tokens: palette from crawl analysis + brain copy for demos/mockups."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from backend.app.services.brain import rule_based_recommendations

# Seeded palettes when crawl HTML has no usable colors (still unique per domain).
DOMAIN_PALETTES = [
    {
        "bg": "#0a0f14",
        "panel": "#121a22",
        "accent": "#e11d48",
        "accent_2": "#fbbf24",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "mode": "dark",
    },
    {
        "bg": "#f7f4ef",
        "panel": "#ffffff",
        "accent": "#0f3d3e",
        "accent_2": "#c45c26",
        "text": "#14201f",
        "muted": "#5c6b6a",
        "mode": "light",
    },
    {
        "bg": "#0b1020",
        "panel": "#151d33",
        "accent": "#6366f1",
        "accent_2": "#34d399",
        "text": "#f5f7fb",
        "muted": "#8d98b5",
        "mode": "dark",
    },
    {
        "bg": "#fff7ed",
        "panel": "#ffffff",
        "accent": "#c2410c",
        "accent_2": "#0369a1",
        "text": "#1c1917",
        "muted": "#78716c",
        "mode": "light",
    },
    {
        "bg": "#020617",
        "panel": "#0f172a",
        "accent": "#38bdf8",
        "accent_2": "#a78bfa",
        "text": "#e2e8f0",
        "muted": "#64748b",
        "mode": "dark",
    },
    {
        "bg": "#ecfdf5",
        "panel": "#ffffff",
        "accent": "#047857",
        "accent_2": "#0ea5e9",
        "text": "#064e3b",
        "muted": "#6b7280",
        "mode": "light",
    },
]

SERVICE_TITLE_RE = re.compile(
    r"^[A-Z][A-Za-z0-9\-/& ]{4,55}(?:Services|Events|Facilities|Production|Streaming|Broadcasting|Commercials)\b"
)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _is_neutral(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    if max(r, g, b) - min(r, g, b) < 18:
        return True
    if _luminance(rgb) > 0.92 or _luminance(rgb) < 0.08:
        return True
    return False


def _pick_palette_seed(domain: str, story_text: str = "") -> dict:
    blob = (domain + " " + story_text).lower()
    if any(k in blob for k in ("video", "broadcast", "stream", "film", "production", "media")):
        # Cinematic dark default for production brands.
        return DOMAIN_PALETTES[0]
    idx = int(hashlib.sha256(domain.encode()).hexdigest(), 16) % len(DOMAIN_PALETTES)
    return DOMAIN_PALETTES[idx]


def _extract_colors_from_text(text: str) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    for match in re.finditer(r"#([0-9a-fA-F]{3,8})\b", text or ""):
        rgb = _hex_to_rgb("#" + match.group(1))
        if rgb:
            colors.append(rgb)
    for match in re.finditer(
        r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", text or ""
    ):
        colors.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return colors


def _dominant_colors_from_image(path: Path, limit: int = 4) -> list[tuple[int, int, int]]:
    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((160, 100))
        pixels = list(img.getdata())
    except OSError:
        return []
    counts: dict[tuple[int, int, int], int] = {}
    for rgb in pixels:
        bucket = (rgb[0] // 24 * 24, rgb[1] // 24 * 24, rgb[2] // 24 * 24)
        counts[bucket] = counts.get(bucket, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    out: list[tuple[int, int, int]] = []
    for rgb, _ in ranked:
        if _is_neutral(rgb):
            continue
        out.append(rgb)
        if len(out) >= limit:
            break
    return out


def _find_crawl_html(root: Path, evidence_pack: dict | None) -> str:
    chunks: list[str] = []
    pages = ((evidence_pack or {}).get("site_story") or {}).get("pages") or []
    for page in pages:
        rel = page.get("html_file")
        if rel:
            path = root / rel
            if path.exists():
                try:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass
    pages_meta = _load_json(root / "evidence" / "pages.json") or {}
    for page in pages_meta.get("pages") or []:
        rel = page.get("html_file")
        if not rel:
            continue
        path = root / rel
        if path.exists():
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(chunks)


def _find_reference_screenshot(root: Path, evidence_pack: dict | None) -> Path | None:
    candidates: list[Path] = []
    for shot in (evidence_pack or {}).get("screenshots") or []:
        rel = shot.get("path")
        if rel:
            candidates.append(root / rel)
    browser = _load_json(root / "evidence" / "browser.json") or []
    for row in browser:
        for rel in (row.get("screenshots") or {}).values():
            if rel:
                candidates.append(root / rel)
    for pattern in ("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp"):
        candidates.extend(root.glob(pattern))
    for path in candidates:
        if path.is_file() and "mockups" not in path.parts and "demo" not in path.parts:
            return path
    return None


def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def extract_palette_from_crawl(
    root: Path,
    evidence_pack: dict | None = None,
) -> dict[str, str]:
    """Build a site-specific palette from screenshots, HTML colors, or domain seed."""
    pack = evidence_pack or _load_json(root / "evidence" / "evidence_pack.json") or {}
    domain = ((pack.get("website") or {}).get("domain")) or root.parent.parent.name
    story = pack.get("site_story") or _load_json(root / "seo" / "site_story.json") or {}
    story_text = " ".join(
        filter(
            None,
            [
                story.get("likely_business_name"),
                " ".join(story.get("value_prop_candidates") or []),
            ],
        )
    )

    colors: list[tuple[int, int, int]] = []
    shot = _find_reference_screenshot(root, pack)
    if shot:
        colors.extend(_dominant_colors_from_image(shot))
    colors.extend(_extract_colors_from_text(_find_crawl_html(root, pack)))

    seed = _pick_palette_seed(domain, story_text)
    if not colors:
        return {k: v for k, v in seed.items() if k != "mode"}

    accent = colors[0]
    accent_2 = colors[1] if len(colors) > 1 else (
        (min(255, accent[0] + 40), accent[1], accent[2])
        if accent[0] < 200
        else (accent[0], min(255, accent[1] + 50), accent[2])
    )
    dark_mode = seed.get("mode") == "dark" or _luminance(accent) < 0.45
    if dark_mode:
        bg = (12, 16, 24) if _luminance(accent) < 0.35 else (18, 22, 32)
        panel = (min(255, bg[0] + 12), min(255, bg[1] + 14), min(255, bg[2] + 18))
        text = (248, 250, 252)
        muted = (148, 163, 184)
    else:
        bg = (247, 244, 239)
        panel = (255, 255, 255)
        text = (20, 32, 31)
        muted = (92, 107, 106)

    return {
        "bg": _rgb_to_hex(bg),
        "panel": _rgb_to_hex(panel),
        "accent": _rgb_to_hex(accent),
        "accent_2": _rgb_to_hex(accent_2),
        "text": _rgb_to_hex(text),
        "muted": _rgb_to_hex(muted),
    }


def parse_service_blocks(site_story: dict | None) -> list[dict[str, str]]:
    """Parse service cards from crawled homepage copy."""
    site_story = site_story or {}
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    for page in site_story.get("pages") or []:
        excerpt = page.get("body_excerpt") or ""
        upper = excerpt.upper()
        if "SERVICES" in upper:
            excerpt = excerpt[upper.index("SERVICES") + len("SERVICES") :]
        chunks = re.split(
            r"\s(?=[A-Z][A-Za-z0-9\-/& ]{4,45}(?:Services|Events|Facilities|Production|Streaming|Broadcasting|Commercials)\b)",
            excerpt,
        )
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk or not SERVICE_TITLE_RE.match(chunk):
                continue
            match = re.match(
                r"^([A-Z][A-Za-z0-9\-/& ]{4,55}(?:Services|Events|Facilities|Production|Streaming|Broadcasting|Commercials))\s+(?:\1\s+)?(?:Our\s+|:)?\s*(.+)$",
                chunk,
                re.DOTALL,
            )
            if not match:
                continue
            title = re.sub(r"\s+", " ", match.group(1)).strip()
            body = re.sub(r"\s+", " ", match.group(2)).strip()
            key = title.lower()
            if key in seen or len(body) < 20:
                continue
            seen.add(key)
            found.append({"title": title[:80], "body": body[:220]})

    if found:
        return found[:6]

    # Fallback: comma-separated offers in value prop.
    offers = []
    for candidate in site_story.get("value_prop_candidates") or []:
        tail = candidate.split(":", 1)[-1] if ":" in candidate else candidate
        for part in re.split(r",|\band\b", tail):
            part = part.strip(" .")
            if len(part) > 4:
                offers.append(part)
    for offer in offers[:4]:
        found.append(
            {
                "title": offer[:1].upper() + offer[1:80],
                "body": f"Clear on-page explanation of {offer.lower()} for your visitors.",
            }
        )
    return found


def short_brand_name(raw: str, domain: str = "") -> str:
    """Prefer a short client-facing brand over long SEO titles."""
    name = (raw or "").strip()
    domain = (domain or "").lower()
    if "evp" in domain or name.lower().startswith("exclusive video"):
        return "EVP Malta" if "malta" in (name + domain).lower() else "EVP"
    # Drop common SEO suffixes.
    name = re.split(r"\s+[|\u2013\-]\s+", name)[0].strip()
    name = re.sub(
        r"\s+(Agency|Studio|Company|Ltd|Limited|Inc)\b.*$",
        "",
        name,
        flags=re.I,
    ).strip()
    if len(name) > 28:
        words = name.split()
        if len(words) >= 2:
            return " ".join(words[:2])
    return name or domain or "Studio"


def _looks_seo_title(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "|" in t or " – " in t:
        return True
    low = t.lower()
    return low in {"home", "homepage", "welcome", "services", "about", "contact"}


def punchy_headline(story: dict, brand: str) -> str:
    """Prefer benefit-led H1s; reject SEO browser titles."""
    for h in story.get("headlines") or []:
        text = str(h).strip()
        if 8 <= len(text) <= 72 and not _looks_seo_title(text):
            return text
    for page in story.get("pages") or []:
        for h in page.get("h1") or []:
            text = str(h).strip()
            if 8 <= len(text) <= 72 and not _looks_seo_title(text):
                return text
    # Fallback: never paste "Brand | Offer – Region" into the demo hero.
    return f"{brand} — clearer story, stronger first impression"


def _content_map(recommendations: dict | None) -> dict[str, str]:
    recs = (recommendations or {}).get("recommendations") or {}
    out: dict[str, str] = {}
    for item in recs.get("content_suggestions") or []:
        if not isinstance(item, dict):
            continue
        area = str(item.get("area") or "").lower()
        suggested = str(item.get("suggested") or "").strip()
        if not suggested:
            continue
        if "headline" in area and "sub" not in area:
            out["headline"] = suggested
        elif "sub" in area:
            out["subheadline"] = suggested
        elif "cta" in area:
            out["cta"] = suggested
        elif "about" in area:
            out["about"] = suggested
    return out


def build_design_brief(
    root: Path,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
) -> dict:
    """Site-specific brief: crawl palette + brain/rule copy."""
    pack = evidence_pack or _load_json(root / "evidence" / "evidence_pack.json") or {}
    rec_payload = recommendations or _load_json(root / "evidence" / "recommendations.json") or {}
    recs = rec_payload.get("recommendations") or {}

    if not recs.get("content_suggestions") and not recs.get("priority_actions"):
        merged = rule_based_recommendations(pack)
        recs = {**merged, **{k: v for k, v in recs.items() if v}}
        if not recs.get("content_suggestions"):
            recs["content_suggestions"] = merged.get("content_suggestions")

    story = pack.get("site_story") or _load_json(root / "seo" / "site_story.json") or {}
    domain = (
        ((rec_payload.get("website") or {}).get("domain"))
        or ((pack.get("website") or {}).get("domain"))
        or "your-site.com"
    )
    brand_raw = story.get("likely_business_name") or domain
    brand = short_brand_name(str(brand_raw), domain)
    content = _content_map(rec_payload)

    # Prefer Brain benefit headlines over crawl SEO titles.
    headline = punchy_headline(story, brand)
    suggested = content.get("headline") or ""
    if (
        suggested
        and not _looks_seo_title(suggested)
        and "that looks and feels" not in suggested.lower()
        and len(suggested) <= 100
    ):
        headline = suggested
    if _looks_seo_title(headline):
        headline = f"{brand} — clearer story, stronger first impression"

    sub = (
        content.get("subheadline")
        or (story.get("value_prop_candidates") or [None])[0]
        or f"{brand} — clearer story, stronger first impression."
    )
    # Soften long agency meta into Dora-style lede.
    if len(str(sub)) > 180 or str(sub).lower().startswith("exclusive video productions agency,"):
        sub = (
            f"Broadcast, stream, and film with a team that treats every frame like it matters — "
            f"across Malta & Gozo."
            if "malta" in (str(sub) + domain).lower()
            else f"{brand} helps ambitious brands show up with clarity and craft."
        )

    ctas = story.get("calls_to_action") or []
    cta_raw = content.get("cta") or (ctas[0] if ctas else "Start a project")
    cta = "Start a project" if str(cta_raw).lower() in {"contact", "learn more", "get started"} else str(cta_raw)

    tone = (recs.get("site_story_summary") or {}).get("tone") or ""
    from backend.app.services.design_direction import decide_design_direction
    from backend.app.services.company_profile import build_company_profile

    direction = recs.get("design_direction")
    if not isinstance(direction, dict) or not direction.get("theme"):
        profile = None
        try:
            from backend.app.services.company_profile import ensure_company_profile

            profile = ensure_company_profile(root, pack)
        except Exception:
            profile = build_company_profile(pack)
        direction = decide_design_direction(pack, profile)

    style_notes = f"Tone: {tone}. " if tone and tone.lower() not in {"unclear", ""} else ""
    style_notes += str(direction.get("style_notes") or direction.get("reasoning") or "")
    style_notes = style_notes.strip() or f"Theme-led landing for {domain}."

    services = parse_service_blocks(story)
    if not services:
        # Industry-aware placeholders when crawl services are thin.
        industry = str(
            (direction.get("theme") or "")
            or ((recs.get("company_profile") or {}).get("industry") or "")
        ).lower()
        if "romance" in industry or "wedding" in industry:
            defaults = ("Wedding films", "Engagement stories", "Reception coverage", "Highlight reels")
        elif "hospitality" in industry:
            defaults = ("Dining", "Events", "Private hire", "Seasonal menu")
        elif "tech" in industry or "bold" in industry:
            defaults = ("Product", "Integrations", "Onboarding", "Support")
        else:
            defaults = ("Outside Broadcasting", "Live Streaming", "Corporate Video", "TV Commercials")
        for label in defaults:
            services.append(
                {
                    "title": label,
                    "body": f"Premium {label.lower()} with clear outcomes for buyers.",
                }
            )

    # Brain theme palette wins when present; crawl colors can still seed accents.
    crawl_palette = extract_palette_from_crawl(root, pack)
    theme_palette = direction.get("palette") if isinstance(direction.get("palette"), dict) else {}
    palette = {**crawl_palette, **{k: v for k, v in theme_palette.items() if v}}

    hero_variant = direction.get("hero_variant") or "cinematic"
    theme = direction.get("theme") or "dark_cinematic"

    return {
        "version": 3,
        "palette": palette,
        "headline": str(headline)[:90],
        "subheadline": str(sub)[:220],
        "cta": str(cta)[:48],
        "style_notes": style_notes[:240],
        "image_prompt": (
            f"{brand} {direction.get('theme_label') or theme} homepage, "
            f"{hero_variant} hero, brand colors"
        )[:120],
        "brand_name": brand,
        "services": services[:6],
        "content_suggestions": recs.get("content_suggestions") or [],
        "source_domain": domain,
        "layout": direction.get("layout") or f"{theme}_{hero_variant}",
        "theme": theme,
        "hero_variant": hero_variant,
        "fonts": direction.get("fonts") or {},
        "section_labels": direction.get("section_labels") or {},
        "design_direction": direction,
        "design_reasoning": direction.get("reasoning") or "",
        "visuals_intent": direction.get("visuals") or {},
        "content_metadata": recs.get("content_metadata")
        if isinstance(recs.get("content_metadata"), dict)
        else {},
        "social_content": recs.get("social_content")
        if isinstance(recs.get("social_content"), dict)
        else {},
    }


def sync_brief_from_brain(
    root: Path,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    preserve_chat_overrides: bool = False,
) -> dict:
    """Refresh design brief from latest brain + crawl analysis (per site)."""
    from backend.app.services.design_chat import load_brief, merge_brief, save_brief

    fresh = build_design_brief(
        root,
        recommendations=recommendations,
        evidence_pack=evidence_pack,
    )
    existing = load_brief(root)
    if existing and preserve_chat_overrides:
        # Chat color/text edits win over auto-sync.
        brief = merge_brief(fresh, existing)
    else:
        brief = fresh
    save_brief(root, brief)

    # Persist best-words + social packs for agency handoff + demo <head>.
    meta = brief.get("content_metadata")
    if isinstance(meta, dict) and meta.get("page_title"):
        try:
            from backend.app.services.content_metadata import write_content_metadata

            write_content_metadata(root, meta)
        except Exception:
            pass
    social = brief.get("social_content")
    if isinstance(social, dict) and (social.get("post_ideas") or social.get("soundtracks")):
        try:
            from backend.app.services.social_content import write_social_content

            write_social_content(root, social)
        except Exception:
            pass
    return brief


def reference_screenshot_path(
    root: Path,
    evidence_pack: dict | None = None,
) -> str | None:
    path = _find_reference_screenshot(root, evidence_pack)
    if not path:
        return None
    try:
        rel = path.relative_to(root)
        return str(rel)
    except ValueError:
        return None
