import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, get_db, settings
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.finding import Finding
from backend.app.models.page import Page
from backend.app.models.project import Project, ProjectStatus
from backend.app.models.website import Website
from backend.app.schemas.crawl import CrawlRead
from backend.app.schemas.finding import FindingRead
from backend.app.schemas.page import PageRead
from backend.app.services.annotate import annotate_screenshots
from backend.app.services.browser_collector import collect_browser_evidence
from backend.app.services.content_seo import collect_content_seo
from backend.app.services.site_story import collect_site_story
from backend.app.services.crawl_enrichment import (
    enrich_pages_with_rendered_html,
    select_browser_targets,
)
from backend.app.services.crawler import crawl_website
from backend.app.services.ssl_collector import collect_ssl
from backend.app.services.seo_collector import collect_seo
from backend.app.services.tech_detector import collect_technologies
from backend.app.services.accessibility_collector import collect_accessibility
from backend.app.services.lighthouse_collector import collect_lighthouse
from backend.app.services.brain import (
    OllamaError,
    generate_recommendations,
    load_recommendations,
    write_recommendations,
)
from backend.app.services.evidence_pack import (
    PACK_FILENAME,
    build_and_write_evidence_pack,
)
from backend.app.services.findings import analyze_crawl
from backend.app.services.demo_site import (
    generate_demo_site,
    load_demo,
)
from backend.app.services.demo_builder import build_demo_from_prompt
from backend.app.services.mockups import (
    generate_mockups,
    load_mockups,
)
from backend.app.services.design_chat import (
    load_brief,
    load_chat,
    process_chat_message,
)
from backend.app.services.social_chat import (
    ensure_social_pack,
    load_social_chat,
    process_social_chat_message,
)
from backend.app.services.social_content import load_social_content
from backend.app.services.site_design import sync_brief_from_brain
from backend.app.services.proposal import (
    generate_proposal,
    load_proposal,
    update_proposal,
    ProposalError,
)
from backend.app.services.proposal_pdf import export_proposal_pdf
from backend.app.services.verification_report import (
    generate_verification_report,
    load_verification_report,
)
from backend.app.services.checklist import (
    build_checklist,
    load_checklist,
    update_checklist_items,
)
from backend.app.services.competitor_compare import compare_competitors
from backend.app.services.vision_review import (
    list_crawl_screenshots,
    review_screenshot,
)
from backend.app.services.upgrade_advisor import build_upgrade_advice
from backend.app.services.conversion_path import analyze_conversion_path
from backend.app.services.finding_clusters import cluster_summary
from backend.app.services.siteone_collector import collect_siteone, load_siteone_summary
from backend.app.services.proof_report import (
    build_proof_pack,
    load_reports_manifest,
)
from backend.app.services.storage import (
    ensure_crawl_directories,
    get_crawl_root,
    slugify_url,
)
from backend.app.services.workflow import set_project_status


# Fallback defaults if Settings are unavailable (tests).
MAX_BROWSER_PAGES = 40

CRAWL_STAGES = [
    ("fetching", "Crawling pages"),
    ("seo", "Checking SSL, SEO and content"),
    ("siteone", "Running SiteOne SEO audit"),
    ("browser", "Capturing screenshots"),
    ("accessibility", "Running accessibility checks"),
    ("analyzing", "Analyzing findings"),
    ("lighthouse", "Scoring with Lighthouse"),
    ("packaging", "Building evidence pack & proof reports"),
]
_STAGE_INDEX = {key: idx for idx, (key, _) in enumerate(CRAWL_STAGES)}

# Background crawls run inside this process, so in-memory state is enough.
# It is lost on server restart; the endpoint then falls back to DB status.
CRAWL_PROGRESS: dict[str, dict] = {}


