from pathlib import Path

from backend.app.services.proposal import (
    build_proposal_markdown,
    generate_proposal,
    load_proposal_config,
)


def test_build_proposal_markdown_includes_sections():
    config = load_proposal_config()
    md = build_proposal_markdown(
        config=config,
        website={"domain": "example.com", "url": "https://example.com"},
        crawl={"id": "crawl-1"},
        scores={"overall": 7.5, "by_category": {"seo": 6.0, "security": 8.0}},
        findings=[
            {
                "severity": "medium",
                "title": "Missing meta description",
                "category": "seo",
                "description": "No meta description found.",
            }
        ],
        recommendations={
            "executive_summary": "Needs SEO basics.",
            "quick_wins": ["Add meta description"],
            "priority_actions": [
                {
                    "title": "Add meta description",
                    "impact": "medium",
                    "why": "Better snippets.",
                    "how": "Write unique copy.",
                }
            ],
            "strategic_improvements": ["Homepage redesign"],
            "proposal_angles": ["Fixed-scope remediation"],
        },
        mockups={
            "images": [
                {"label": "Desktop", "path": "mockups/ai-desktop-homepage.png"}
            ]
        },
        narratives={
            "executive_summary": "Example needs improvement.",
            "opportunity": "Fix SEO to improve discovery.",
            "closing": "Approve to proceed.",
        },
        recommended_package_key="growth",
    )

    assert "# Website Improvement Proposal" in md
    assert "example.com" in md
    assert "Missing meta description" in md
    assert "Growth" in md
    assert "mockups/ai-desktop-homepage.png" in md
    assert "3,500" in md or "3500" in md or "€3500" in md


def test_generate_proposal_writes_files(tmp_path: Path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "evidence_pack.json").write_text(
        __import__("json").dumps(
            {
                "website": {"domain": "example.com", "url": "https://example.com"},
                "crawl": {"id": "abc"},
                "scores": {"overall": 8.1, "by_category": {"seo": 7.2}},
                "findings": {
                    "top": [
                        {
                            "title": "No sitemap",
                            "severity": "medium",
                            "category": "seo",
                            "description": "Sitemap missing",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence" / "recommendations.json").write_text(
        __import__("json").dumps(
            {
                "recommendations": {
                    "executive_summary": "Improve SEO.",
                    "quick_wins": ["Add sitemap"],
                    "priority_actions": [],
                    "strategic_improvements": [],
                    "proposal_angles": ["Remediation package"],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = generate_proposal(tmp_path, prefer_ollama=False)
    assert payload["source"] == "rule_based"
    assert (tmp_path / "proposal" / "proposal.md").exists()
    assert "Website Improvement Proposal" in payload["markdown"]
    loaded = __import__("backend.app.services.proposal", fromlist=["load_proposal"]).load_proposal(
        tmp_path
    )
    assert loaded is not None
    assert "markdown" in loaded
