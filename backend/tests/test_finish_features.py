"""Tests for content SEO, lighthouse heuristic, annotate, PDF, workflow."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from backend.app.models.project import Project, ProjectStatus
from backend.app.services.annotate import annotate_screenshots
from backend.app.services.content_seo import analyze_page_content, collect_content_seo
from backend.app.services.evidence_pack import build_evidence_pack
from backend.app.services.findings import analyze_crawl
from backend.app.services.lighthouse_collector import collect_lighthouse
from backend.app.services.proposal_pdf import markdown_to_pdf
from backend.app.services.workflow import can_transition, set_project_status


def test_content_seo_detects_thin_and_missing_h1():
    html = """
    <html><head><title>Hi</title>
    <meta name="description" content="short">
    </head><body><p>Hello world site</p></body></html>
    """
    page = analyze_page_content("https://example.com/", html)
    assert page["thin_content"] is True
    assert page["missing_h1"] is True
    assert page["title_too_short"] is True

    bundle = collect_content_seo(
        [{"url": "https://example.com/", "html": html}],
        sample=1,
    )
    assert bundle["pages_analyzed"] == 1
    assert bundle["thin_content_pages"] == 1
    assert bundle["missing_h1_pages"] == 1


def test_lighthouse_heuristic_and_pack_merge(tmp_path: Path):
    root = tmp_path
    (root / "evidence").mkdir()
    (root / "seo").mkdir()
    (root / "evidence" / "findings.json").write_text("[]", encoding="utf-8")
    (root / "evidence" / "performance.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://example.com/",
                    "final_url": "https://example.com/",
                    "performance": {"lcp_ms": 1800},
                    "error": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "evidence" / "accessibility.json").write_text(
        json.dumps([{"url": "https://example.com/", "violations": []}]),
        encoding="utf-8",
    )
    (root / "seo" / "analysis.json").write_text(
        json.dumps({"sitemap_found": True, "robots": {"found": True}}),
        encoding="utf-8",
    )
    (root / "seo" / "content.json").write_text(
        json.dumps({"pages": [], "pages_analyzed": 0}),
        encoding="utf-8",
    )

    summary = collect_lighthouse(
        root, ["https://example.com/"], prefer_cli=False
    )
    assert summary["source"] == "heuristic_v1"
    assert summary["aggregate"]["overall"] is not None
    (root / "lighthouse" / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )

    (root / "evidence" / "pages.json").write_text(
        json.dumps({"pages": [], "errors": []}), encoding="utf-8"
    )
    (root / "evidence" / "browser.json").write_text("[]", encoding="utf-8")

    pack = build_evidence_pack(root, website={"domain": "example.com"}, crawl={"id": "x"})
    assert "lighthouse" in (pack["scores"].get("method") or "")
    assert pack["scores"]["overall"] == summary["aggregate"]["overall_out_of_10"]


def test_annotate_screenshots_writes_overlay(tmp_path: Path):
    root = tmp_path
    shot_rel = "screenshots/home-desktop.png"
    (root / "screenshots").mkdir()
    Image.new("RGB", (640, 400), color=(40, 80, 120)).save(root / shot_rel)

    (root / "evidence").mkdir()
    (root / "evidence" / "findings.json").write_text(
        json.dumps(
            [
                {
                    "code": "thin_content",
                    "severity": "high",
                    "category": "seo",
                    "title": "Thin content",
                    "description": "Too few words",
                    "url": "https://example.com/",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "evidence" / "browser.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://example.com/",
                    "final_url": "https://example.com/",
                    "screenshots": {"desktop": shot_rel},
                    "error": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    manifest = annotate_screenshots(root)
    assert len(manifest["images"]) == 1
    out = root / manifest["images"][0]["annotated_path"]
    assert out.exists()
    assert out.stat().st_size > 0


def test_content_seo_findings_from_disk(tmp_path: Path):
    root = tmp_path
    (root / "seo").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    for name in (
        "browser.json",
        "performance.json",
        "pages.json",
        "accessibility.json",
    ):
        (root / "evidence" / name).write_text(
            "[]" if name != "pages.json" else json.dumps({"pages": [], "errors": []}),
            encoding="utf-8",
        )
    (root / "ssl").mkdir()
    (root / "ssl" / "certificate.json").write_text("{}", encoding="utf-8")
    (root / "seo" / "analysis.json").write_text("{}", encoding="utf-8")
    (root / "seo" / "content.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "url": "https://example.com/",
                        "thin_content": True,
                        "missing_h1": True,
                        "word_count": 12,
                        "title_too_short": False,
                        "title_too_long": False,
                        "meta_too_short": False,
                        "meta_too_long": False,
                        "keyword_stuffing_risk": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    findings = analyze_crawl(root)
    codes = {f["code"] for f in findings}
    assert "thin_content" in codes
    assert "missing_h1" in codes


def test_proposal_pdf_export(tmp_path: Path):
    md = "# Proposal\n\n## Scope\n\n- Fix SEO\n- Improve speed\n"
    out = tmp_path / "proposal.pdf"
    path = markdown_to_pdf(md, out)
    assert path.exists()
    assert path.stat().st_size > 100


def test_workflow_transitions():
    project = Project(name="Demo")
    project.status = ProjectStatus.AWAITING_APPROVAL
    assert can_transition(project.status, ProjectStatus.APPROVED)
    set_project_status(project, ProjectStatus.APPROVED)
    assert project.status == ProjectStatus.APPROVED
    set_project_status(project, ProjectStatus.IMPLEMENTATION)
    set_project_status(project, ProjectStatus.VERIFICATION)
    assert can_transition(project.status, ProjectStatus.CRAWLING)
