"""Suggest CMS / stack upgrades from technology fingerprints."""

from __future__ import annotations

import json
from pathlib import Path

# Playbooks keyed by detected technology name (case-sensitive match to detector).
PLAYBOOKS = {
    "WordPress": {
        "severity": "medium",
        "title": "WordPress platform hygiene opportunity",
        "summary": (
            "WordPress sites often accumulate outdated plugins, slow themes, "
            "and missing caching. A hygiene pass plus Core Web Vitals work is "
            "usually a billable Essentials/Growth item."
        ),
        "actions": [
            "Audit plugins/themes for updates and unused bloat",
            "Add page caching / CDN if missing",
            "Hardening: limit login, keep core/plugins current",
            "Image compression and lazy-loading pass",
        ],
        "package_hint": "growth",
    },
    "WooCommerce": {
        "severity": "medium",
        "title": "WooCommerce checkout & performance review",
        "summary": (
            "Ecommerce stacks are sensitive to plugin weight and checkout UX. "
            "Performance and conversion friction usually justify Growth scope."
        ),
        "actions": [
            "Review checkout steps and trust signals",
            "Trim cart/checkout plugin conflicts",
            "Product image and catalog performance pass",
        ],
        "package_hint": "growth",
    },
    "Shopify": {
        "severity": "low",
        "title": "Shopify theme & conversion polish",
        "summary": (
            "Shopify handles hosting; value is in theme speed, merchandising, "
            "and conversion path clarity."
        ),
        "actions": [
            "Theme performance audit (apps + scripts)",
            "Homepage → collection → product → cart CTA review",
            "Structured data / SEO basics for products",
        ],
        "package_hint": "essentials",
    },
    "Wix": {
        "severity": "medium",
        "title": "Wix limits vs. custom redesign decision",
        "summary": (
            "Wix is fine for simple sites; complex SEO, integrations, or brand "
            "redesigns often justify migrating to a more flexible stack."
        ),
        "actions": [
            "Confirm whether SEO/perf ceilings block goals",
            "If redesigning, evaluate Webflow/WordPress/custom",
            "Export content inventory before any migration",
        ],
        "package_hint": "redesign",
    },
    "Squarespace": {
        "severity": "low",
        "title": "Squarespace template refresh opportunity",
        "summary": (
            "Template constraints can cap conversion design. A content and "
            "template refresh is often enough without full migration."
        ),
        "actions": [
            "Homepage messaging and CTA refresh",
            "Mobile spacing / hierarchy pass",
            "SEO title/meta cleanup across key pages",
        ],
        "package_hint": "growth",
    },
    "Drupal": {
        "severity": "medium",
        "title": "Drupal maintenance & upgrade path",
        "summary": (
            "Drupal sites need module hygiene and occasionally major-version "
            "planning. Surface this as a technical risk in the proposal."
        ),
        "actions": [
            "Inventory modules and unsupported versions",
            "Security updates and caching configuration",
            "Plan major upgrade if on unsupported core",
        ],
        "package_hint": "growth",
    },
    "jQuery": {
        "severity": "info",
        "title": "Legacy JavaScript dependency",
        "summary": (
            "Heavy jQuery-era stacks often pair with outdated themes. Not "
            "urgent alone, but relevant if redesigning."
        ),
        "actions": [
            "Inventory custom scripts before redesign",
            "Prefer modern framework only if rebuilding UI",
        ],
        "package_hint": "redesign",
    },
}

STACK_GAPS = [
    {
        "missing_any": ["Google Analytics", "Google Tag Manager"],
        "code": "stack_gap",
        "severity": "medium",
        "title": "No analytics tag detected",
        "summary": (
            "Without analytics you cannot prove traffic or conversion impact "
            "after fixes. Add GA4 or GTM as a quick win."
        ),
        "actions": ["Install GA4 via GTM", "Define conversion events for contact/book"],
        "package_hint": "essentials",
    },
    {
        "missing_any": ["Cloudflare", "Amazon CloudFront", "Fastly", "Varnish"],
        "when_any": ["WordPress", "Drupal", "Nginx", "Apache"],
        "code": "stack_gap",
        "severity": "low",
        "title": "No CDN / edge cache detected",
        "summary": (
            "A CDN often improves global performance and absorbs traffic spikes "
            "cheaply — a common Growth add-on."
        ),
        "actions": ["Evaluate Cloudflare or equivalent CDN", "Enable caching + compression"],
        "package_hint": "growth",
    },
]


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


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


def build_upgrade_advice(root: Path) -> dict:
    tech = _load(root / "technologies" / "technologies.json") or {}
    detections = tech.get("detections") or []
    names = {d.get("name") for d in detections if d.get("name")}
    site_url = tech.get("site_url")

    opportunities = []
    for name in sorted(names):
        book = PLAYBOOKS.get(name)
        if not book:
            continue
        opportunities.append(
            {
                "technology": name,
                "category": next(
                    (d.get("category") for d in detections if d.get("name") == name),
                    "other",
                ),
                **book,
            }
        )

    for gap in STACK_GAPS:
        missing = gap["missing_any"]
        if any(m in names for m in missing):
            continue
        when = gap.get("when_any")
        if when and not any(w in names for w in when):
            continue
        opportunities.append(
            {
                "technology": "gap:" + ",".join(missing),
                "category": "stack_gap",
                "severity": gap["severity"],
                "title": gap["title"],
                "summary": gap["summary"],
                "actions": gap["actions"],
                "package_hint": gap["package_hint"],
            }
        )

    advice = {
        "version": 1,
        "site_url": site_url,
        "detected": sorted(names),
        "opportunities": opportunities,
    }
    out_dir = root / "technologies"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "upgrades.json").write_text(
        json.dumps(advice, indent=2), encoding="utf-8"
    )
    return advice


def upgrade_findings(root: Path) -> list[dict]:
    advice = build_upgrade_advice(root)
    ef = "technologies/upgrades.json"
    out = []
    for opp in advice.get("opportunities") or []:
        if (opp.get("severity") or "info") == "info":
            continue
        code = (
            "cms_upgrade_opportunity"
            if not str(opp.get("technology") or "").startswith("gap:")
            else "stack_gap"
        )
        out.append(
            _finding(
                code,
                opp.get("severity") or "medium",
                "technical",
                opp.get("title") or "Upgrade opportunity",
                opp.get("summary") or "",
                ef,
                advice.get("site_url"),
                {
                    "technology": opp.get("technology"),
                    "actions": opp.get("actions") or [],
                    "package_hint": opp.get("package_hint"),
                },
            )
        )
    return out