def _set_progress(crawl_id: uuid.UUID, stage: str, **extra) -> None:
    key = str(crawl_id)
    current = CRAWL_PROGRESS.get(key, {})
    CRAWL_PROGRESS[key] = {
        **current,
        **extra,
        "stage": stage,
        "label": dict(CRAWL_STAGES)[stage],
        "step": _STAGE_INDEX[stage] + 1,
        "total_steps": len(CRAWL_STAGES),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


router = APIRouter(
    prefix="/api/websites/{website_id}/crawls",
    tags=["crawls"],
)


def run_crawl(crawl_id: uuid.UUID) -> None:
    """Runs after the HTTP response is sent, so it needs its own DB session."""
    db = SessionLocal()

    try:
        crawl = db.get(Crawl, crawl_id)
        if crawl is None:
            return

        website = db.get(Website, crawl.website_id)

        project = db.get(Project, website.project_id) if website else None
        if project is not None:
            try:
                set_project_status(project, ProjectStatus.CRAWLING)
            except ValueError:
                project.status = ProjectStatus.CRAWLING

        crawl.status = CrawlStatus.RUNNING
        crawl.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            _set_progress(crawl.id, "fetching")
            result = crawl_website(
                website.url,
                max_pages=settings.crawl_max_pages,
            )

            root = ensure_crawl_directories(website.domain, crawl.id)

            _set_progress(
                crawl.id,
                "seo",
                pages_crawled=result["pages_crawled"],
                pages_discovered=result["pages_discovered"],
            )
            ssl_evidence = collect_ssl(website.domain)
            (root / "ssl" / "certificate.json").write_text(
                json.dumps(ssl_evidence, indent=2),
                encoding="utf-8",
            )

            seo = collect_seo(website.url)
            raw_robots = seo.pop("raw_robots")
            raw_sitemap = seo.pop("raw_sitemap")
            if raw_robots is not None:
                (root / "seo" / "robots.txt").write_text(
                    raw_robots, encoding="utf-8"
                )
            if raw_sitemap is not None:
                (root / "seo" / "sitemap.xml").write_text(
                    raw_sitemap, encoding="utf-8"
                )
            (root / "seo" / "analysis.json").write_text(
                json.dumps(seo, indent=2), encoding="utf-8"
            )

            content_seo = collect_content_seo(
                result["pages"],
                sample=settings.crawl_max_content_pages,
            )
            (root / "seo" / "content.json").write_text(
                json.dumps(content_seo, indent=2), encoding="utf-8"
            )

            site_story = collect_site_story(result["pages"], max_pages=12)
            (root / "seo" / "site_story.json").write_text(
                json.dumps(site_story, indent=2), encoding="utf-8"
            )

            tech = collect_technologies(website.url, result["pages"])
            (root / "technologies" / "technologies.json").write_text(
                json.dumps(tech, indent=2), encoding="utf-8"
            )

            _set_progress(crawl.id, "siteone")
            collect_siteone(
                website.url,
                root,
                max_urls=settings.crawl_siteone_max_urls,
            )

            summary = []
            page_rows = []
            for page in result["pages"]:
                filename = f"{slugify_url(page['url'])}.html"
                (root / "html" / filename).write_text(
                    page["html"], encoding="utf-8"
                )
                html_file = f"html/{filename}"

                row = Page(
                    crawl_id=crawl.id,
                    url=page["url"],
                    status_code=page["status_code"],
                    title=page["title"],
                    html_file=html_file,
                )
                db.add(row)
                page_rows.append(row)

                summary.append(
                    {
                        "url": page["url"],
                        "status_code": page["status_code"],
                        "title": page["title"],
                        "html_file": html_file,
                    }
                )

            (root / "evidence" / "pages.json").write_text(
                json.dumps(
                    {"pages": summary, "errors": result["errors"]},
                    indent=2,
                ),
                encoding="utf-8",
            )

            # Browser evidence (screenshots + rendered DOM), capped.
            # Prefer key pages (home/about/contact/services) over long-tail URLs.
            browser_results = []
            browser_limit = settings.crawl_max_browser_pages or MAX_BROWSER_PAGES
            target_pages = select_browser_targets(
                result["pages"], browser_limit
            )
            url_to_row = {row.url: row for row in page_rows}
            browser_targets = [
                (page, url_to_row[page["url"]])
                for page in target_pages
                if page.get("url") in url_to_row
            ]
            for idx, (page, row) in enumerate(browser_targets):
                _set_progress(
                    crawl.id, "browser", sub_done=idx, sub_total=len(browser_targets)
                )
                ev = collect_browser_evidence(
                    page["url"], root, slugify_url(page["url"])
                )
                browser_results.append(ev)
                row.desktop_screenshot = ev["screenshots"].get("desktop")
                row.mobile_screenshot = ev["screenshots"].get("mobile")
                row.rendered_html_file = ev["rendered_html_file"]

            performance_results = []
            for ev in browser_results:
                performance_results.append(
                    {
                        "url": ev.get("url"),
                        "final_url": ev.get("final_url"),
                        "performance": ev.get("performance"),
                        "error": ev.get("error"),
                    }
                )

            accessibility_results = []
            for idx, (page, row) in enumerate(browser_targets):
                _set_progress(
                    crawl.id, "accessibility", sub_done=idx, sub_total=len(browser_targets)
                )
                a11y = collect_accessibility(page["url"])
                accessibility_results.append(a11y)

            (root / "evidence" / "accessibility.json").write_text(
                json.dumps(accessibility_results, indent=2),
                encoding="utf-8",
            )

            (root / "evidence" / "browser.json").write_text(
                json.dumps(browser_results, indent=2),
                encoding="utf-8",
            )

            (root / "evidence" / "performance.json").write_text(
                json.dumps(performance_results, indent=2),
                encoding="utf-8",
            )

            # Re-analyze content/story using rendered HTML (Next.js shells
            # look empty in static HTML — that was poisoning chat/brain).
            enriched_pages = enrich_pages_with_rendered_html(
                result["pages"], root, browser_results
            )
            content_seo = collect_content_seo(
                enriched_pages,
                sample=settings.crawl_max_content_pages,
            )
            (root / "seo" / "content.json").write_text(
                json.dumps(content_seo, indent=2), encoding="utf-8"
            )
            site_story = collect_site_story(enriched_pages, max_pages=12)
            (root / "seo" / "site_story.json").write_text(
                json.dumps(site_story, indent=2), encoding="utf-8"
            )

            if project is not None:
                try:
                    set_project_status(project, ProjectStatus.EVIDENCE_COLLECTED)
                except ValueError:
                    project.status = ProjectStatus.EVIDENCE_COLLECTED
                try:
                    set_project_status(project, ProjectStatus.ANALYZING)
                except ValueError:
                    project.status = ProjectStatus.ANALYZING
                db.commit()

            _set_progress(crawl.id, "analyzing", sub_done=None, sub_total=None)
            findings = analyze_crawl(root)
            (root / "evidence" / "findings.json").write_text(
                json.dumps(findings, indent=2), encoding="utf-8"
            )
            for f in findings:
                db.add(Finding(crawl_id=crawl.id, **f))

            annotate_screenshots(root)

            _set_progress(crawl.id, "lighthouse")
            lighthouse_urls = [
                p.get("url")
                for p in select_browser_targets(
                    result["pages"], settings.crawl_max_lighthouse_pages
                )
                if p.get("url")
            ]
            lighthouse = collect_lighthouse(root, lighthouse_urls, prefer_cli=True)
            (root / "lighthouse" / "summary.json").write_text(
                json.dumps(lighthouse, indent=2), encoding="utf-8"
            )

            _set_progress(crawl.id, "packaging")
            crawl.pages_discovered = result["pages_discovered"]
            crawl.pages_crawled = result["pages_crawled"]
            crawl.status = CrawlStatus.COMPLETED
            crawl.completed_at = datetime.now(timezone.utc)
            if project is not None:
                try:
                    set_project_status(project, ProjectStatus.AWAITING_APPROVAL)
                except ValueError:
                    project.status = ProjectStatus.AWAITING_APPROVAL
            db.commit()

            website_meta = {
                "id": str(website.id),
                "url": website.url,
                "domain": website.domain,
            }
            crawl_meta = {
                "id": str(crawl.id),
                "status": crawl.status.value,
                "pages_discovered": crawl.pages_discovered,
                "pages_crawled": crawl.pages_crawled,
                "started_at": crawl.started_at.isoformat()
                if crawl.started_at
                else None,
                "completed_at": crawl.completed_at.isoformat()
                if crawl.completed_at
                else None,
            }
            # Proof pack first so the evidence pack can index its paths.
            build_proof_pack(
                root,
                domain=website.domain,
                crawl_id=str(crawl.id),
                website_url=website.url,
            )
            build_and_write_evidence_pack(
                root,
                website=website_meta,
                crawl=crawl_meta,
            )
            # Commercial opportunities from clustered evidence (not raw findings).
            try:
                from backend.app.services.opportunities import generate_opportunities

                generate_opportunities(
                    db,
                    root=root,
                    project_id=website.project_id,
                    website_id=website.id,
                    crawl_id=crawl.id,
                    replace=False,
                )
            except Exception:
                # Crawl success must not fail if opportunity generation errors.
                db.rollback()
                db.add(crawl)
                if project is not None:
                    db.add(project)
                db.commit()

        except Exception as exc:
            db.rollback()
            crawl.status = CrawlStatus.FAILED
            crawl.error_message = str(exc)
            crawl.completed_at = datetime.now(timezone.utc)
            db.commit()

    finally:
        CRAWL_PROGRESS.pop(str(crawl_id), None)
        db.close()


@router.post(
    "",
    response_model=CrawlRead,
    status_code=201,
)
def create_crawl(
    website_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    website = db.get(Website, website_id)

    if website is None:
        raise HTTPException(
            status_code=404,
            detail="Website not found",
        )

    crawl = Crawl(
        website_id=website_id,
        status=CrawlStatus.QUEUED,
    )

    db.add(crawl)
    db.commit()
    db.refresh(crawl)

    background_tasks.add_task(run_crawl, crawl.id)

    return crawl



def _require_crawl(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session,
) -> tuple[Crawl, Website]:
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(status_code=404, detail="Crawl not found")

    website = db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    return crawl, website


def _website_meta(website: Website) -> dict:
    return {
        "id": str(website.id),
        "url": website.url,
        "domain": website.domain,
        "role": getattr(website, "role", None) or "primary",
    }


def _crawl_meta(crawl: Crawl) -> dict:
    return {
        "id": str(crawl.id),
        "status": crawl.status.value
        if hasattr(crawl.status, "value")
        else str(crawl.status),
        "pages_discovered": crawl.pages_discovered,
        "pages_crawled": crawl.pages_crawled,
        "started_at": crawl.started_at.isoformat()
        if crawl.started_at
        else None,
        "completed_at": crawl.completed_at.isoformat()
        if crawl.completed_at
        else None,
    }


def _load_or_build_pack(website: Website, crawl: Crawl) -> dict:
    root = get_crawl_root(website.domain, crawl.id)
    pack_path = root / PACK_FILENAME
    website_meta = _website_meta(website)
    crawl_meta = _crawl_meta(crawl)

    if not pack_path.exists():
        if not (root / "evidence" / "findings.json").exists():
            raise HTTPException(
                status_code=404,
                detail="Crawl evidence not found on disk",
            )
        return build_and_write_evidence_pack(
            root,
            website=website_meta,
            crawl=crawl_meta,
        )

    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pack = build_and_write_evidence_pack(
            root,
            website=website_meta,
            crawl=crawl_meta,
        )

    pack["website"] = website_meta
    pack["crawl"] = crawl_meta
    return pack


def _agent_inputs(db: Session, website: Website, crawl: Crawl, root) -> dict:
    """Load opportunities + sell + agency for the generative agent."""
    from backend.app.services.agency_settings import load_agency_settings
    from backend.app.services.agent_context import load_sell_recommendation
    from backend.app.services.opportunities import (
        generate_opportunities,
        list_opportunities,
    )

    opps = list_opportunities(db, crawl.id)
    if not opps and crawl.status == CrawlStatus.COMPLETED:
        try:
            opps = generate_opportunities(
                db,
                root=root,
                project_id=website.project_id,
                website_id=website.id,
                crawl_id=crawl.id,
                replace=False,
            )
        except Exception:
            opps = []
    return {
        "opportunities": opps,
        "sell_recommendation": load_sell_recommendation(root),
        "agency": load_agency_settings(),
    }


@router.get(
    "",
    response_model=list[CrawlRead],
)
def list_crawls(
    website_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    website = db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    rows = db.execute(
        select(Crawl)
        .where(Crawl.website_id == website_id)
        .order_by(Crawl.created_at.desc())
    ).scalars().all()
    return rows


@router.get(
    "/history",
)
def crawl_history(
    website_id: uuid.UUID,
    limit: int = 12,
    db: Session = Depends(get_db),
):
    """Findings totals per completed crawl, oldest first, in one query."""
    website = db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    limit = max(1, min(limit, 50))
    crawls = db.execute(
        select(Crawl)
        .where(
            Crawl.website_id == website_id,
            Crawl.status == CrawlStatus.COMPLETED,
        )
        .order_by(Crawl.created_at.desc())
        .limit(limit)
    ).scalars().all()

    ids = [crawl.id for crawl in crawls]
    counts: dict = {crawl_id: {"high": 0, "medium": 0, "low": 0, "info": 0} for crawl_id in ids}
    if ids:
        rows = db.execute(
            select(Finding.crawl_id, Finding.severity, func.count())
            .where(Finding.crawl_id.in_(ids))
            .group_by(Finding.crawl_id, Finding.severity)
        ).all()
        for crawl_id, severity, count in rows:
            counts[crawl_id][severity] = count

    return [
        {
            "id": crawl.id,
            "date": crawl.completed_at or crawl.created_at,
            "pages_crawled": crawl.pages_crawled,
            "total": sum(counts[crawl.id].values()),
            "high": counts[crawl.id]["high"],
            "by_severity": counts[crawl.id],
        }
        for crawl in reversed(crawls)
    ]


@router.get(
    "/compare",
)
def compare_crawls(
    website_id: uuid.UUID,
    crawl_a: uuid.UUID,
    crawl_b: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl_a_row = db.get(Crawl, crawl_a)
    crawl_b_row = db.get(Crawl, crawl_b)

    if (
        crawl_a_row is None
        or crawl_a_row.website_id != website_id
    ):
        raise HTTPException(
            status_code=404,
            detail="First crawl not found",
        )

    if (
        crawl_b_row is None
        or crawl_b_row.website_id != website_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Second crawl not found",
        )

    findings_a = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_a)
    ).scalars().all()

    findings_b = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_b)
    ).scalars().all()

    def finding_key(finding):
        return (
            finding.code,
            finding.url,
        )

    map_a = {
        finding_key(finding): finding
        for finding in findings_a
    }

    map_b = {
        finding_key(finding): finding
        for finding in findings_b
    }

    keys_a = set(map_a)
    keys_b = set(map_b)

    resolved = sorted(
        keys_a - keys_b,
        key=lambda key: (key[0], key[1] or ""),
    )

    new = sorted(
        keys_b - keys_a,
        key=lambda key: (key[0], key[1] or ""),
    )

    unchanged = sorted(
        keys_a & keys_b,
        key=lambda key: (key[0], key[1] or ""),
    )

    def serialize(finding):
        return {
            "code": finding.code,
            "severity": finding.severity,
            "category": finding.category,
            "title": finding.title,
            "description": finding.description,
            "url": finding.url,
            "detail": finding.detail,
        }

    return {
        "website_id": website_id,
        "crawl_a": {
            "id": crawl_a_row.id,
            "status": crawl_a_row.status,
            "created_at": crawl_a_row.created_at,
            "completed_at": crawl_a_row.completed_at,
        },
        "crawl_b": {
            "id": crawl_b_row.id,
            "status": crawl_b_row.status,
            "created_at": crawl_b_row.created_at,
            "completed_at": crawl_b_row.completed_at,
        },
        "summary": {
            "crawl_a_findings": len(findings_a),
            "crawl_b_findings": len(findings_b),
            "new": len(new),
            "resolved": len(resolved),
            "unchanged": len(unchanged),
        },
        "new": [
            serialize(map_b[key])
            for key in new
        ],
        "resolved": [
            serialize(map_a[key])
            for key in resolved
        ],
        "unchanged": [
            serialize(map_b[key])
            for key in unchanged
        ],
    }


