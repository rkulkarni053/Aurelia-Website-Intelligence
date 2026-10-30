from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from backend.app.services.playwright_env import ensure_playwright_browsers_path

AXE_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


def collect_accessibility(url: str) -> dict:
    """Run axe-core against a rendered page. Never raises; errors recorded."""
    evidence = {
        "url": url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "violations": [],
        "passes_count": None,
        "incomplete_count": None,
        "error": None,
    }

    try:
        ensure_playwright_browsers_path()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.add_script_tag(url=AXE_CDN_URL)

                results = page.evaluate(
                    "async () => await axe.run(document, "
                    "{resultTypes: ['violations', 'passes', 'incomplete']})"
                )

                evidence["violations"] = [
                    {
                        "id": v["id"],
                        "impact": v.get("impact"),
                        "description": v["description"],
                        "help": v["help"],
                        "help_url": v["helpUrl"],
                        "tags": v.get("tags", []),
                        "node_count": len(v.get("nodes", [])),
                        "sample_targets": [
                            n["target"] for n in v.get("nodes", [])[:5]
                        ],
                    }
                    for v in results.get("violations", [])
                ]
                evidence["passes_count"] = len(results.get("passes", []))
                evidence["incomplete_count"] = len(results.get("incomplete", []))
            finally:
                browser.close()

    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"

    return evidence
