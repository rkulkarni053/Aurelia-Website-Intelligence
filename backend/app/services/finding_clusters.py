"""Dedupe noisy findings and rewrite them in client-friendly language."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}

# Codes that explode page-by-page (especially a11y contrast). Cluster by code.
CLUSTER_CODES = {
    "a11y_color-contrast",
    "a11y_link-name",
    "a11y_image-alt",
    "a11y_button-name",
    "a11y_label",
    "a11y_landmark-one-main",
    "a11y_region",
    "a11y_heading-order",
    "missing_meta_description",
    "missing_title",
    "missing_h1",
    "thin_content",
    "title_too_short",
    "title_too_long",
    "meta_description_too_short",
    "meta_description_too_long",
    "page_render_failed",
    "browser_tooling_unavailable",
}

CLIENT_TITLES = {
    "a11y_color-contrast": "Text contrast is hard to read",
    "a11y_link-name": "Some links lack clear labels",
    "a11y_image-alt": "Images are missing alternative text",
    "a11y_button-name": "Buttons lack accessible names",
    "a11y_label": "Form fields are missing labels",
    "missing_meta_description": "Pages lack search snippet copy",
    "missing_title": "Pages are missing browser titles",
    "missing_h1": "Pages are missing a clear page headline",
    "thin_content": "Some pages have very little copy",
    "ssl_expiring_soon": "HTTPS certificate expires soon",
    "ssl_expired": "HTTPS certificate has expired",
    "no_https_redirect": "Site does not force HTTPS",
    "missing_robots": "Search engines lack a robots.txt guide",
    "missing_sitemap": "No XML sitemap was found",
    "siteone_low_overall_score": "Overall technical quality score is low",
    "weak_cta_path": "Conversion path is unclear",
    "missing_contact_path": "No clear contact or booking path",
    "cms_upgrade_opportunity": "Platform upgrade opportunity",
    "stack_gap": "Recommended stack improvement",
}

CLIENT_WHY = {
    "accessibility": "Improves usability for all visitors and reduces legal risk.",
    "seo": "Helps people find the business in search and understand the offer.",
    "performance": "Faster pages keep visitors engaged and improve conversion.",
    "security": "Protects visitor trust and search ranking signals.",
    "technical": "Reduces fragility and makes future changes safer.",
    "content": "Clearer messaging improves conversion and brand clarity.",
    "ux": "Removes friction between interest and enquiry/purchase.",
}


def _rank(sev: str | None) -> int:
    return SEVERITY_RANK.get((sev or "info").lower(), 9)


def client_title(finding: dict) -> str:
    code = finding.get("code") or ""
    return CLIENT_TITLES.get(code) or finding.get("title") or code or "Issue"


def client_description(finding: dict, *, page_count: int = 1, sample_urls: list | None = None) -> str:
    base = (finding.get("description") or "").strip()
    category = (finding.get("category") or "technical").lower()
    why = CLIENT_WHY.get(category, "")
    parts = []
    if page_count > 1:
        parts.append(f"Affects {page_count} pages.")
    if base:
        # Strip tooling jargon that confuses clients.
        cleaned = base.replace("SiteOne Crawler: ", "").replace("axe-core", "accessibility scan")
        parts.append(cleaned)
    if why:
        parts.append(why)
    samples = [u for u in (sample_urls or []) if u][:3]
    if samples:
        parts.append("Examples: " + "; ".join(samples))
    return " ".join(parts).strip()


def dedupe_findings(findings: list[dict]) -> list[dict]:
    """Collapse duplicate (code, url) rows, then cluster noisy codes site-wide."""
    if not findings:
        return []

    # Exact page duplicates.
    exact: dict[tuple, dict] = {}
    for f in findings:
        key = (f.get("code"), f.get("url") or "")
        prev = exact.get(key)
        if prev is None or _rank(f.get("severity")) < _rank(prev.get("severity")):
            exact[key] = dict(f)
    unique = list(exact.values())

    by_code: dict[str, list[dict]] = defaultdict(list)
    passthrough: list[dict] = []
    for f in unique:
        code = f.get("code") or ""
        if code in CLUSTER_CODES or code.startswith("a11y_"):
            by_code[code].append(f)
        else:
            passthrough.append(f)

    clustered: list[dict] = []
    for code, group in by_code.items():
        if len(group) == 1:
            one = dict(group[0])
            one["title"] = client_title(one)
            one["description"] = client_description(one, page_count=1, sample_urls=[one.get("url")])
            detail = dict(one.get("detail") or {})
            detail["clustered"] = False
            detail["page_count"] = 1
            one["detail"] = detail
            clustered.append(one)
            continue

        group.sort(key=lambda x: _rank(x.get("severity")))
        primary = dict(group[0])
        urls = []
        for g in group:
            u = g.get("url")
            if u and u not in urls:
                urls.append(u)
        node_total = 0
        for g in group:
            detail = g.get("detail") or {}
            try:
                node_total += int(detail.get("node_count") or 0)
            except (TypeError, ValueError):
                pass
        primary["url"] = None  # site-level cluster
        primary["title"] = client_title(primary)
        primary["description"] = client_description(
            primary, page_count=len(urls) or len(group), sample_urls=urls
        )
        primary["detail"] = {
            **(primary.get("detail") or {}),
            "clustered": True,
            "page_count": len(urls) or len(group),
            "sample_urls": urls[:8],
            "node_count_total": node_total or None,
            "original_count": len(group),
        }
        clustered.append(primary)

    out = passthrough + clustered
    # Client-friendly titles for non-clustered rows too.
    for f in out:
        if f.get("code") in CLIENT_TITLES:
            f["title"] = client_title(f)
    out.sort(key=lambda x: (_rank(x.get("severity")), x.get("category") or "", x.get("code") or ""))
    return out


def cluster_summary(findings: list[dict], *, max_items: int = 8) -> list[dict[str, Any]]:
    """Top client-facing issue cards for proposals / verification."""
    ranked = sorted(
        findings,
        key=lambda x: (
            _rank(x.get("severity")),
            -int((x.get("detail") or {}).get("page_count") or 0),
        ),
    )
    cards = []
    for f in ranked[:max_items]:
        detail = f.get("detail") or {}
        cards.append(
            {
                "code": f.get("code"),
                "severity": f.get("severity"),
                "category": f.get("category"),
                "title": client_title(f),
                "description": f.get("description") or client_description(f),
                "page_count": detail.get("page_count") or (1 if f.get("url") else None),
                "sample_urls": detail.get("sample_urls") or ([f["url"]] if f.get("url") else []),
            }
        )
    return cards
