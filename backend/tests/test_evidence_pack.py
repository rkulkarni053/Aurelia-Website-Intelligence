from pathlib import Path

from backend.app.services.evidence_pack import build_evidence_pack


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(data, indent=2), encoding="utf-8")


def test_build_evidence_pack_scores_and_truncates(tmp_path: Path):
    root = tmp_path

    _write_json(
        root / "evidence" / "findings.json",
        [
            {
                "code": "missing_title",
                "severity": "high",
                "category": "seo",
                "title": "Missing title",
                "description": "No title",
                "url": "https://example.com/",
                "evidence_file": "evidence/browser.json",
                "detail": {"sample": list(range(10))},
            },
            {
                "code": "http_not_redirected_to_https",
                "severity": "medium",
                "category": "security",
                "title": "HTTP not redirected",
                "description": "No HTTPS redirect",
                "url": "example.com",
                "evidence_file": "ssl/certificate.json",
                "detail": None,
            },
        ],
    )
    _write_json(
        root / "evidence" / "pages.json",
        {
            "pages": [
                {
                    "url": "https://example.com/",
                    "status_code": 200,
                    "title": "Example",
                    "html_file": "html/example-com.html",
                }
            ],
            "errors": [],
        },
    )
    _write_json(
        root / "evidence" / "browser.json",
        [
            {
                "url": "https://example.com/",
                "final_url": "https://example.com/",
                "load_time_ms": 120,
                "screenshots": {
                    "desktop": "screenshots/example-com-desktop.png",
                    "mobile": "screenshots/example-com-mobile.png",
                },
                "rendered_html_file": "html/example-com-rendered.html",
                "dom": {"title": "Example"},
                "error": None,
            }
        ],
    )
    _write_json(
        root / "evidence" / "performance.json",
        [
            {
                "url": "https://example.com/",
                "final_url": "https://example.com/",
                "performance": {"lcp_ms": 2100, "fcp_ms": 400},
                "error": None,
            }
        ],
    )
    _write_json(root / "evidence" / "accessibility.json", [])
    _write_json(
        root / "ssl" / "certificate.json",
        {
            "https_enabled": True,
            "certificate_valid": True,
            "tls_version": "TLSv1.3",
            "issuer": {"organizationName": "Test CA"},
            "days_remaining": 80,
            "http_to_https": {"status_code": 301, "location": "https://example.com/"},
            "error": None,
        },
    )
    _write_json(
        root / "seo" / "analysis.json",
        {
            "robots": {"found": False},
            "sitemap_found": False,
            "sitemap_declared_in_robots": False,
            "total_sitemap_urls": 0,
        },
    )
    _write_json(
        root / "technologies" / "technologies.json",
        {
            "detections": [
                {"name": "Cloudflare", "category": "cdn", "pages_matched": 0}
            ]
        },
    )

    pack = build_evidence_pack(
        root,
        website={"domain": "example.com", "url": "https://example.com"},
        crawl={"id": "test-crawl"},
    )

    assert pack["version"] == 1
    assert pack["website"]["domain"] == "example.com"
    assert pack["findings"]["total"] == 2
    assert pack["findings"]["top"][0]["detail"]["sample"] == [0, 1, 2]
    assert pack["scores"]["scale"] == 10
    assert "seo" in pack["scores"]["by_category"]
    assert pack["scores"]["by_category"]["seo"] < 10
    assert pack["screenshots"][0]["path"].endswith(".png")
    assert pack["artifact_paths"]["pack"] == "evidence/evidence_pack.json"
