from pathlib import Path

from backend.app.services.mockups import generate_mockups, load_mockups


def test_generate_mockups_writes_images(tmp_path: Path):
    recs = {
        "source": "rule_based",
        "website": {"domain": "example.com", "url": "https://example.com"},
        "scores": {"overall": 7.5, "by_category": {"seo": 6.0}},
        "recommendations": {
            "executive_summary": "Example site needs clearer SEO and trust signals.",
            "priority_actions": [
                {
                    "title": "Add meta description",
                    "why": "Improves search snippets.",
                    "how": "Write a unique description.",
                },
                {
                    "title": "Force HTTPS redirect",
                    "why": "Builds trust.",
                    "how": "Redirect http to https.",
                },
                {
                    "title": "Add H1",
                    "why": "Improves structure.",
                    "how": "Add one H1.",
                },
            ],
            "quick_wins": ["Add alt text", "Add robots.txt"],
            "mockup_prompts": [
                "Clean modern homepage with strong CTA",
                "Mobile-first landing page",
            ],
        },
    }

    manifest = generate_mockups(tmp_path, recommendations=recs, backend="concept")
    assert manifest["backend"] == "concept_pillow_v1"
    assert len(manifest["images"]) == 3

    for image in manifest["images"]:
        path = tmp_path / image["path"]
        assert path.exists()
        assert path.stat().st_size > 1000

    loaded = load_mockups(tmp_path)
    assert loaded is not None
    assert loaded["domain"] == "example.com"