@router.get(
    "/{crawl_id}",
    response_model=CrawlRead,
)
def get_crawl(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl = db.get(Crawl, crawl_id)

    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(
            status_code=404,
            detail="Crawl not found",
        )

    return crawl


@router.get("/{crawl_id}/progress")
def get_crawl_progress(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(status_code=404, detail="Crawl not found")

    live = CRAWL_PROGRESS.get(str(crawl_id))
    return {
        "crawl_id": crawl.id,
        "status": crawl.status,
        "started_at": crawl.started_at,
        "stages": [label for _, label in CRAWL_STAGES],
        **(live or {"stage": None, "label": None, "step": 0, "total_steps": len(CRAWL_STAGES)}),
    }


@router.get(
    "/{crawl_id}/pages",
    response_model=list[PageRead],
)
def list_crawl_pages(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl = db.get(Crawl, crawl_id)

    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(
            status_code=404,
            detail="Crawl not found",
        )

    result = db.execute(
        select(Page)
        .where(Page.crawl_id == crawl_id)
        .order_by(Page.created_at)
    )

    return result.scalars().all()


@router.get(
    "/{crawl_id}/findings/summary",
)
def summarize_crawl_findings(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl = db.get(Crawl, crawl_id)

    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(
            status_code=404,
            detail="Crawl not found",
        )

    rows = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_id)
    ).scalars().all()

    by_severity = {
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    by_category = {}

    for finding in rows:
        severity = finding.severity
        category = finding.category

        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "crawl_id": crawl.id,
        "website_id": crawl.website_id,
        "total": len(rows),
        "by_severity": by_severity,
        "by_category": by_category,
    }




SEVERITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
    "info": 3,
}


@router.get(
    "/{crawl_id}/findings",
    response_model=list[FindingRead],
)
def list_crawl_findings(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl = db.get(Crawl, crawl_id)

    if crawl is None or crawl.website_id != website_id:
        raise HTTPException(
            status_code=404,
            detail="Crawl not found",
        )

    rows = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_id)
    ).scalars().all()

    return sorted(
        rows, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.code)
    )


