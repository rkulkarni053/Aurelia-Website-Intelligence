"""Generate and persist commercial Opportunities from crawl evidence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.opportunity import (
    Opportunity,
    OpportunityStatus,
    ProposalItemStatus,
)
from backend.app.services.commercial_score import (
    opportunity_commercial_score,
    recommend_package_from_opportunities,
    suggest_package_for_theme,
)
from backend.app.services.finding_clusters import client_title, dedupe_findings

MANIFEST = "evidence/opportunities.json"

THEME_DEFS: list[dict[str, Any]] = [
    {
        "key": "accessibility",
        "title": "Improve accessibility and readability",
        "client_title": "Improve accessibility and readability across the website",
        "match": lambda f: (f.get("code") or "").startswith("a11y_")
        or (f.get("category") or "") == "accessibility",
        "impact_business": 3,
        "impact_ux": 4,
        "impact_content": 1,
        "impact_technical": 3,
        "scope_complexity": 2,
        "category": "accessibility",
        "recommendation": "Remediate high-impact accessibility issues so the site is easier to use and clearer to read.",
        "business_impact": "Hard-to-read text and unclear controls reduce trust and can exclude customers — and create compliance risk.",
    },
    {
        "key": "seo_basics",
        "title": "Strengthen search foundations",
        "client_title": "Strengthen search visibility foundations",
        "match": lambda f: (f.get("code") or "")
        in {
            "missing_title",
            "missing_meta_description",
            "missing_h1",
            "thin_content",
            "title_too_short",
            "title_too_long",
            "meta_description_too_short",
            "meta_description_too_long",
            "missing_robots",
            "missing_sitemap",
        }
        or (
            (f.get("category") or "") == "seo"
            and (f.get("code") or "").startswith(("missing_", "title_", "meta_", "thin_"))
        ),
        "impact_business": 3,
        "impact_ux": 1,
        "impact_content": 3,
        "impact_technical": 2,
        "scope_complexity": 2,
        "category": "seo",
        "recommendation": "Fix titles, meta descriptions, headings, and sitemap/robots so search engines and visitors understand each page.",
        "business_impact": "Weak titles and snippets make it harder for prospects to find and choose the business in search.",
    },
    {
        "key": "performance",
        "title": "Improve page speed and first impression",
        "client_title": "Make the website feel faster, especially on mobile",
        "match": lambda f: (f.get("category") or "") == "performance"
        or "lcp" in (f.get("code") or "").lower()
        or "transfer" in (f.get("code") or "").lower()
        or "weight" in ((f.get("title") or "") + (f.get("code") or "")).lower(),
        "impact_business": 3,
        "impact_ux": 4,
        "impact_content": 0,
        "impact_technical": 4,
        "scope_complexity": 3,
        "category": "performance",
        "recommendation": "Optimize hero media and above-the-fold resources so the homepage becomes usable quickly.",
        "business_impact": "Slow first paint weakens first impressions and can reduce engagement and enquiries.",
    },
    {
        "key": "security",
        "title": "Restore trust and HTTPS hygiene",
        "client_title": "Improve site security and visitor trust signals",
        "match": lambda f: (f.get("category") or "") == "security"
        or (f.get("code") or "").startswith("ssl_")
        or (f.get("code") or "") in {"no_https_redirect"},
        "impact_business": 4,
        "impact_ux": 1,
        "impact_content": 0,
        "impact_technical": 3,
        "scope_complexity": 2,
        "category": "security",
        "recommendation": "Resolve HTTPS, certificate, and related trust issues that visitors and browsers surface.",
        "business_impact": "Security warnings and weak HTTPS undermine confidence before a visitor even reads the offer.",
    },
    {
        "key": "conversion",
        "title": "Clarify the conversion path",
        "client_title": "Improve homepage conversion and primary calls to action",
        "match": lambda f: (f.get("code") or "")
        in {"weak_cta_path", "missing_contact_path", "unclear_cta", "competing_ctas"}
        or (f.get("category") or "") in {"ux", "conversion"},
        "impact_business": 5,
        "impact_ux": 5,
        "impact_content": 3,
        "impact_technical": 1,
        "scope_complexity": 3,
        "category": "conversion",
        "recommendation": "Redesign homepage and key journey steps around one clear primary action and a cleaner path to enquiry.",
        "business_impact": "Unclear CTAs and competing actions lose enquiries even when traffic is healthy.",
    },
    {
        "key": "content",
        "title": "Strengthen messaging and service clarity",
        "client_title": "Clarify what the business offers and who it serves",
        "match": lambda f: (f.get("category") or "") == "content"
        or (f.get("code") or "") in {"thin_content", "weak_positioning", "unclear_offer"},
        "impact_business": 4,
        "impact_ux": 2,
        "impact_content": 5,
        "impact_technical": 0,
        "scope_complexity": 3,
        "category": "content",
        "recommendation": "Rewrite homepage and service messaging so visitors immediately understand the offer, audience, and next step.",
        "business_impact": "Vague positioning makes it harder for the right clients to recognise a fit and take action.",
    },
    {
        "key": "stack",
        "title": "Modernise the technology foundation",
        "client_title": "Upgrade the website platform where it is holding the business back",
        "match": lambda f: (f.get("code") or "")
        in {"cms_upgrade_opportunity", "stack_gap", "outdated_cms"}
        or (f.get("category") or "") == "stack",
        "impact_business": 3,
        "impact_ux": 2,
        "impact_content": 1,
        "impact_technical": 4,
        "scope_complexity": 4,
        "category": "technical",
        "recommendation": "Plan a platform or stack upgrade that reduces maintenance risk and unlocks modern UX and SEO work.",
        "business_impact": "Outdated platforms slow delivery, raise security risk, and limit conversion improvements.",
    },
    {
        "key": "technical",
        "title": "Resolve technical quality issues",
        "client_title": "Clean up technical quality issues affecting reliability",
        "match": lambda f: (f.get("category") or "") in {"technical", "best-practices"}
        or True,  # catch-all — applied last
        "impact_business": 2,
        "impact_ux": 1,
        "impact_content": 0,
        "impact_technical": 3,
        "scope_complexity": 2,
        "category": "technical",
        "recommendation": "Address remaining technical quality issues that affect reliability and maintainability.",
        "business_impact": "Unresolved technical debt makes future improvements slower and riskier.",
        "catch_all": True,
    },
]


def _severity_rank(sev: str | None) -> int:
    return {"high": 0, "medium": 1, "low": 2, "info": 3}.get((sev or "info").lower(), 9)


def _strip_jargon(text: str) -> str:
    cleaned = (text or "")
    for token in (
        "WCAG 2 AA minimum contrast ratio thresholds",
        "WCAG 2 AA",
        "WCAG",
        "axe-core",
        "SiteOne Crawler: ",
        "Lighthouse",
        "`a11y_color-contrast`",
        "a11y_color-contrast",
    ):
        cleaned = cleaned.replace(token, "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip(" .")


def _client_problem(theme: dict, sample_title: str, pages_n: int, sample_urls: list) -> str:
    """Business-facing problem statement — never dump collector jargon."""
    templates = {
        "accessibility": (
            f"{sample_title}. This affects about {pages_n} pages, making parts of the site harder to read and use."
        ),
        "performance": (
            f"Key pages take longer than expected to become visually usable, particularly on mobile "
            f"({pages_n} pages flagged)."
        ),
        "seo_basics": (
            f"Search and page basics need attention across roughly {pages_n} pages — titles, snippets, "
            f"or thin copy make the offer harder to discover."
        ),
        "security": (
            "Trust and HTTPS signals need attention so visitors are not warned away before they engage."
        ),
        "conversion": (
            "The homepage does not establish a clear primary action and has competing or unclear CTAs."
        ),
        "content": (
            "Homepage messaging does not clearly explain the offer, audience, and why to act now."
        ),
        "stack": (
            "The current platform is limiting how quickly the site can be improved and maintained."
        ),
        "technical": (
            f"Several technical quality issues ({pages_n} signals) affect reliability and maintainability."
        ),
    }
    base = templates.get(theme["key"]) or f"{sample_title}. Affects approximately {pages_n} pages."
    if sample_urls:
        base += " Examples: " + "; ".join(sample_urls[:3])
    return _strip_jargon(base)


def _priority_from_group(findings: list[dict], theme: dict) -> str:
    if any((f.get("severity") or "").lower() == "high" for f in findings):
        return "high"
    if theme["key"] in {"conversion", "content", "positioning"}:
        return "high"
    if any((f.get("severity") or "").lower() == "medium" for f in findings):
        return "medium"
    return "low"


def _effort_from_count(n: int, complexity: int) -> str:
    if n >= 10 or complexity >= 4:
        return "high"
    if n >= 3 or complexity >= 3:
        return "medium"
    return "low"


def _load_findings(root: Path, db: Session, crawl_id: uuid.UUID) -> list[dict]:
    from backend.app.models.finding import Finding

    path = root / "evidence" / "findings.json"
    rows: list[dict] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            rows = raw
    except (FileNotFoundError, json.JSONDecodeError):
        rows = []

    db_findings = list(
        db.execute(select(Finding).where(Finding.crawl_id == crawl_id)).scalars().all()
    )
    by_key: dict[tuple, dict] = {}
    for f in rows:
        key = (f.get("code"), f.get("url") or "")
        by_key[key] = dict(f)

    for f in db_findings:
        key = (f.code, f.url or "")
        entry = by_key.get(key) or {
            "code": f.code,
            "severity": f.severity,
            "category": f.category,
            "title": f.title,
            "description": f.description,
            "url": f.url,
            "detail": f.detail,
        }
        entry["id"] = str(f.id)
        by_key[key] = entry

    return dedupe_findings(list(by_key.values()))


def _conversion_opportunities(root: Path) -> list[dict]:
    """Extra opportunities from conversion-path / site story when present."""
    extras: list[dict] = []
    pack_path = root / "evidence" / "evidence_pack.json"
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pack = {}

    conv = pack.get("conversion_path") or {}
    gaps = conv.get("gaps") or []
    strength = (conv.get("strength") or "").lower()
    if gaps or strength in {"weak", "poor", "low"}:
        extras.append(
            {
                "theme_key": "conversion",
                "title": "Improve homepage conversion",
                "client_title": "Improve homepage conversion and primary calls to action",
                "problem": (
                    gaps[0]
                    if gaps
                    else "The homepage does not establish a clear primary action and has competing or unclear CTAs."
                ),
                "business_impact": "Visitors who do not immediately understand what to do next are less likely to enquire.",
                "recommendation": "Homepage UX + messaging redesign around a single primary CTA and clearer journey.",
                "category": "conversion",
                "priority": "high",
                "impact_business": 5,
                "impact_ux": 5,
                "impact_content": 3,
                "impact_technical": 1,
                "scope_complexity": 3,
                "evidence": {
                    "type": "conversion_path",
                    "gaps": gaps[:6],
                    "strength": conv.get("strength"),
                    "funnel": conv.get("funnel") or [],
                },
                "source_finding_ids": [],
                "source_cluster_ids": ["conversion_path"],
                "finding_count": len(gaps) or 1,
            }
        )

    story = ((pack.get("site_story") or {}).get("gaps")) or []
    if not story:
        # brain / seo story
        try:
            site_story = json.loads((root / "seo" / "site_story.json").read_text(encoding="utf-8"))
            story = site_story.get("gaps") or []
        except (FileNotFoundError, json.JSONDecodeError):
            story = []
    if story:
        extras.append(
            {
                "theme_key": "content",
                "title": "Clarify business positioning",
                "client_title": "Clarify what the business offers and who it serves",
                "problem": story[0]
                if isinstance(story[0], str)
                else "Homepage messaging does not clearly explain the offer and audience.",
                "business_impact": "Prospects cannot quickly tell if this is the right provider for them.",
                "recommendation": "Rewrite positioning on the homepage and key service pages.",
                "category": "content",
                "priority": "high",
                "impact_business": 4,
                "impact_ux": 2,
                "impact_content": 5,
                "impact_technical": 0,
                "scope_complexity": 3,
                "evidence": {"type": "site_story", "gaps": story[:6]},
                "source_finding_ids": [],
                "source_cluster_ids": ["site_story"],
                "finding_count": len(story),
            }
        )
    return extras


def build_opportunity_drafts(root: Path, db: Session, crawl_id: uuid.UUID) -> list[dict]:
    findings = _load_findings(root, db, crawl_id)
    assigned: set[int] = set()
    drafts: list[dict] = []

    for theme in THEME_DEFS:
        group = []
        indexes = []
        for i, f in enumerate(findings):
            if i in assigned:
                continue
            if theme["match"](f):
                # catch-all only takes leftovers that aren't already themed
                if theme.get("catch_all") and (f.get("severity") or "").lower() == "info":
                    continue
                group.append(f)
                indexes.append(i)
        if not group:
            continue
        if theme.get("catch_all") and len(group) < 2 and not any(
            (f.get("severity") or "").lower() == "high" for f in group
        ):
            # skip tiny residual noise
            if len(group) == 1 and (group[0].get("severity") or "").lower() == "low":
                continue

        for i in indexes:
            assigned.add(i)

        page_urls = []
        finding_ids = []
        cluster_ids = []
        for f in group:
            if f.get("id"):
                finding_ids.append(f["id"])
            code = f.get("code") or "issue"
            cluster_ids.append(code)
            detail = f.get("detail") or {}
            for u in detail.get("sample_urls") or []:
                if u and u not in page_urls:
                    page_urls.append(u)
            if f.get("url") and f["url"] not in page_urls:
                page_urls.append(f["url"])

        priority = _priority_from_group(group, theme)
        sample_title = client_title(group[0]) if group else theme["client_title"]
        pages_n = len(page_urls) or len(group)
        problem = _client_problem(theme, sample_title, pages_n, page_urls[:3])

        drafts.append(
            {
                "theme_key": theme["key"],
                "title": theme["title"],
                "client_title": theme["client_title"],
                "problem": problem[:1200],
                "business_impact": theme["business_impact"],
                "recommendation": theme["recommendation"],
                "category": theme["category"],
                "priority": priority,
                "impact_business": theme["impact_business"],
                "impact_ux": theme["impact_ux"],
                "impact_content": theme["impact_content"],
                "impact_technical": theme["impact_technical"],
                "scope_complexity": theme["scope_complexity"],
                "estimated_effort": _effort_from_count(len(group), theme["scope_complexity"]),
                "selected_package": suggest_package_for_theme(theme["key"], priority=priority),
                "evidence": {
                    "type": "finding_cluster",
                    "finding_count": len(group),
                    "codes": sorted({f.get("code") for f in group if f.get("code")}),
                    "sample_titles": [client_title(f) for f in group[:5]],
                    "sample_urls": page_urls[:8],
                    "severities": {
                        "high": sum(1 for f in group if (f.get("severity") or "").lower() == "high"),
                        "medium": sum(1 for f in group if (f.get("severity") or "").lower() == "medium"),
                        "low": sum(1 for f in group if (f.get("severity") or "").lower() == "low"),
                    },
                },
                "source_finding_ids": finding_ids,
                "source_cluster_ids": list(dict.fromkeys(cluster_ids))[:20],
                "finding_count": len(group),
            }
        )

    # Merge conversion/story extras if theme not already present
    existing_keys = {d["theme_key"] for d in drafts}
    for extra in _conversion_opportunities(root):
        if extra["theme_key"] in existing_keys:
            # boost existing
            for d in drafts:
                if d["theme_key"] == extra["theme_key"]:
                    d["priority"] = "high"
                    d["impact_ux"] = max(d["impact_ux"], extra["impact_ux"])
                    d["impact_business"] = max(d["impact_business"], extra["impact_business"])
                    ev = dict(d.get("evidence") or {})
                    ev["conversion"] = extra.get("evidence")
                    d["evidence"] = ev
                    if extra.get("problem") and len(extra["problem"]) > 20:
                        d["problem"] = extra["problem"]
                    break
        else:
            extra["estimated_effort"] = _effort_from_count(
                extra.get("finding_count") or 1, extra["scope_complexity"]
            )
            extra["selected_package"] = suggest_package_for_theme(
                extra["theme_key"], priority=extra["priority"]
            )
            drafts.append(extra)
            existing_keys.add(extra["theme_key"])

    drafts.sort(key=lambda d: (_severity_rank(d.get("priority")), -opportunity_commercial_score(d)))
    return drafts


def opportunity_to_dict(row: Opportunity) -> dict:
    evidence = row.evidence or {}
    evidence_count = int(
        evidence.get("finding_count")
        or len(row.source_finding_ids or [])
        or len((evidence.get("sample_urls") or []))
        or 1
    )
    data = {
        "id": row.id,
        "project_id": row.project_id,
        "website_id": row.website_id,
        "crawl_id": row.crawl_id,
        "source_finding_ids": row.source_finding_ids or [],
        "source_cluster_ids": row.source_cluster_ids or [],
        "title": row.title,
        "client_title": row.client_title,
        "problem": row.problem,
        "evidence": evidence,
        "business_impact": row.business_impact,
        "recommendation": row.recommendation,
        "impact_business": row.impact_business,
        "impact_ux": row.impact_ux,
        "impact_content": row.impact_content,
        "impact_technical": row.impact_technical,
        "scope_complexity": row.scope_complexity,
        "category": row.category,
        "priority": row.priority,
        "estimated_effort": row.estimated_effort,
        "estimated_value": row.estimated_value,
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "proposal_status": (
            row.proposal_status.value
            if hasattr(row.proposal_status, "value")
            else str(row.proposal_status)
        ),
        "selected_package": row.selected_package,
        "theme_key": row.theme_key,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "evidence_count": evidence_count,
        "commercial_score": opportunity_commercial_score(
            {
                "impact_business": row.impact_business,
                "impact_ux": row.impact_ux,
                "impact_content": row.impact_content,
                "impact_technical": row.impact_technical,
                "scope_complexity": row.scope_complexity,
            }
        ),
    }
    return data


def list_opportunities(db: Session, crawl_id: uuid.UUID) -> list[dict]:
    rows = list(
        db.execute(
            select(Opportunity)
            .where(Opportunity.crawl_id == crawl_id)
            .order_by(Opportunity.created_at.asc())
        )
        .scalars()
        .all()
    )
    return [opportunity_to_dict(r) for r in rows]


def generate_opportunities(
    db: Session,
    *,
    root: Path,
    project_id: uuid.UUID,
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    replace: bool = False,
) -> list[dict]:
    existing = list(
        db.execute(select(Opportunity).where(Opportunity.crawl_id == crawl_id)).scalars().all()
    )
    if existing and not replace:
        # Keep human decisions; only regenerate if empty
        return [opportunity_to_dict(r) for r in existing]

    if existing and replace:
        # Preserve statuses for matching theme_keys
        prior = {r.theme_key: r for r in existing if r.theme_key}
        for r in existing:
            db.delete(r)
        db.flush()
    else:
        prior = {}

    drafts = build_opportunity_drafts(root, db, crawl_id)
    now = datetime.now(timezone.utc)
    created: list[Opportunity] = []
    for draft in drafts:
        old = prior.get(draft["theme_key"])
        status = OpportunityStatus.NEW
        proposal_status = ProposalItemStatus.NOT_IN_PROPOSAL
        if old is not None:
            status = old.status
            proposal_status = old.proposal_status
        row = Opportunity(
            id=uuid.uuid4(),
            project_id=project_id,
            website_id=website_id,
            crawl_id=crawl_id,
            source_finding_ids=draft.get("source_finding_ids") or [],
            source_cluster_ids=draft.get("source_cluster_ids") or [],
            title=draft["title"],
            client_title=draft["client_title"],
            problem=draft["problem"],
            evidence=draft.get("evidence") or {},
            business_impact=draft["business_impact"],
            recommendation=draft["recommendation"],
            impact_business=draft["impact_business"],
            impact_ux=draft["impact_ux"],
            impact_content=draft["impact_content"],
            impact_technical=draft["impact_technical"],
            scope_complexity=draft["scope_complexity"],
            category=draft["category"],
            priority=draft["priority"],
            estimated_effort=draft.get("estimated_effort") or "medium",
            estimated_value=draft.get("estimated_value"),
            status=status,
            proposal_status=proposal_status,
            selected_package=draft.get("selected_package"),
            theme_key=draft["theme_key"],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)

    payload = [opportunity_to_dict(r) for r in created]
    _write_manifest(root, crawl_id, payload)
    return payload


def _write_manifest(root: Path, crawl_id: uuid.UUID, opportunities: list[dict]) -> None:
    path = root / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for o in opportunities:
        item = dict(o)
        for key in ("id", "project_id", "website_id", "crawl_id"):
            if key in item and item[key] is not None:
                item[key] = str(item[key])
        for key in ("created_at", "updated_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat() if hasattr(item[key], "isoformat") else item[key]
        serializable.append(item)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "crawl_id": str(crawl_id),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "opportunities": serializable,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def patch_opportunity(
    db: Session,
    opportunity_id: uuid.UUID,
    *,
    crawl_id: uuid.UUID,
    patch: dict,
) -> dict | None:
    row = db.get(Opportunity, opportunity_id)
    if row is None or row.crawl_id != crawl_id:
        return None

    if patch.get("status"):
        row.status = OpportunityStatus(patch["status"])
        if row.status == OpportunityStatus.APPROVED and row.proposal_status == ProposalItemStatus.NOT_IN_PROPOSAL:
            row.proposal_status = ProposalItemStatus.SELECTED
        if row.status == OpportunityStatus.REJECTED:
            row.proposal_status = ProposalItemStatus.NOT_IN_PROPOSAL
    if patch.get("proposal_status"):
        row.proposal_status = ProposalItemStatus(patch["proposal_status"])
        if row.proposal_status in {ProposalItemStatus.SELECTED, ProposalItemStatus.INCLUDED}:
            if row.status in {OpportunityStatus.NEW, OpportunityStatus.REVIEW}:
                row.status = OpportunityStatus.APPROVED
    if "selected_package" in patch:
        row.selected_package = patch["selected_package"]
    for field in (
        "title",
        "client_title",
        "problem",
        "business_impact",
        "recommendation",
        "priority",
        "estimated_effort",
    ):
        if field in patch and patch[field] is not None:
            setattr(row, field, patch[field])
    if "estimated_value" in patch:
        row.estimated_value = patch["estimated_value"]

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return opportunity_to_dict(row)


def selected_for_proposal(opportunities: list[dict]) -> list[dict]:
    out = []
    for o in opportunities:
        status = (o.get("status") or "").lower()
        pstatus = (o.get("proposal_status") or "").lower()
        if status in {"rejected", "deferred"}:
            continue
        if pstatus in {"selected", "included"} or status in {"approved", "sold"}:
            out.append(o)
    return out


def build_sell_recommendation(
    opportunities: list[dict],
    *,
    config: dict,
    accepted_package: str | None = None,
) -> dict:
    rec = recommend_package_from_opportunities(opportunities, config=config)
    if accepted_package and accepted_package in (config.get("packages") or {}):
        pkg = (config.get("packages") or {})[accepted_package]
        rec["recommended_package"] = accepted_package
        rec["package_name"] = pkg.get("name") or accepted_package
        rec["price"] = pkg.get("price")
        rec["duration_days"] = pkg.get("duration_days")
        rec["summary"] = pkg.get("summary") or ""
        rec["accepted"] = True
    else:
        rec["accepted"] = False
    return rec

