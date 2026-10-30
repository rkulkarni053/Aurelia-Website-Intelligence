import json
from pathlib import Path

from backend.app.services.conversion_path import analyze_conversion_path, conversion_findings
from backend.app.services.upgrade_advisor import build_upgrade_advice
from backend.app.services.checklist import build_checklist, update_checklist_items
from backend.app.services.proposal import build_scoped_packages, load_proposal_config, update_proposal, generate_proposal
from backend.app.services.verification_report import generate_verification_report
from backend.app.services.competitor_compare import compare_competitors


def test_conversion_path_detects_gaps(tmp_path: Path):
    (tmp_path / "seo").mkdir()
    (tmp_path / "seo" / "site_story.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "url": "https://example.com/",
                        "role": "home",
                        "h1": ["Welcome"],
                        "ctas": ["Learn more"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    path = analyze_conversion_path(tmp_path)
    assert path["strength"] in {"weak", "mixed"}
    findings = conversion_findings(tmp_path)
    assert any(f["code"] in {"weak_cta_path", "missing_contact_path"} for f in findings)


def test_upgrade_advisor_wordpress(tmp_path: Path):
    (tmp_path / "technologies").mkdir()
    (tmp_path / "technologies" / "technologies.json").write_text(
        json.dumps(
            {
                "site_url": "https://example.com",
                "detections": [{"name": "WordPress", "category": "cms"}],
            }
        ),
        encoding="utf-8",
    )
    advice = build_upgrade_advice(tmp_path)
    assert any(o.get("technology") == "WordPress" for o in advice["opportunities"])


def test_checklist_toggle(tmp_path: Path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "recommendations.json").write_text(
        json.dumps(
            {
                "recommendations": {
                    "priority_actions": [
                        {
                            "title": "Fix titles",
                            "category": "seo",
                            "impact": "high",
                            "effort": "low",
                            "why": "SEO",
                            "how": "Write titles",
                        }
                    ],
                    "quick_wins": ["Add meta"],
                }
            }
        ),
        encoding="utf-8",
    )
    check = build_checklist(tmp_path)
    assert check["total"] >= 1
    item_id = check["items"][0]["id"]
    updated = update_checklist_items(tmp_path, [{"id": item_id, "done": True}])
    assert updated["done_count"] >= 1


def test_scoped_packages_include_findings():
    config = load_proposal_config()
    packages = build_scoped_packages(
        config,
        findings=[
            {
                "code": "missing_sitemap",
                "severity": "high",
                "category": "seo",
                "title": "No sitemap",
                "description": "missing",
            }
        ],
        recommendations={
            "priority_actions": [
                {"title": "Add sitemap", "impact": "high", "why": "x", "how": "y"}
            ]
        },
    )
    growth_includes = "\n".join(packages.get("growth", {}).get("includes") or [])
    assert "No sitemap" in growth_includes or "sitemap" in growth_includes.lower()


def test_update_proposal(tmp_path: Path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "evidence_pack.json").write_text(
        json.dumps(
            {
                "website": {"domain": "example.com", "url": "https://example.com"},
                "crawl": {"id": "c1"},
                "scores": {"overall": 7.0, "by_category": {"seo": 6}},
                "findings": {
                    "top": [
                        {
                            "title": "No sitemap",
                            "severity": "medium",
                            "category": "seo",
                            "description": "missing",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    generate_proposal(tmp_path, prefer_ollama=False)
    updated = update_proposal(
        tmp_path,
        narratives={"executive_summary": "Edited summary for the client."},
        recommended_package="essentials",
    )
    assert "Edited summary" in updated["markdown"]
    assert updated["recommended_package"] == "essentials"
    assert updated.get("edited") is True


def test_verification_report(tmp_path: Path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    for root, overall in ((root_a, 6.0), (root_b, 8.0)):
        (root / "evidence").mkdir(parents=True)
        (root / "evidence" / "evidence_pack.json").write_text(
            json.dumps(
                {
                    "scores": {
                        "overall": overall,
                        "by_category": {"seo": overall, "accessibility": overall},
                    }
                }
            ),
            encoding="utf-8",
        )
    report = generate_verification_report(
        root_b,
        domain="example.com",
        crawl_a={"id": "a"},
        crawl_b={"id": "b"},
        comparison={
            "summary": {"new": 0, "resolved": 1, "unchanged": 2},
            "resolved": [
                {
                    "code": "missing_sitemap",
                    "severity": "medium",
                    "category": "seo",
                    "title": "No sitemap",
                    "description": "fixed",
                }
            ],
            "new": [],
        },
        root_a=root_a,
    )
    assert report["pdf_file"].endswith(".pdf")
    assert (root_b / report["pdf_file"]).exists()
    assert report["score_delta"]["overall_delta"] == 2.0


def test_competitor_compare(tmp_path: Path):
    primary = tmp_path / "primary"
    comp = tmp_path / "comp"
    for root, overall, domain in (
        (primary, 7.0, "client.com"),
        (comp, 8.5, "rival.com"),
    ):
        (root / "evidence").mkdir(parents=True)
        (root / "seo").mkdir(parents=True)
        (root / "evidence" / "evidence_pack.json").write_text(
            json.dumps(
                {
                    "scores": {"overall": overall, "by_category": {"seo": overall}},
                    "findings": {"total": 3, "by_severity": {"high": 1}},
                    "technologies": {"detections": []},
                }
            ),
            encoding="utf-8",
        )
        (root / "seo" / "site_story.json").write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "role": "home",
                            "url": f"https://{domain}/",
                            "h1": ["Hello"],
                            "ctas": ["Contact us"] if domain == "rival.com" else [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    result = compare_competitors(
        {"domain": "client.com", "role": "primary", "root": primary, "crawl_id": "1"},
        [{"domain": "rival.com", "role": "competitor", "root": comp, "crawl_id": "2"}],
    )
    assert len(result["scoreboard"]) == 2
    assert result["insights"]