@router.get("/{crawl_id}/evidence-pack")
def get_evidence_pack(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    rebuild: bool = False,
    db: Session = Depends(get_db),
):
    """Return the brain-ready evidence pack for a crawl.

    Set rebuild=true to regenerate from saved evidence files.
    """
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)

    if rebuild:
        if not (root / "evidence" / "findings.json").exists():
            raise HTTPException(
                status_code=404,
                detail="Crawl evidence not found on disk",
            )
        return build_and_write_evidence_pack(
            root,
            website=_website_meta(website),
            crawl=_crawl_meta(crawl),
        )

    return _load_or_build_pack(website, crawl)


@router.get("/{crawl_id}/recommendations")
def get_recommendations(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    payload = load_recommendations(root)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendations not generated yet",
        )
    return payload


@router.post("/{crawl_id}/recommendations", status_code=201)
def create_recommendations(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    fallback: bool = True,
    db: Session = Depends(get_db),
):
    """Ask the local Ollama brain for recommendations from the evidence pack.

    If Ollama is unavailable and fallback=true (default), returns rule-based
    recommendations so the product still works offline.
    """
    crawl, website = _require_crawl(website_id, crawl_id, db)

    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before generating recommendations",
        )

    pack = _load_or_build_pack(website, crawl)
    root = get_crawl_root(website.domain, crawl.id)
    agent = _agent_inputs(db, website, crawl, root)

    try:
        payload = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=True,
            allow_fallback=fallback,
            opportunities=agent["opportunities"],
            sell_recommendation=agent["sell_recommendation"],
            agency=agent["agency"],
            root=root,
        )
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    write_recommendations(root, payload)
    build_checklist(root, recommendations=payload)
    # Brain → brief + live demo only. Mockup image boards stay on Design
    # (they were a major source of Ask Brain feeling stuck).
    brief = sync_brief_from_brain(
        root,
        recommendations=payload,
        evidence_pack=pack,
    )
    demo = generate_demo_site(
        root,
        domain=website.domain,
        recommendations=payload,
        evidence_pack=pack,
        design_brief=brief,
    )
    return {**payload, "demo": demo, "mockups": None}


@router.get("/{crawl_id}/design/chat")
def get_design_chat(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)
    # Keep chat-driven palette/copy edits; don't clobber with a fresh brain brief.
    brief = sync_brief_from_brain(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
        preserve_chat_overrides=True,
    )
    chat = load_chat(root)
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "messages": chat.get("messages") or [],
        "design_brief": brief,
        "updated_at": chat.get("updated_at") or brief.get("updated_at"),
    }


class DesignChatMessage(BaseModel):
    message: str = ""
    regenerate: bool | None = None  # force regenerate when true
    image_path: str | None = None  # crawl-relative screenshot for vision review


class SocialChatMessage(BaseModel):
    message: str = ""


@router.get("/{crawl_id}/social/chat")
def get_social_chat(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)
    social = ensure_social_pack(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
    )
    chat = load_social_chat(root)
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "messages": chat.get("messages") or [],
        "social_content": social,
        "updated_at": chat.get("updated_at") or social.get("generated_at"),
    }


