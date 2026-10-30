"""Infer conversion / CTA path health from site story + content evidence."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

CONTACT_HINTS = (
    "contact", "kontakt", "book", "booking", "demo", "quote", "anfrage",
    "appointment", "termin", "get-in-touch", "enquiry", "inquiry", "support",
)
CONVERSION_CTA = (
    "contact", "book", "buy", "get started", "sign up", "request", "quote",
    "demo", "call", "shop", "start", "join", "subscribe", "enquire", "inquiry",
)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _is_contact_url(url: str) -> bool:
    path = (urlparse(url or "").path or "/").lower()
    return any(h in path for h in CONTACT_HINTS)


def analyze_conversion_path(root: Path) -> dict:
    """Return funnel map + gaps for evidence pack / findings."""
    story = _load(root / "seo" / "site_story.json") or {}
    pages = story.get("pages") or []
    by_role = {p.get("role"): p for p in pages if p.get("role")}

    home = by_role.get("home") or next((p for p in pages if p.get("role") == "home"), None)
    services = [p for p in pages if p.get("role") == "services"]
    about = by_role.get("about")
    contact_pages = [p for p in pages if _is_contact_url(p.get("url") or "")]

    home_ctas = list((home or {}).get("ctas") or [])
    home_has_conversion_cta = any(
        any(w in (c or "").lower() for w in CONVERSION_CTA) for c in home_ctas
    )

    gaps: list[str] = []
    if not home:
        gaps.append("No clear homepage narrative page was identified.")
    elif not home_ctas:
        gaps.append("Homepage has no obvious call-to-action labels.")
    elif not home_has_conversion_cta:
        gaps.append(
            "Homepage CTAs look informational; no clear contact/book/buy action."
        )
    if not services:
        gaps.append("No services/products page was found in the crawl sample.")
    if not contact_pages and not home_has_conversion_cta:
        gaps.append("No contact, booking, or demo path was detected.")
    if about and not (about.get("ctas") or []):
        gaps.append("About page has no onward CTA toward contact or services.")

    strength = "strong"
    if len(gaps) >= 3:
        strength = "weak"
    elif gaps:
        strength = "mixed"

    return {
        "version": 1,
        "strength": strength,
        "home": {
            "url": (home or {}).get("url"),
            "ctas": home_ctas[:6],
            "has_conversion_cta": home_has_conversion_cta,
            "h1": ((home or {}).get("h1") or [None])[0],
        },
        "services_pages": [
            {"url": p.get("url"), "ctas": (p.get("ctas") or [])[:4]}
            for p in services[:5]
        ],
        "about": {"url": (about or {}).get("url")} if about else None,
        "contact_pages": [{"url": p.get("url")} for p in contact_pages[:5]],
        "gaps": gaps,
        "funnel": [
            {"step": "home", "ok": bool(home), "url": (home or {}).get("url")},
            {
                "step": "offer",
                "ok": bool(services),
                "url": (services[0].get("url") if services else None),
            },
            {
                "step": "convert",
                "ok": bool(contact_pages or home_has_conversion_cta),
                "url": (
                    contact_pages[0]["url"]
                    if contact_pages
                    else (home or {}).get("url")
                ),
            },
        ],
    }


def _finding(code, severity, category, title, description, evidence_file, url=None, detail=None):
    return {
        "code": code,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "url": url,
        "evidence_file": evidence_file,
        "detail": detail,
    }


def conversion_findings(root: Path) -> list[dict]:
    """Emit finding dicts compatible with the findings engine."""
    path = analyze_conversion_path(root)
    (root / "seo").mkdir(parents=True, exist_ok=True)
    (root / "seo" / "conversion_path.json").write_text(
        json.dumps(path, indent=2), encoding="utf-8"
    )

    out = []
    ef = "seo/conversion_path.json"
    home_url = (path.get("home") or {}).get("url")

    if path.get("strength") == "weak":
        out.append(
            _finding(
                "weak_cta_path",
                "high",
                "ux",
                "Conversion path is unclear",
                "Visitors may not see a clear path from interest to contact or purchase. "
                + " ".join(path.get("gaps") or [])[:400],
                ef,
                home_url,
                {"gaps": path.get("gaps"), "funnel": path.get("funnel")},
            )
        )
    elif path.get("gaps"):
        out.append(
            _finding(
                "weak_cta_path",
                "medium",
                "ux",
                "Conversion path has gaps",
                " ".join(path.get("gaps") or [])[:500],
                ef,
                home_url,
                {"gaps": path.get("gaps"), "funnel": path.get("funnel")},
            )
        )

    if not path.get("contact_pages") and not (path.get("home") or {}).get(
        "has_conversion_cta"
    ):
        out.append(
            _finding(
                "missing_contact_path",
                "medium",
                "ux",
                "No clear contact or booking path",
                "We did not find a contact/booking page or a strong conversion CTA on the homepage.",
                ef,
                home_url,
                {"funnel": path.get("funnel")},
            )
        )
    return out
