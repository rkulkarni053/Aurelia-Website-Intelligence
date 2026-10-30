"""Build a compact, brain-ready evidence pack from a crawl's saved files.

The pack is intentionally small enough for local LLM context: summaries,
scores, top findings, and paths to heavier artifacts — not raw HTML.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK_VERSION = 1
PACK_FILENAME = "evidence/evidence_pack.json"
MAX_FINDINGS = 80
MAX_PAGES = 100
MAX_TECHNOLOGIES = 40
MAX_SCREENSHOTS = 24

SEVERITY_PENALTY = {
    "high": 2.0,
    "medium": 1.0,
    "low": 0.4,
    "info": 0.1,
}

CATEGORY_ORDER = (
    "seo",
    "performance",
    "accessibility",
    "security",
    "technical",
    "ux",
    "content",
)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


def _summarize_findings(findings: list[dict]) -> dict:
    by_severity: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    for f in findings:
        by_severity[f.get("severity") or "info"] += 1
        by_category[f.get("category") or "technical"] += 1

    ordered = sorted(
        findings,
        key=lambda f: (
            {"high": 0, "medium": 1, "low": 2, "info": 3}.get(
                f.get("severity"), 9
            ),
            f.get("code") or "",
        ),
    )

    top = []
    for f in ordered[:MAX_FINDINGS]:
        top.append(
            {
                "code": f.get("code"),
                "severity": f.get("severity"),
                "category": f.get("category"),
                "title": f.get("title"),
                "description": f.get("description"),
                "url": f.get("url"),
                "evidence_file": f.get("evidence_file"),
                # Keep detail small; drop large samples for the brain pack.
                "detail": _shrink_detail(f.get("detail")),
            }
        )

    return {
        "total": len(findings),
        "by_severity": dict(by_severity),
        "by_category": dict(by_category),
        "top": top,
        "truncated": len(findings) > MAX_FINDINGS,
    }


def _shrink_detail(detail: Any) -> Any:
    if detail is None:
        return None
    if isinstance(detail, dict):
        out = {}
        for key, value in detail.items():
            if key in {"sample", "sample_pages"} and isinstance(value, list):
                out[key] = value[:3]
            elif key == "h1" and isinstance(value, list):
                out[key] = value[:5]
            else:
                out[key] = value
        return out
    return detail


def _score_from_findings(findings: list[dict], category: str) -> float | None:
    relevant = [f for f in findings if f.get("category") == category]
    if not relevant:
        return None
    score = 10.0
    for f in relevant:
        score -= SEVERITY_PENALTY.get(f.get("severity"), 0.5)
    return _clamp_score(score)


def _performance_bonus(performance: list[dict] | None) -> float | None:
    """Return a heuristic performance score from LCP when available."""
    if not performance:
        return None

    lcps = []
    for row in performance:
        if row.get("error"):
            continue
        perf = row.get("performance") or {}
        lcp = perf.get("lcp_ms")
        if isinstance(lcp, (int, float)):
            lcps.append(lcp)

    if not lcps:
        return None

    avg_lcp = sum(lcps) / len(lcps)
    # Rough mapping inspired by Core Web Vitals thresholds.
    if avg_lcp <= 2500:
        return 9.5
    if avg_lcp <= 4000:
        return 7.0
    if avg_lcp <= 6000:
        return 4.5
    return 2.0


def _security_ssl_adjustment(ssl: dict | None) -> float:
    if not ssl:
        return 0.0
    delta = 0.0
    if ssl.get("https_enabled") is False:
        delta -= 3.0
    if ssl.get("certificate_valid") is False:
        delta -= 3.0
    days = ssl.get("days_remaining")
    if isinstance(days, int) and days < 30:
        delta -= 1.5
    http = ssl.get("http_to_https") or {}
    location = http.get("location") or ""
    if http and not str(location).startswith("https://"):
        # Already likely covered by a finding; light extra nudge only.
        delta -= 0.5
    return delta


def _compute_scores(
    findings: list[dict],
    *,
    ssl: dict | None,
    performance: list[dict] | None,
) -> dict:
    scores: dict[str, float] = {}

    for category in CATEGORY_ORDER:
        base = _score_from_findings(findings, category)
        if category == "performance":
            lcp_score = _performance_bonus(performance)
            if base is None and lcp_score is None:
                continue
            if base is None:
                scores[category] = lcp_score  # type: ignore[assignment]
            elif lcp_score is None:
                scores[category] = base
            else:
                scores[category] = _clamp_score((base + lcp_score) / 2)
            continue

        if base is None:
            # No findings in category: treat as solid unless we have no signal.
            if category == "security" and ssl:
                score = 10.0 + _security_ssl_adjustment(ssl)
                scores[category] = _clamp_score(score)
            continue

        if category == "security":
            base = _clamp_score(base + _security_ssl_adjustment(ssl))
        scores[category] = base

    if scores:
        overall = _clamp_score(sum(scores.values()) / len(scores))
    else:
        overall = 10.0

    return {
        "scale": 10,
        "method": "heuristic_v1",
        "overall": overall,
        "by_category": scores,
        "notes": (
            "Heuristic scores from findings severity and basic LCP/SSL "
            "signals. Not Lighthouse. Replace/augment with real Lighthouse "
            "or PageSpeed later."
        ),
    }


def _summarize_ssl(ssl: dict | None) -> dict | None:
    if not ssl:
        return None
    return {
        "https_enabled": ssl.get("https_enabled"),
        "certificate_valid": ssl.get("certificate_valid"),
        "tls_version": ssl.get("tls_version"),
        "issuer": (ssl.get("issuer") or {}).get("organizationName")
        or (ssl.get("issuer") or {}).get("commonName"),
        "valid_until": ssl.get("valid_until"),
        "days_remaining": ssl.get("days_remaining"),
        "http_to_https_status": (ssl.get("http_to_https") or {}).get(
            "status_code"
        ),
        "http_to_https_location": (ssl.get("http_to_https") or {}).get(
            "location"
        ),
        "error": ssl.get("error"),
        "evidence_file": "ssl/certificate.json",
    }


def _summarize_seo(seo: dict | None) -> dict | None:
    if not seo:
        return None
    robots = seo.get("robots") or {}
    sample_urls: list[str] = []
    for entry in seo.get("sitemaps") or []:
        parsed = (entry or {}).get("parsed") or {}
        for loc in parsed.get("urls") or parsed.get("sample_urls") or []:
            if loc and loc not in sample_urls:
                sample_urls.append(str(loc))
            if len(sample_urls) >= 40:
                break
        if len(sample_urls) >= 40:
            break
    return {
        "robots_found": robots.get("found"),
        "sitemap_found": seo.get("sitemap_found"),
        "sitemap_declared_in_robots": seo.get("sitemap_declared_in_robots"),
        "total_sitemap_urls": seo.get("total_sitemap_urls"),
        "sample_urls": sample_urls,
        "evidence_file": "seo/analysis.json",
    }


def _summarize_technologies(tech: dict | None) -> dict | None:
    if not tech:
        return None
    detections = tech.get("detections") or []
    slim = [
        {
            "name": d.get("name"),
            "category": d.get("category"),
            "pages_matched": d.get("pages_matched"),
        }
        for d in detections[:MAX_TECHNOLOGIES]
    ]
    return {
        "count": len(detections),
        "detections": slim,
        "truncated": len(detections) > MAX_TECHNOLOGIES,
        "evidence_file": "technologies/technologies.json",
    }


def _summarize_pages(pages_data: dict | None, browser: list | None) -> dict:
    pages = (pages_data or {}).get("pages") or []
    errors = (pages_data or {}).get("errors") or []

    browser_by_url = {}
    for ev in browser or []:
        key = ev.get("final_url") or ev.get("url")
        if key:
            browser_by_url[key] = ev

    slim_pages = []
    for page in pages[:MAX_PAGES]:
        url = page.get("url")
        ev = browser_by_url.get(url) or {}
        screenshots = ev.get("screenshots") or {}
        slim_pages.append(
            {
                "url": url,
                "status_code": page.get("status_code"),
                "title": page.get("title") or (ev.get("dom") or {}).get("title"),
                "html_file": page.get("html_file"),
                "rendered_html_file": ev.get("rendered_html_file"),
                "screenshots": {
                    "desktop": screenshots.get("desktop"),
                    "mobile": screenshots.get("mobile"),
                },
                "load_time_ms": ev.get("load_time_ms"),
            }
        )

    return {
        "crawled": len(pages),
        "errors": len(errors),
        "pages": slim_pages,
        "truncated": len(pages) > MAX_PAGES,
        "evidence_file": "evidence/pages.json",
    }


def _summarize_performance(performance: list | None) -> dict | None:
    if not performance:
        return None
    rows = []
    for row in performance:
        perf = row.get("performance") or {}
        rows.append(
            {
                "url": row.get("final_url") or row.get("url"),
                "lcp_ms": perf.get("lcp_ms"),
                "fcp_ms": perf.get("fcp_ms"),
                "total_requests": perf.get("total_requests"),
                "total_transfer_bytes": perf.get("total_transfer_bytes"),
                "error": row.get("error"),
            }
        )
    return {
        "pages": rows,
        "evidence_file": "evidence/performance.json",
    }


def _summarize_accessibility(a11y: list | None) -> dict | None:
    if not a11y:
        return None
    rows = []
    for row in a11y:
        violations = row.get("violations") or []
        rows.append(
            {
                "url": row.get("url") or row.get("final_url"),
                "violation_count": len(violations),
                "error": row.get("error"),
            }
        )
    return {
        "pages": rows,
        "evidence_file": "evidence/accessibility.json",
    }


def _collect_screenshot_index(browser: list | None) -> list[dict]:
    out = []
    for ev in browser or []:
        shots = ev.get("screenshots") or {}
        for viewport, path in shots.items():
            if not path:
                continue
            out.append(
                {
                    "url": ev.get("final_url") or ev.get("url"),
                    "viewport": viewport,
                    "path": path,
                }
            )
            if len(out) >= MAX_SCREENSHOTS:
                return out
    return out


def build_evidence_pack(
    root: Path,
    *,
    website: dict | None = None,
    crawl: dict | None = None,
) -> dict:
    """Assemble a brain-ready pack from files under a crawl root."""
    findings = _load(root / "evidence" / "findings.json") or []
    pages_data = _load(root / "evidence" / "pages.json")
    browser = _load(root / "evidence" / "browser.json") or []
    performance = _load(root / "evidence" / "performance.json") or []
    accessibility = _load(root / "evidence" / "accessibility.json") or []
    ssl = _load(root / "ssl" / "certificate.json")
    seo = _load(root / "seo" / "analysis.json")
    content = _load(root / "seo" / "content.json")
    site_story = _load(root / "seo" / "site_story.json")
    conversion_path = _load(root / "seo" / "conversion_path.json")
    tech = _load(root / "technologies" / "technologies.json")
    upgrades = _load(root / "technologies" / "upgrades.json")
    lighthouse = _load(root / "lighthouse" / "summary.json")
    annotated = _load(root / "evidence" / "annotated_screenshots.json")
    siteone = _load(root / "seo" / "siteone_summary.json")
    reports_manifest = _load(root / "reports" / "manifest.json")

    if not isinstance(findings, list):
        findings = []

    scores = _compute_scores(findings, ssl=ssl, performance=performance)

    # Prefer Lighthouse aggregate scores when present.
    lh_agg = (lighthouse or {}).get("aggregate") or {}
    lh_10 = lh_agg.get("scores_out_of_10") or {}
    if lh_10:
        merged = dict(scores.get("by_category") or {})
        if lh_10.get("seo") is not None:
            merged["seo"] = lh_10["seo"]
        if lh_10.get("performance") is not None:
            merged["performance"] = lh_10["performance"]
        if lh_10.get("accessibility") is not None:
            merged["accessibility"] = lh_10["accessibility"]
        scores["by_category"] = merged
        if lh_agg.get("overall_out_of_10") is not None:
            scores["overall"] = lh_agg["overall_out_of_10"]
        scores["method"] = f"lighthouse_preferred:{(lighthouse or {}).get('source')}"
        scores["notes"] = (
            "Scores prefer Lighthouse/heuristic lighthouse aggregate when "
            "available; otherwise finding-based heuristics."
        )
        scores["lighthouse"] = lh_agg

    # When SiteOne ran successfully, surface its SEO score if Lighthouse
    # did not already supply one.
    siteone_scores = (siteone or {}).get("scores") or {}
    siteone_by_cat = siteone_scores.get("by_category") or {}
    if siteone and siteone.get("ok") and siteone_by_cat.get("seo") is not None:
        merged = dict(scores.get("by_category") or {})
        if merged.get("seo") is None:
            merged["seo"] = siteone_by_cat["seo"]
            scores["by_category"] = merged
        scores["siteone"] = {
            "overall": siteone_scores.get("overall"),
            "by_category": siteone_by_cat,
        }

    finding_summary = _summarize_findings(findings)

    pack = {
        "version": PACK_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Compact audit context for a local AI brain. Prefer this file "
            "over raw evidence when generating recommendations."
        ),
        "website": website,
        "crawl": crawl,
        "scores": scores,
        "findings": finding_summary,
        "pages": _summarize_pages(pages_data, browser),
        "ssl": _summarize_ssl(ssl),
        "seo": _summarize_seo(seo),
        "content_seo": {
            "pages_analyzed": (content or {}).get("pages_analyzed"),
            "thin_content_pages": (content or {}).get("thin_content_pages"),
            "missing_h1_pages": (content or {}).get("missing_h1_pages"),
            "keyword_stuffing_pages": (content or {}).get("keyword_stuffing_pages"),
            "evidence_file": "seo/content.json",
        }
        if content
        else None,
        "site_story": site_story,
        "conversion_path": conversion_path,
        "technologies": _summarize_technologies(tech),
        "upgrades": {
            "detected": (upgrades or {}).get("detected") or [],
            "opportunities": (upgrades or {}).get("opportunities") or [],
            "evidence_file": "technologies/upgrades.json",
        }
        if upgrades
        else None,
        "performance": _summarize_performance(performance),
        "accessibility": _summarize_accessibility(accessibility),
        "lighthouse": lighthouse,
        "siteone": {
            "ok": (siteone or {}).get("ok"),
            "available": (siteone or {}).get("available"),
            "error": (siteone or {}).get("error"),
            "scores": (siteone or {}).get("scores"),
            "visited_urls": (siteone or {}).get("visited_urls"),
            "counts": (siteone or {}).get("counts"),
            "files": (siteone or {}).get("files"),
            "summary_item_count": len((siteone or {}).get("summary_items") or []),
            "evidence_file": "seo/siteone_summary.json",
        }
        if siteone
        else None,
        "reports": {
            "manifest": "reports/manifest.json",
            "proof_zip": "reports/proof-pack.zip",
            "proof_index": "reports/index.html",
            "download_count": len((reports_manifest or {}).get("downloads") or []),
            "screenshot_count": (reports_manifest or {}).get("screenshot_count"),
        }
        if reports_manifest
        else None,
        "screenshots": _collect_screenshot_index(browser),
        "annotated_screenshots": (annotated or {}).get("images") or [],
        "artifact_paths": {
            "findings": "evidence/findings.json",
            "browser": "evidence/browser.json",
            "performance": "evidence/performance.json",
            "accessibility": "evidence/accessibility.json",
            "pages": "evidence/pages.json",
            "ssl": "ssl/certificate.json",
            "seo": "seo/analysis.json",
            "content_seo": "seo/content.json",
            "site_story": "seo/site_story.json",
            "conversion_path": "seo/conversion_path.json",
            "siteone": "seo/siteone_summary.json",
            "siteone_html": "reports/siteone/report.html",
            "siteone_json": "reports/siteone/report.json",
            "technologies": "technologies/technologies.json",
            "upgrades": "technologies/upgrades.json",
            "lighthouse": "lighthouse/summary.json",
            "annotated_screenshots": "evidence/annotated_screenshots.json",
            "proof_zip": "reports/proof-pack.zip",
            "proof_index": "reports/index.html",
            "reports_manifest": "reports/manifest.json",
            "pack": PACK_FILENAME,
        },
    }
    return pack


def write_evidence_pack(root: Path, pack: dict) -> Path:
    path = root / PACK_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    return path


def build_and_write_evidence_pack(
    root: Path,
    *,
    website: dict | None = None,
    crawl: dict | None = None,
) -> dict:
    pack = build_evidence_pack(root, website=website, crawl=crawl)
    write_evidence_pack(root, pack)
    return pack