@router.post("/{crawl_id}/social/chat")
def post_social_chat(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: SocialChatMessage,
    db: Session = Depends(get_db),
):
    """Interactive social strategist: refine posts, hashtags, soundtrack ideas."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before social chat",
        )

    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)
    if recommendations is None:
        recommendations = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=False,
            allow_fallback=True,
            root=root,
        )
        write_recommendations(root, recommendations)

    try:
        result = process_social_chat_message(
            root,
            payload.message,
            recommendations=recommendations,
            evidence_pack=pack,
            prefer_ollama=True,
            model=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        **result,
        "domain": website.domain,
        "crawl_id": str(crawl.id),
    }


@router.get("/{crawl_id}/social")
def get_social_content(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)
    social = ensure_social_pack(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
    )
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "social_content": social or load_social_content(root),
    }


@router.post("/{crawl_id}/design/chat")
def post_design_chat(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: DesignChatMessage,
    db: Session = Depends(get_db),
):
    """Interactive design turn: update brief and optionally regenerate mockups."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before design chat",
        )

    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    agent = _agent_inputs(db, website, crawl, root)
    recommendations = load_recommendations(root)
    # Never block Site chat on a full Brain/Ollama run. Bootstrap instantly
    # from crawl evidence; Ask Brain can regenerate with the local model later.
    if recommendations is None:
        recommendations = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=False,
            allow_fallback=True,
            opportunities=agent["opportunities"],
            sell_recommendation=agent["sell_recommendation"],
            agency=agent["agency"],
            root=root,
        )
        write_recommendations(root, recommendations)

    try:
        result = process_chat_message(
            root,
            payload.message,
            recommendations=recommendations,
            evidence_pack=pack,
            opportunities=agent["opportunities"],
            sell_recommendation=agent["sell_recommendation"],
            agency=agent["agency"],
            # Let design_chat pick a small local model for design edits.
            model=None,
            base_url=settings.ollama_base_url,
            prefer_ollama=True,
            image_path=payload.image_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Base44-style loop: design edits refresh the live HTML demo immediately.
    # Mockup image boards stay on the explicit Generate Mockups action (or
    # regenerate=true) so chat stays fast.
    from backend.app.services.design_chat import brief_patch_nonempty

    # Generative builder already wrote demo/index.html — don't clobber it.
    if result.get("source") == "demo_builder" and result.get("demo"):
        return {
            **result,
            "mockups": None,
            "demo": result.get("demo"),
            "regenerated": True,
            "preview_updated": True,
            "domain": website.domain,
            "crawl_id": str(crawl.id),
        }

    should_regen_demo = bool(result.get("preview_updated")) or brief_patch_nonempty(
        result.get("design_brief_patch")
    )
    if payload.regenerate is True:
        should_regen_demo = True
    # Bootstrap a live preview on first chat turn if none exists yet.
    if not should_regen_demo and load_demo(root) is None:
        should_regen_demo = True
    should_regen_mockups = payload.regenerate is True

    mockups = None
    demo = None
    if should_regen_demo:
        demo = generate_demo_site(
            root,
            domain=website.domain,
            recommendations=recommendations,
            evidence_pack=pack,
            design_brief=result.get("design_brief"),
        )
    else:
        demo = load_demo(root)
    if should_regen_mockups:
        mockups = generate_mockups(
            root,
            recommendations=recommendations,
            evidence_pack=pack,
            design_brief=result.get("design_brief"),
            backend="concept",
        )

    return {
        **result,
        "mockups": mockups,
        "demo": demo,
        "regenerated": should_regen_demo and bool(demo),
        "preview_updated": should_regen_demo and bool(demo),
        "domain": website.domain,
        "crawl_id": str(crawl.id),
    }


@router.get("/{crawl_id}/design/brief")
def get_design_brief(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    brief = sync_brief_from_brain(
        root,
        recommendations=load_recommendations(root),
        evidence_pack=pack,
        preserve_chat_overrides=True,
    )
    return {"domain": website.domain, "crawl_id": str(crawl.id), "design_brief": brief}


@router.get("/{crawl_id}/mockups")
def get_mockups(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    payload = load_mockups(root)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Mockups not generated yet",
        )
    return payload


@router.post("/{crawl_id}/mockups", status_code=201)
def create_mockups(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Generate local redesign concept images from recommendations.

    Uses recommendations if present; otherwise builds a rule-based pack
    summary from the evidence pack so mockups can still be created.
    """
    crawl, website = _require_crawl(website_id, crawl_id, db)

    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before generating mockups",
        )

    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)

    if recommendations is None:
        # Ensure we always have recommendation context for visuals.
        recommendations = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=False,
            allow_fallback=True,
        )
        write_recommendations(root, recommendations)

    brief = sync_brief_from_brain(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
    )
    # Always use concept boards here — TinySD on CPU is slow and looks fake.
    mockup_backend = settings.mockup_backend
    if mockup_backend in {"auto", "ai"}:
        mockup_backend = "concept"
    mockups = generate_mockups(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
        design_brief=brief,
        backend=mockup_backend,
        image_model_id=settings.image_model_id,
        image_steps=settings.image_steps,
        image_size=settings.image_size,
    )
    demo = generate_demo_site(
        root,
        domain=website.domain,
        recommendations=recommendations,
        evidence_pack=pack,
        design_brief=brief,
    )
    return {**mockups, "demo": demo}


@router.get("/{crawl_id}/demo")
def get_demo(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    payload = load_demo(root)
    if payload is None:
        raise HTTPException(status_code=404, detail="Demo site not generated yet")
    return payload


class DemoBuildRequest(BaseModel):
    prompt: str = "Build a modern marketing website from this crawl"
    max_fix_iters: int = 1


@router.post("/{crawl_id}/demo", status_code=201)
def create_demo(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Build / refresh the clickable HTML demo from brain + design brief."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before generating a demo",
        )

    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)
    if recommendations is None:
        recommendations = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=True,
            allow_fallback=True,
        )
        write_recommendations(root, recommendations)

    brief = sync_brief_from_brain(
        root,
        recommendations=recommendations,
        evidence_pack=pack,
    )
    return generate_demo_site(
        root,
        domain=website.domain,
        recommendations=recommendations,
        evidence_pack=pack,
        design_brief=brief,
    )


@router.post("/{crawl_id}/demo/build", status_code=201)
def build_generative_demo(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: DemoBuildRequest,
    db: Session = Depends(get_db),
):
    """Generative loop: prompt → spec → components → HTML → Playwright → QA fix."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before building a demo",
        )
    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    prompt = (payload.prompt or "").strip() or (
        f"Build a modern website for {website.domain} based on the crawl story"
    )
    try:
        result = build_demo_from_prompt(
            root,
            prompt,
            domain=website.domain,
            context={
                "site_story": (pack or {}).get("site_story") or {},
                "scores": (pack or {}).get("scores") or {},
            },
            max_fix_iters=max(0, min(int(payload.max_fix_iters or 1), 3)),
            model=settings.ollama_model,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        **result,
        "domain": website.domain,
        "crawl_id": str(crawl.id),
    }


@router.get("/{crawl_id}/proposal")
def get_proposal(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    payload = load_proposal(root)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Proposal not generated yet",
        )
    return payload


@router.post("/{crawl_id}/proposal", status_code=201)
def create_proposal(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    fallback: bool = True,
    db: Session = Depends(get_db),
):
    """Generate a business proposal markdown from audit + recommendations."""
    crawl, website = _require_crawl(website_id, crawl_id, db)

    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before generating a proposal",
        )

    root = get_crawl_root(website.domain, crawl.id)
    pack = _load_or_build_pack(website, crawl)
    recommendations = load_recommendations(root)

    if recommendations is None:
        recommendations = generate_recommendations(
            pack,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            prefer_ollama=False,
            allow_fallback=True,
        )
        write_recommendations(root, recommendations)

    mockups = load_mockups(root)

    from backend.app.services.agency_settings import proposal_config_from_agency
    from backend.app.services.opportunities import (
        build_sell_recommendation,
        generate_opportunities,
        list_opportunities,
        selected_for_proposal,
    )

    opps = list_opportunities(db, crawl.id)
    if not opps:
        opps = generate_opportunities(
            db,
            root=root,
            project_id=website.project_id,
            website_id=website.id,
            crawl_id=crawl.id,
            replace=False,
        )
    # Prefer approved/selected; otherwise use all non-rejected for draft scope.
    config = proposal_config_from_agency()
    sell = build_sell_recommendation(opps, config=config)
    # Persist accepted package from sell file if present
    sell_path = root / "proposal" / "sell_recommendation.json"
    if sell_path.exists():
        try:
            saved = json.loads(sell_path.read_text(encoding="utf-8"))
            if saved.get("accepted") and saved.get("recommended_package"):
                sell = build_sell_recommendation(
                    opps, config=config, accepted_package=saved["recommended_package"]
                )
        except (json.JSONDecodeError, OSError):
            pass

    return generate_proposal(
        root,
        website=_website_meta(website),
        crawl=_crawl_meta(crawl),
        evidence_pack=pack,
        recommendations=recommendations,
        mockups=mockups,
        config=config,
        opportunities=opps if selected_for_proposal(opps) else opps,
        sell_recommendation=sell,
        prefer_ollama=True,
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
    )


@router.get("/{crawl_id}/reports")
def get_reports(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List downloadable proof reports (SiteOne, ZIP, screenshots)."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    manifest = load_reports_manifest(root)
    if manifest is None:
        if crawl.status != CrawlStatus.COMPLETED:
            raise HTTPException(
                status_code=404,
                detail="Reports not available until the crawl completes",
            )
        manifest = build_proof_pack(
            root,
            domain=website.domain,
            crawl_id=str(crawl.id),
            website_url=website.url,
        )
    siteone = load_siteone_summary(root)
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "manifest": manifest,
        "siteone": siteone,
        "urls": {
            "proof_zip": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/proof-pack.zip",
            "proof_index": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/index.html",
            "siteone_html": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/siteone/report.html",
            "siteone_json": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/siteone/report.json",
        },
    }


@router.post("/{crawl_id}/reports/proof", status_code=201)
def rebuild_proof_pack(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Rebuild the downloadable proof ZIP (screenshots + SiteOne + evidence)."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl must be completed before building proof reports",
        )
    root = get_crawl_root(website.domain, crawl.id)
    if not (root / "evidence" / "findings.json").exists():
        raise HTTPException(status_code=404, detail="Crawl evidence not found on disk")

    manifest = build_proof_pack(
        root,
        domain=website.domain,
        crawl_id=str(crawl.id),
        website_url=website.url,
    )
    # Keep the evidence pack in sync with new report paths.
    build_and_write_evidence_pack(
        root,
        website=_website_meta(website),
        crawl=_crawl_meta(crawl),
    )
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "manifest": manifest,
        "url": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/proof-pack.zip",
        "index_url": f"/data/websites/{website.domain}/crawls/{crawl.id}/reports/index.html",
    }


