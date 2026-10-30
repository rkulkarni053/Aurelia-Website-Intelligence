"""Extract the website's narrative / story signals for the AI brain.

Pulls homepage, about, and services-style pages so recommendations can be
grounded in what the business actually says — not only technical findings.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from backend.app.services.content_seo import _tokens, _visible_text

ABOUT_HINTS = (
    "about", "our-story", "ourstory", "who-we-are", "company", "mission",
    "team", "geschichte", "uber-uns", "über-uns",
)
SERVICES_HINTS = (
    "service", "services", "product", "products", "solution", "solutions",
    "offer", "offering", "what-we-do", "leistungen",
)
CTA_WORDS = (
    "contact", "book", "buy", "get started", "sign up", "request", "quote",
    "demo", "call", "shop", "learn more", "start", "join", "subscribe",
)


def _path_role(url: str) -> str:
    path = (urlparse(url).path or "/").lower().strip("/")
    if path in {"", "index", "index.html", "home", "homepage"}:
        return "home"
    slug = path.replace("_", "-")
    if any(h in slug for h in ABOUT_HINTS):
        return "about"
    if any(h in slug for h in SERVICES_HINTS):
        return "services"
    return "other"


def _clip(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _ctas(soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for tag in soup.find_all(["a", "button"]):
        label = tag.get_text(" ", strip=True)
        if not label or len(label) > 60:
            continue
        low = label.lower()
        if any(w in low for w in CTA_WORDS):
            if label not in found:
                found.append(label)
        if len(found) >= 6:
            break
    return found


def extract_page_story(url: str, html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_description = (meta.get("content") or "").strip() if meta else ""
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    body = _visible_text(soup)
    role = _path_role(url)

    return {
        "url": url,
        "role": role,
        "title": title,
        "meta_description": meta_description,
        "og_title": (og_title.get("content") or "").strip() if og_title else "",
        "og_description": (og_desc.get("content") or "").strip() if og_desc else "",
        "h1": h1s[:3],
        "h2": h2s[:8],
        "body_excerpt": _clip(body, 900),
        "ctas": _ctas(soup),
        "word_count": len(_tokens(body)),
    }


def _priority(page: dict) -> tuple:
    role_rank = {"home": 0, "about": 1, "services": 2, "other": 3}
    return (role_rank.get(page.get("role"), 9), -(page.get("word_count") or 0))


def collect_site_story(pages: list[dict], max_pages: int = 8) -> dict:
    """Build compact narrative evidence from crawled HTML pages."""
    # Prefer rendered HTML pages when mixed with empty SPA shells.
    ordered = sorted(
        [p for p in pages if p.get("html")],
        key=lambda p: 0 if p.get("html_source") == "rendered" else 1,
    )
    analyzed = [
        extract_page_story(p.get("url") or "", p.get("html") or "")
        for p in ordered
    ]
    analyzed.sort(key=_priority)
    selected = analyzed[:max_pages]

    # Prefer story-bearing roles; fill with richest other pages if needed.
    preferred = [p for p in analyzed if p.get("role") in {"home", "about", "services"}]
    if preferred:
        rest = [p for p in analyzed if p not in preferred]
        selected = (preferred + rest)[:max_pages]

    headlines: list[str] = []
    for p in selected:
        for h in (p.get("h1") or []) + (p.get("h2") or [])[:2]:
            if h and h not in headlines:
                headlines.append(h)
        if len(headlines) >= 10:
            break

    ctas: list[str] = []
    for p in selected:
        for c in p.get("ctas") or []:
            if c not in ctas:
                ctas.append(c)

    meta_bits = [
        p.get("meta_description") or p.get("og_description")
        for p in selected
        if p.get("meta_description") or p.get("og_description")
    ]

    home = next((p for p in selected if p.get("role") == "home"), None)
    about = next((p for p in selected if p.get("role") == "about"), None)
    title_seed = (
        (home or {}).get("og_title")
        or (home or {}).get("title")
        or (selected[0].get("title") if selected else "")
        or ""
    )

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "pages_used": len(selected),
        "roles_present": sorted({p.get("role") for p in selected if p.get("role")}),
        "likely_business_name": _clip(title_seed.split("|")[0].split("-")[0], 80),
        "headlines": headlines[:10],
        "value_prop_candidates": [m for m in meta_bits if m][:4],
        "calls_to_action": ctas[:6],
        "pages": [
            {
                "url": p["url"],
                "role": p["role"],
                "title": p["title"],
                "h1": p["h1"],
                "meta_description": p["meta_description"],
                "body_excerpt": p["body_excerpt"],
                "ctas": p["ctas"],
            }
            for p in selected
        ],
        "notes": (
            "Narrative excerpts for the AI brain. Prefer home/about/services "
            "pages. Not a substitute for reading the full site."
        ),
        "about_present": about is not None,
        "home_present": home is not None,
    }
