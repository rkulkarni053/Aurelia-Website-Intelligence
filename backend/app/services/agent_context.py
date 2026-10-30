"""Unified commercial context for the generative Brain / design agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_sell_recommendation(root: Path) -> dict | None:
    path = root / "proposal" / "sell_recommendation.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def compact_opportunities(opportunities: list[dict] | None, *, max_items: int = 10) -> list[dict]:
    out = []
    for o in opportunities or []:
        status = (o.get("status") or "").lower()
        if status == "rejected":
            continue
        out.append(
            {
                "id": str(o.get("id")) if o.get("id") else None,
                "theme_key": o.get("theme_key"),
                "client_title": o.get("client_title") or o.get("title"),
                "problem": (o.get("problem") or "")[:280],
                "business_impact": (o.get("business_impact") or "")[:220],
                "recommendation": (o.get("recommendation") or "")[:220],
                "priority": o.get("priority"),
                "status": o.get("status"),
                "proposal_status": o.get("proposal_status"),
                "selected_package": o.get("selected_package"),
                "category": o.get("category"),
                "evidence_count": o.get("evidence_count")
                or (o.get("evidence") or {}).get("finding_count"),
                "commercial_score": o.get("commercial_score"),
            }
        )
        if len(out) >= max_items:
            break
    return out


def agency_snippet(agency: dict | None) -> dict:
    agency = agency or {}
    branding = agency.get("branding") or {}
    packages = agency.get("packages") or {}
    return {
        "agency_name": branding.get("agency_name") or "Aurelia",
        "tagline": branding.get("tagline") or "",
        "methodology": (agency.get("methodology") or "")[:800],
        "packages": {
            k: {
                "name": v.get("name") or k,
                "price": v.get("price"),
                "summary": (v.get("summary") or "")[:160],
            }
            for k, v in packages.items()
        },
        "currency": agency.get("currency") or "EUR",
        "recommended_package_default": agency.get("recommended_package_default") or "growth",
    }


def build_agent_context(
    *,
    evidence_pack: dict | None = None,
    recommendations: dict | None = None,
    opportunities: list[dict] | None = None,
    sell_recommendation: dict | None = None,
    agency: dict | None = None,
    root: Path | None = None,
    include_few_shot: bool = True,
) -> dict[str, Any]:
    """Compact context shared by Brain and design chat."""
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.feedback_store import format_few_shot_block, load_examples

    pack = evidence_pack or {}
    agency = agency or load_agency_settings()
    if sell_recommendation is None and root is not None:
        sell_recommendation = load_sell_recommendation(root)

    # Prefer crawl site_story; enrich with brain summary if present
    rec_payload = recommendations or {}
    recs = rec_payload.get("recommendations") or {}
    raw_story = pack.get("site_story") or {}
    brain_story = recs.get("site_story_summary") or {}
    site_story = {
        "business_type": brain_story.get("business_type")
        or raw_story.get("likely_business_name")
        or "",
        "audience": brain_story.get("audience") or "",
        "story": brain_story.get("story")
        or (raw_story.get("value_prop_candidates") or [None])[0]
        or (raw_story.get("headlines") or [None])[0]
        or "",
        "offer": brain_story.get("offer")
        or (raw_story.get("calls_to_action") or [None])[0]
        or "",
        "tone": brain_story.get("tone") or "",
        "gaps": brain_story.get("gaps")
        or ([] if raw_story.get("about_present") else ["No dedicated About page found."]),
        "headlines": (raw_story.get("headlines") or [])[:6],
        "calls_to_action": (raw_story.get("calls_to_action") or [])[:6],
        "value_props": (raw_story.get("value_prop_candidates") or [])[:4],
    }

    findings = pack.get("findings") or {}
    top = []
    for item in findings.get("top") or []:
        if not isinstance(item, dict):
            continue
        code = (item.get("code") or "").lower()
        title = (item.get("title") or "").lower()
        # Skip infra noise
        if any(
            x in code or x in title
            for x in ("playwright", "browser_tooling", "page_render_failed", "static-html")
        ):
            continue
        top.append(
            {
                "severity": item.get("severity"),
                "category": item.get("category"),
                "title": item.get("title"),
                "description": (item.get("description") or "")[:160],
            }
        )
        if len(top) >= 8:
            break

    opp_list = compact_opportunities(opportunities)
    sell = None
    if sell_recommendation:
        sell = {
            "recommended_package": sell_recommendation.get("recommended_package"),
            "package_name": sell_recommendation.get("package_name"),
            "price": sell_recommendation.get("price"),
            "currency": sell_recommendation.get("currency"),
            "why": (sell_recommendation.get("why") or sell_recommendation.get("reasons") or [])[
                :6
            ],
            "accepted": bool(sell_recommendation.get("accepted")),
        }

    company_profile = None
    if root is not None:
        try:
            from backend.app.services.company_profile import ensure_company_profile

            profile = ensure_company_profile(root, pack)
            company_profile = {
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
            }
            # Prefer real brand over SEO niche title in site_story.
            if company_profile.get("brand"):
                site_story["business_type"] = company_profile["brand"]
            if company_profile.get("one_liner"):
                site_story["story"] = company_profile["one_liner"]
            if company_profile.get("audience"):
                site_story["audience"] = company_profile["audience"]
            if company_profile.get("services"):
                site_story["offer"] = ", ".join(company_profile["services"][:4])
        except Exception:
            company_profile = None

    ctx: dict[str, Any] = {
        "role": "agency_generative_agent",
        "website": pack.get("website") or rec_payload.get("website"),
        "scores": pack.get("scores") or rec_payload.get("scores"),
        "company_profile": company_profile,
        "site_story": site_story,
        "opportunities": opp_list,
        "sell_recommendation": sell,
        "agency": agency_snippet(agency),
        "findings_summary": {
            "total": findings.get("total"),
            "by_severity": findings.get("by_severity"),
            "by_category": findings.get("by_category"),
            "top": top,
        },
        "conversion_path": {
            "strength": (pack.get("conversion_path") or {}).get("strength"),
            "gaps": ((pack.get("conversion_path") or {}).get("gaps") or [])[:5],
        },
        "technologies": [
            d.get("name") or d.get("technology")
            for d in ((pack.get("technologies") or {}).get("detections") or [])[:10]
            if isinstance(d, dict)
        ],
        "priority_actions": [
            {
                "title": a.get("title") if isinstance(a, dict) else str(a),
                "why": ((a.get("why") or "")[:160] if isinstance(a, dict) else ""),
                "impact": a.get("impact") if isinstance(a, dict) else None,
                "category": a.get("category") if isinstance(a, dict) else None,
            }
            for a in (recs.get("priority_actions") or [])[:5]
        ],
        "quick_wins": (recs.get("quick_wins") or [])[:5],
        "executive_summary": (recs.get("executive_summary") or "")[:500],
    }

    if include_few_shot:
        industry = None
        if company_profile:
            industry = company_profile.get("industry")
        block = format_few_shot_block(
            load_examples(limit=4, industry=industry),
            max_chars=3200,
        )
        if block:
            ctx["agency_examples"] = block

    return ctx


def _compact_perf_pages(pack: dict, *, limit: int = 4) -> list[dict]:
    pages = ((pack.get("performance") or {}).get("pages") or [])[:limit]
    out = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        bytes_ = page.get("total_transfer_bytes")
        out.append(
            {
                "url": page.get("url"),
                "lcp_ms": page.get("lcp_ms"),
                "fcp_ms": page.get("fcp_ms"),
                "transfer_mb": round(bytes_ / 1_000_000, 2) if isinstance(bytes_, (int, float)) else None,
                "requests": page.get("total_requests"),
            }
        )
    return out


def _compact_a11y(pack: dict) -> dict:
    pages = (pack.get("accessibility") or {}).get("pages") or []
    worst = sorted(
        [p for p in pages if isinstance(p, dict)],
        key=lambda p: int(p.get("violation_count") or 0),
        reverse=True,
    )[:5]
    a11y_findings = [
        {
            "title": f.get("title"),
            "pages_affected": f.get("occurrences") or f.get("count"),
        }
        for f in ((pack.get("findings") or {}).get("top") or [])
        if isinstance(f, dict) and (f.get("category") or "") == "accessibility"
    ][:5]
    return {
        "pages_with_violations": sum(
            1 for p in pages if isinstance(p, dict) and int(p.get("violation_count") or 0) > 0
        ),
        "worst_pages": [
            {"url": p.get("url"), "violation_count": p.get("violation_count")} for p in worst
        ],
        "top_issues": a11y_findings,
    }


def _compact_seo_signals(pack: dict) -> dict:
    seo = pack.get("seo") or {}
    content = pack.get("content_seo") or {}
    return {
        "robots_found": seo.get("robots_found"),
        "sitemap_found": seo.get("sitemap_found"),
        "thin_content_pages": content.get("thin_content_pages"),
        "missing_h1_pages": content.get("missing_h1_pages"),
        "pages_analyzed": content.get("pages_analyzed"),
    }


def _compact_lighthouse(pack: dict) -> dict:
    lh = pack.get("lighthouse") or {}
    agg = lh.get("aggregate") or {}
    if not agg and isinstance(lh.get("pages"), list) and lh["pages"]:
        # Fall back to first page categories if aggregate missing
        first = lh["pages"][0] if isinstance(lh["pages"][0], dict) else {}
        cats = first.get("categories") or first.get("scores") or {}
        agg = cats
    return {
        "source": lh.get("source"),
        "aggregate": {
            k: agg.get(k)
            for k in ("performance", "accessibility", "best-practices", "best_practices", "seo")
            if agg.get(k) is not None
        }
        or agg,
    }


def _score_gaps(pack: dict) -> dict:
    """Weakest score categories — what a redesign must beat."""
    by_cat = (pack.get("scores") or {}).get("by_category") or {}
    overall = (pack.get("scores") or {}).get("overall")
    ranked = sorted(
        ((str(k), float(v)) for k, v in by_cat.items() if isinstance(v, (int, float))),
        key=lambda kv: kv[1],
    )
    return {
        "overall": overall,
        "weakest": [{"category": k, "score": v} for k, v in ranked[:4]],
        "strongest": [{"category": k, "score": v} for k, v in ranked[-2:]] if ranked else [],
        "target_overall": (
            min(10.0, round(float(overall) + 0.8, 1))
            if isinstance(overall, (int, float))
            else None
        ),
    }


def shrink_for_brain(ctx: dict, pack: dict, *, max_findings: int = 8) -> dict:
    """Lean Brain prompt: all signal types, small enough for local 4k context."""
    story = pack.get("site_story") or {}
    story_pages = []
    for page in (story.get("pages") or [])[:3]:
        if not isinstance(page, dict):
            continue
        story_pages.append(
            {
                "role": page.get("role"),
                "title": (page.get("title") or "")[:80],
                "h1": (page.get("h1") or [])[:1],
                "ctas": (page.get("ctas") or [])[:3],
                "excerpt": (page.get("excerpt") or page.get("body_excerpt") or "")[:280],
            }
        )

    conv = pack.get("conversion_path") or {}
    ssl = pack.get("ssl") or {}
    a11y = _compact_a11y(pack)
    # Trim a11y further for prompt size
    a11y = {
        "pages_with_violations": a11y.get("pages_with_violations"),
        "worst_pages": (a11y.get("worst_pages") or [])[:3],
        "top_issues": [
            {"title": (i.get("title") or "")[:80]}
            for i in (a11y.get("top_issues") or [])[:3]
        ],
    }

    return {
        "goal": (
            "Raise overall score + conversion. Use opportunities + weak categories. "
            "Benefit-led hero copy — never SEO page titles. Client language only. "
            "Match agency training examples for voice and CTA specificity."
        ),
        "website": ctx.get("website"),
        "scores": ctx.get("scores"),
        "score_gaps": _score_gaps(pack),
        "company_profile": ctx.get("company_profile"),
        "site_story": ctx.get("site_story"),
        "site_story_pages": story_pages,
        "opportunities": (ctx.get("opportunities") or [])[:8],
        "sell_recommendation": ctx.get("sell_recommendation"),
        "agency": {
            "agency_name": ((ctx.get("agency") or {}).get("agency_name")),
            "methodology": ((ctx.get("agency") or {}).get("methodology") or "")[:400],
            "packages": (ctx.get("agency") or {}).get("packages"),
        },
        "performance": _compact_perf_pages(pack, limit=3),
        "accessibility": a11y,
        "seo_signals": _compact_seo_signals(pack),
        "lighthouse": _compact_lighthouse(pack),
        "ssl": {
            "https_enabled": ssl.get("https_enabled"),
            "certificate_valid": ssl.get("certificate_valid"),
            "http_to_https_status": ssl.get("http_to_https_status"),
        },
        "conversion_path": {
            "strength": conv.get("strength"),
            "gaps": (conv.get("gaps") or [])[:4],
            "contact_pages": len(conv.get("contact_pages") or []),
            "about": bool(conv.get("about")),
        },
        "findings_top": (
            (ctx.get("findings_summary") or {}).get("top") or []
        )[:max_findings],
        "technologies": (ctx.get("technologies") or [])[:8],
        "screenshots_count": len(pack.get("screenshots") or [])
        if isinstance(pack.get("screenshots"), list)
        else 0,
    }