@router.post("/{crawl_id}/proposal/pdf")
def create_proposal_pdf(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)

    if not (root / "proposal" / "proposal.md").exists():
        pack = _load_or_build_pack(website, crawl)
        recommendations = load_recommendations(root)
        if recommendations is None:
            recommendations = generate_recommendations(
                pack,
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                prefer_ollama=False,
                allow_fallback=True,
            )
            write_recommendations(root, recommendations)
        generate_proposal(
            root,
            website=_website_meta(website),
            crawl=_crawl_meta(crawl),
            evidence_pack=pack,
            recommendations=recommendations,
            mockups=load_mockups(root),
            prefer_ollama=False,
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    export_proposal_pdf(root)
    # Keep manifest aware of PDF for GET /proposal.
    manifest_path = root / "proposal" / "proposal.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pdf_file"] = "proposal/proposal.pdf"
            manifest_path.write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
        except json.JSONDecodeError:
            pass
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "pdf_file": "proposal/proposal.pdf",
        "url": f"/data/websites/{website.domain}/crawls/{crawl.id}/proposal/proposal.pdf",
    }


class ProposalUpdate(BaseModel):
    narratives: dict | None = None
    recommended_package: str | None = None
    packages: dict | None = None
    out_of_scope: list[str] | None = None
    markdown: str | None = None


