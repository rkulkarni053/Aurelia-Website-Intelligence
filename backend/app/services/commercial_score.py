"""Commercial scoring and package recommendation from Opportunities.

Never recommend packages from raw finding counts.
"""

from __future__ import annotations

from typing import Any


PACKAGE_ORDER = ("essentials", "growth", "redesign")

# Theme → default package suggestion for a single opportunity
THEME_PACKAGE = {
    "accessibility": "essentials",
    "seo_basics": "essentials",
    "security": "essentials",
    "performance": "growth",
    "conversion": "growth",
    "content": "growth",
    "ux": "growth",
    "positioning": "redesign",
    "visual_design": "redesign",
    "stack": "growth",
    "technical": "essentials",
}


def opportunity_commercial_score(opp: dict[str, Any]) -> int:
    """0–25 composite from impact dimensions."""
    return (
        int(opp.get("impact_business") or 0)
        + int(opp.get("impact_ux") or 0)
        + int(opp.get("impact_content") or 0)
        + int(opp.get("impact_technical") or 0)
        + int(opp.get("scope_complexity") or 0)
    )


def _active_opportunities(opportunities: list[dict]) -> list[dict]:
    skip = {"rejected", "deferred"}
    return [o for o in opportunities if (o.get("status") or "new").lower() not in skip]


def score_portfolio(opportunities: list[dict]) -> dict[str, Any]:
    """Aggregate commercial signals from opportunities (not raw findings)."""
    active = _active_opportunities(opportunities)
    approved = [o for o in active if (o.get("status") or "").lower() in {"approved", "sold", "completed", "verified", "review", "new"}]

    # Prefer approved/selected for sell decision; fall back to all non-rejected.
    pool = [o for o in active if (o.get("status") or "").lower() in {"approved", "sold", "selected"}]
    if not pool:
        pool = [o for o in active if (o.get("proposal_status") or "") in {"selected", "included"}]
    if not pool:
        pool = active

    totals = {
        "business": 0,
        "ux": 0,
        "content": 0,
        "technical": 0,
        "complexity": 0,
    }
    high = 0
    medium = 0
    conversionish = 0
    contentish = 0
    designish = 0
    for o in pool:
        totals["business"] += int(o.get("impact_business") or 0)
        totals["ux"] += int(o.get("impact_ux") or 0)
        totals["content"] += int(o.get("impact_content") or 0)
        totals["technical"] += int(o.get("impact_technical") or 0)
        totals["complexity"] += int(o.get("scope_complexity") or 0)
        pri = (o.get("priority") or "medium").lower()
        if pri == "high":
            high += 1
        elif pri == "medium":
            medium += 1
        cat = (o.get("category") or o.get("theme_key") or "").lower()
        if cat in {"conversion", "ux"} or int(o.get("impact_ux") or 0) >= 3:
            conversionish += 1
        if cat in {"content", "positioning"} or int(o.get("impact_content") or 0) >= 3:
            contentish += 1
        if cat in {"visual_design", "positioning", "redesign"} or (
            int(o.get("impact_content") or 0) >= 4 and int(o.get("impact_ux") or 0) >= 3
        ):
            designish += 1

    composite = sum(totals.values())
    return {
        "opportunity_count": len(pool),
        "active_count": len(active),
        "approved_count": len([o for o in active if (o.get("status") or "").lower() == "approved"]),
        "high_priority": high,
        "medium_priority": medium,
        "conversion_signals": conversionish,
        "content_signals": contentish,
        "design_signals": designish,
        "dimensions": totals,
        "composite": composite,
        "avg_per_opportunity": round(composite / len(pool), 1) if pool else 0,
    }


def recommend_package_from_opportunities(
    opportunities: list[dict],
    *,
    config: dict | None = None,
) -> dict[str, Any]:
    """Map commercial portfolio score → package. Never uses raw finding counts."""
    config = config or {}
    packages = config.get("packages") or {}
    default = config.get("recommended_package_default") or "growth"
    scores = score_portfolio(opportunities)
    composite = scores["composite"]
    high = scores["high_priority"]
    design = scores["design_signals"]
    conversion = scores["conversion_signals"]
    content = scores["content_signals"]
    count = scores["opportunity_count"]

    reasons: list[str] = []
    key = default

    # Redesign: coordinated visual/positioning/UX overhaul, not noise.
    if design >= 2 and (high >= 3 or composite >= 40):
        key = "redesign"
        reasons.append(f"{design} opportunities point to positioning / visual redesign")
        reasons.append(f"{high} high-priority opportunities need coordinated delivery")
    elif high >= 4 and (conversion + content) >= 3 and composite >= 32:
        key = "redesign"
        reasons.append(f"{high} high-impact opportunities spanning conversion and content")
    # Growth: conversion/UX/content/performance coordination
    elif high >= 2 or conversion >= 2 or content >= 2 or (count >= 3 and composite >= 18):
        key = "growth"
        if conversion:
            reasons.append(f"{conversion} conversion / UX opportunities")
        if content:
            reasons.append(f"{content} content / positioning opportunities")
        if high:
            reasons.append(f"{high} high-priority opportunities")
        if not reasons:
            reasons.append(f"{count} scoped opportunities with commercial score {composite}")
    # Essentials: mostly technical remediation
    else:
        key = "essentials"
        reasons.append("Issues are primarily technical remediation rather than a redesign")
        if count:
            reasons.append(f"{count} focused opportunities to close")

    if key not in packages and packages:
        for fallback in PACKAGE_ORDER:
            if fallback in packages:
                key = fallback
                break
        else:
            key = next(iter(packages))

    if key not in packages:
        key = default

    pkg = packages.get(key) or {}
    why = list(reasons)
    if scores["dimensions"]["ux"]:
        why.append(f"UX / conversion impact score: {scores['dimensions']['ux']}")
    if scores["dimensions"]["content"]:
        why.append(f"Content / positioning impact score: {scores['dimensions']['content']}")
    if scores["dimensions"]["technical"]:
        why.append(f"Technical impact score: {scores['dimensions']['technical']}")

    return {
        "recommended_package": key,
        "package_name": pkg.get("name") or key.replace("_", " ").title(),
        "price": pkg.get("price"),
        "currency": (config.get("currency") or "EUR").upper(),
        "duration_days": pkg.get("duration_days"),
        "summary": pkg.get("summary") or "",
        "why": why[:8],
        "reasons": why[:8],
        "commercial_score": scores,
        "opportunity_counts": {
            "total": scores["opportunity_count"],
            "high": high,
            "medium": scores["medium_priority"],
            "conversion": conversion,
            "content": content,
            "design": design,
        },
        "packages": {
            k: {
                "name": v.get("name") or k,
                "price": v.get("price"),
                "duration_days": v.get("duration_days"),
                "summary": v.get("summary") or "",
                "includes": list(v.get("includes") or [])[:12],
            }
            for k, v in packages.items()
        },
    }


def suggest_package_for_theme(theme_key: str, *, priority: str = "medium") -> str:
    base = THEME_PACKAGE.get(theme_key, "growth")
    if priority == "high" and base == "essentials" and theme_key in {"performance", "ux"}:
        return "growth"
    return base
