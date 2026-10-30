import json
from pathlib import Path

from backend.app.services.findings import analyze_crawl
from backend.app.services.proof_report import build_proof_pack
from backend.app.services.siteone_collector import _summarize_json


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        path.write_text(str(data), encoding="utf-8")


def test_summarize_siteone_json():
    payload = {
        "qualityScores": {
            "overall": {"score": 7.5, "label": "Good", "code": "overall"},
            "categories": [
                {
                    "code": "seo",
                    "score": 8.0,
                    "label": "Good",
                    "name": "SEO",
                    "deductions": [{"reason": "missing h1", "fix": "add h1", "points": 0.3}],
                }
            ],
        },
        "summary": {
            "items": [
                {"aplCode": "pages-without-h1", "status": "CRITICAL", "text": "1 page without h1"},
                {"aplCode": "webp-support", "status": "WARNING", "text": "No WebP"},
                {"aplCode": "ok-item", "status": "OK", "text": "All good"},
            ]
        },
        "tables": {"seo": {"rows": [{}, {}]}, "404": {"rows": []}},
        "results": [{"url": "https://example.com/"}],
        "error": [],
    }
    summary = _summarize_json(
        payload,
        url="https://example.com",
        files={"html": "reports/siteone/report.html"},
    )
    assert summary["ok"] is True
    assert summary["scores"]["overall"] == 7.5
    assert summary["scores"]["by_category"]["seo"] == 8.0
    assert summary["visited_urls"] == 1
    assert summary["counts"]["seo_pages"] == 2
    assert len(summary["summary_items"]) == 3


def test_siteone_findings_and_proof_pack(tmp_path: Path):
    root = tmp_path
    _write(
        root / "seo" / "siteone_summary.json",
        {
            "tool": "siteone-crawler",
            "url": "https://example.com",
            "available": True,
            "ok": True,
            "scores": {
                "overall": 4.2,
                "by_category": {"seo": 6.0, "security": 3.0},
            },
            "summary_items": [
                {
                    "code": "pages-without-h1",
                    "status": "CRITICAL",
                    "text": "1 page(s) without <h1> heading",
                },
                {
                    "code": "ssl-protocol-unsafe",
                    "status": "WARNING",
                    "text": "TLS 1.0 is unsafe",
                },
            ],
            "files": {
                "html": "reports/siteone/report.html",
                "json": "reports/siteone/report.json",
            },
        },
    )
    _write(root / "evidence" / "findings.json", [])
    _write(root / "reports" / "siteone" / "report.html", "<html>report</html>")
    _write(root / "reports" / "siteone" / "report.json", {"ok": True})
    shot = root / "screenshots" / "example-desktop.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    annotated = root / "screenshots" / "annotated" / "example-desktop-annotated.png"
    annotated.parent.mkdir(parents=True, exist_ok=True)
    annotated.write_bytes(b"\x89PNG\r\n\x1a\nanno")

    findings = analyze_crawl(root)
    codes = {f["code"] for f in findings}
    assert "siteone_pages-without-h1" in codes
    assert "siteone_ssl-protocol-unsafe" in codes
    assert "siteone_low_overall_score" in codes
    h1 = next(f for f in findings if f["code"] == "siteone_pages-without-h1")
    assert h1["severity"] == "high"
    assert h1["category"] == "seo"

    manifest = build_proof_pack(
        root,
        domain="example.com",
        crawl_id="crawl-1",
        website_url="https://example.com",
    )
    assert (root / "reports" / "proof-pack.zip").exists()
    assert (root / "reports" / "index.html").exists()
    assert (root / "reports" / "manifest.json").exists()
    assert manifest["screenshot_count"] == 2
    assert any(d["path"] == "reports/proof-pack.zip" and d["available"] for d in manifest["downloads"])
    html = (root / "reports" / "index.html").read_text(encoding="utf-8")
    assert "Audit proofs" in html
    assert "example-desktop-annotated.png" in html