@router.patch("/{crawl_id}/proposal")
def patch_proposal(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: ProposalUpdate,
    db: Session = Depends(get_db),
):
    """Edit proposal narratives / packages / markdown before PDF export."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    before = load_proposal(root)
    try:
        updated = update_proposal(
            root,
            narratives=payload.narratives,
            recommended_package=payload.recommended_package,
            packages=payload.packages,
            out_of_scope=payload.out_of_scope,
            markdown=payload.markdown,
        )
    except ProposalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Human edits train the agent voice (few-shot feedback store).
    if payload.narratives and before:
        try:
            from backend.app.services.feedback_store import record_feedback

            record_feedback(
                kind="proposal_narrative",
                before=before.get("narratives") or {},
                after=updated.get("narratives") or payload.narratives,
                domain=website.domain,
                crawl_id=str(crawl.id),
            )
        except Exception:
            pass
    return updated


@router.get("/{crawl_id}/findings/clusters")
def get_finding_clusters(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    findings_path = root / "evidence" / "findings.json"
    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        findings = [
            {
                "code": f.code,
                "severity": f.severity,
                "category": f.category,
                "title": f.title,
                "description": f.description,
                "url": f.url,
                "detail": f.detail,
            }
            for f in db.execute(
                select(Finding).where(Finding.crawl_id == crawl.id)
            ).scalars().all()
        ]
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "clusters": cluster_summary(findings, max_items=12),
        "total": len(findings),
    }


class OpportunityPatchBody(BaseModel):
    status: str | None = None
    proposal_status: str | None = None
    selected_package: str | None = None
    title: str | None = None
    client_title: str | None = None
    problem: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    priority: str | None = None
    estimated_effort: str | None = None
    estimated_value: float | None = None


class SellAcceptBody(BaseModel):
    package: str | None = None
    customize: bool = False


@router.get("/{crawl_id}/opportunities")
def get_opportunities(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    from backend.app.services.opportunities import generate_opportunities, list_opportunities

    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    items = list_opportunities(db, crawl.id)
    if not items and crawl.status == CrawlStatus.COMPLETED:
        items = generate_opportunities(
            db,
            root=root,
            project_id=website.project_id,
            website_id=website.id,
            crawl_id=crawl.id,
            replace=False,
        )
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "project_id": str(website.project_id),
        "opportunities": items,
        "total": len(items),
    }


@router.post("/{crawl_id}/opportunities/generate", status_code=201)
def regenerate_opportunities(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    replace: bool = True,
    db: Session = Depends(get_db),
):
    from backend.app.services.opportunities import generate_opportunities

    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Crawl must be completed")
    root = get_crawl_root(website.domain, crawl.id)
    items = generate_opportunities(
        db,
        root=root,
        project_id=website.project_id,
        website_id=website.id,
        crawl_id=crawl.id,
        replace=replace,
    )
    return {
        "domain": website.domain,
        "crawl_id": str(crawl.id),
        "opportunities": items,
        "total": len(items),
    }


@router.patch("/{crawl_id}/opportunities/{opportunity_id}")
def patch_opportunity_route(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    payload: OpportunityPatchBody,
    db: Session = Depends(get_db),
):
    from backend.app.services.feedback_store import record_feedback
    from backend.app.services.opportunities import list_opportunities, patch_opportunity

    crawl, website = _require_crawl(website_id, crawl_id, db)
    before = next(
        (o for o in list_opportunities(db, crawl.id) if str(o.get("id")) == str(opportunity_id)),
        None,
    )
    data = patch_opportunity(
        db,
        opportunity_id,
        crawl_id=crawl_id,
        patch=payload.model_dump(exclude_none=True),
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    patch_keys = payload.model_dump(exclude_none=True)
    if before and any(
        k in patch_keys
        for k in ("client_title", "problem", "business_impact", "recommendation")
    ):
        try:
            record_feedback(
                kind="opportunity_rewrite",
                before={
                    "client_title": before.get("client_title"),
                    "problem": before.get("problem"),
                    "business_impact": before.get("business_impact"),
                    "recommendation": before.get("recommendation"),
                },
                after={
                    "client_title": data.get("client_title"),
                    "problem": data.get("problem"),
                    "business_impact": data.get("business_impact"),
                    "recommendation": data.get("recommendation"),
                },
                domain=website.domain,
                crawl_id=str(crawl.id),
            )
        except Exception:
            pass
    return data


@router.get("/{crawl_id}/sell-recommendation")
def get_sell_recommendation(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    from backend.app.services.agency_settings import proposal_config_from_agency
    from backend.app.services.opportunities import (
        build_sell_recommendation,
        generate_opportunities,
        list_opportunities,
    )

    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    opps = list_opportunities(db, crawl.id)
    if not opps and crawl.status == CrawlStatus.COMPLETED:
        opps = generate_opportunities(
            db,
            root=root,
            project_id=website.project_id,
            website_id=website.id,
            crawl_id=crawl.id,
            replace=False,
        )
    config = proposal_config_from_agency()
    sell = build_sell_recommendation(opps, config=config)
    sell_path = root / "proposal" / "sell_recommendation.json"
    if sell_path.exists():
        try:
            saved = json.loads(sell_path.read_text(encoding="utf-8"))
            sell["accepted"] = bool(saved.get("accepted"))
            if saved.get("recommended_package"):
                sell["accepted_package"] = saved.get("recommended_package")
                if saved.get("accepted"):
                    sell = build_sell_recommendation(
                        opps,
                        config=config,
                        accepted_package=saved["recommended_package"],
                    )
        except (json.JSONDecodeError, OSError):
            pass
    return sell


@router.post("/{crawl_id}/sell-recommendation/accept")
def accept_sell_recommendation(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: SellAcceptBody,
    db: Session = Depends(get_db),
):
    from backend.app.models.opportunity import (
        Opportunity,
        OpportunityStatus,
        ProposalItemStatus,
    )
    from backend.app.services.agency_settings import proposal_config_from_agency
    from backend.app.services.opportunities import (
        build_sell_recommendation,
        list_opportunities,
        opportunity_to_dict,
    )

    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    config = proposal_config_from_agency()
    opps = list_opportunities(db, crawl.id)
    sell = build_sell_recommendation(
        opps, config=config, accepted_package=payload.package
    )
    package = sell["recommended_package"]

    rows = list(
        db.execute(select(Opportunity).where(Opportunity.crawl_id == crawl.id))
        .scalars()
        .all()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
        if status_val in {"rejected", "deferred"}:
            continue
        row.status = OpportunityStatus.APPROVED
        row.proposal_status = ProposalItemStatus.SELECTED
        row.selected_package = package
        row.updated_at = now
    db.commit()

    out_dir = root / "proposal"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = {
        **sell,
        "accepted": True,
        "accepted_at": now.isoformat(),
        "customize": payload.customize,
        "opportunities": [opportunity_to_dict(r) for r in rows],
    }
    # JSON-safe
    for o in saved["opportunities"]:
        for key in ("id", "project_id", "website_id", "crawl_id"):
            if o.get(key) is not None:
                o[key] = str(o[key])
        for key in ("created_at", "updated_at"):
            if o.get(key) is not None and hasattr(o[key], "isoformat"):
                o[key] = o[key].isoformat()
    (out_dir / "sell_recommendation.json").write_text(
        json.dumps({k: v for k, v in saved.items() if k != "opportunities"}, indent=2),
        encoding="utf-8",
    )
    return saved


@router.post("/{crawl_id}/verification", status_code=201)
def create_verification_report(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    crawl_a: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    """Build before/after verification markdown + PDF vs a prior crawl."""
    crawl_b, website = _require_crawl(website_id, crawl_id, db)
    if crawl_b.status != CrawlStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Crawl must be completed")

    if crawl_a is None:
        prior = db.execute(
            select(Crawl)
            .where(
                Crawl.website_id == website_id,
                Crawl.status == CrawlStatus.COMPLETED,
                Crawl.id != crawl_b.id,
                Crawl.created_at < crawl_b.created_at,
            )
            .order_by(Crawl.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is None:
            raise HTTPException(
                status_code=404,
                detail="No prior completed crawl to compare against",
            )
        crawl_a_row = prior
    else:
        crawl_a_row = db.get(Crawl, crawl_a)
        if crawl_a_row is None or crawl_a_row.website_id != website_id:
            raise HTTPException(status_code=404, detail="Baseline crawl not found")

    # Reuse compare endpoint logic via internal call shape.
    findings_a = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_a_row.id)
    ).scalars().all()
    findings_b = db.execute(
        select(Finding).where(Finding.crawl_id == crawl_b.id)
    ).scalars().all()

    def finding_key(finding):
        return (finding.code, finding.url)

    map_a = {finding_key(f): f for f in findings_a}
    map_b = {finding_key(f): f for f in findings_b}
    keys_a, keys_b = set(map_a), set(map_b)

    def serialize(f):
        return {
            "code": f.code,
            "severity": f.severity,
            "category": f.category,
            "title": f.title,
            "description": f.description,
            "url": f.url,
            "detail": f.detail,
        }

    comparison = {
        "summary": {
            "crawl_a_findings": len(findings_a),
            "crawl_b_findings": len(findings_b),
            "new": len(keys_b - keys_a),
            "resolved": len(keys_a - keys_b),
            "unchanged": len(keys_a & keys_b),
        },
        "new": [serialize(map_b[k]) for k in keys_b - keys_a],
        "resolved": [serialize(map_a[k]) for k in keys_a - keys_b],
        "unchanged": [serialize(map_b[k]) for k in keys_a & keys_b],
    }

    root_a = get_crawl_root(website.domain, crawl_a_row.id)
    root_b = get_crawl_root(website.domain, crawl_b.id)
    report = generate_verification_report(
        root_b,
        domain=website.domain,
        crawl_a=_crawl_meta(crawl_a_row),
        crawl_b=_crawl_meta(crawl_b),
        comparison=comparison,
        root_a=root_a,
    )
    return {
        **report,
        "url": f"/data/websites/{website.domain}/crawls/{crawl_b.id}/{report['pdf_file']}",
        "markdown_url": (
            f"/data/websites/{website.domain}/crawls/{crawl_b.id}/{report['markdown_file']}"
        ),
    }


@router.get("/{crawl_id}/verification")
def get_verification_report(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    payload = load_verification_report(root)
    if payload is None:
        raise HTTPException(status_code=404, detail="Verification report not generated yet")
    return payload


@router.get("/{crawl_id}/checklist")
def get_checklist(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    rebuild: bool = False,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    if rebuild or load_checklist(root) is None:
        return build_checklist(
            root,
            recommendations=load_recommendations(root),
        )
    return load_checklist(root)


class ChecklistUpdate(BaseModel):
    items: list[dict]


@router.patch("/{crawl_id}/checklist")
def patch_checklist(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: ChecklistUpdate,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    return update_checklist_items(root, payload.items or [])


@router.get("/{crawl_id}/competitors")
def get_competitor_compare(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Compare this crawl against latest crawls of competitor websites on the project."""
    crawl, website = _require_crawl(website_id, crawl_id, db)
    if crawl.status != CrawlStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Crawl must be completed")

    siblings = db.execute(
        select(Website).where(Website.project_id == website.project_id)
    ).scalars().all()
    competitors = [
        w for w in siblings
        if (getattr(w, "role", None) or "primary") == "competitor"
        and w.id != website.id
    ]

    primary_root = get_crawl_root(website.domain, crawl.id)
    primary = {
        "domain": website.domain,
        "role": getattr(website, "role", None) or "primary",
        "root": primary_root,
        "crawl_id": str(crawl.id),
    }
    comp_entries = []
    for w in competitors[:3]:
        latest = db.execute(
            select(Crawl)
            .where(
                Crawl.website_id == w.id,
                Crawl.status == CrawlStatus.COMPLETED,
            )
            .order_by(Crawl.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            continue
        comp_entries.append(
            {
                "domain": w.domain,
                "role": "competitor",
                "root": get_crawl_root(w.domain, latest.id),
                "crawl_id": str(latest.id),
            }
        )

    return compare_competitors(primary, comp_entries)


@router.get("/{crawl_id}/upgrades")
def get_upgrades(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    advice = build_upgrade_advice(root)
    return advice


@router.get("/{crawl_id}/conversion-path")
def get_conversion_path(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    return analyze_conversion_path(root)


@router.get("/{crawl_id}/screenshots")
def get_screenshots(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    shots = list_crawl_screenshots(root)
    for s in shots:
        s["url"] = (
            f"/data/websites/{website.domain}/crawls/{crawl.id}/{s['path']}"
        )
    return {"domain": website.domain, "crawl_id": str(crawl.id), "screenshots": shots}


class VisionReviewBody(BaseModel):
    image_path: str
    question: str | None = None


@router.post("/{crawl_id}/vision")
def post_vision_review(
    website_id: uuid.UUID,
    crawl_id: uuid.UUID,
    payload: VisionReviewBody,
    db: Session = Depends(get_db),
):
    crawl, website = _require_crawl(website_id, crawl_id, db)
    root = get_crawl_root(website.domain, crawl.id)
    try:
        return review_screenshot(
            root,
            payload.image_path,
            question=payload.question,
            base_url=settings.ollama_base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


