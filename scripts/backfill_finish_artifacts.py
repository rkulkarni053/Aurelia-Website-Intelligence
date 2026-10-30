"""Backfill content SEO, Lighthouse, annotated screenshots, and packs.

Usage (from repo root):
  .venv/bin/python -m scripts.backfill_finish_artifacts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.annotate import annotate_screenshots  # noqa: E402
from backend.app.services.content_seo import collect_content_seo  # noqa: E402
from backend.app.services.evidence_pack import (  # noqa: E402
    PACK_FILENAME,
    build_and_write_evidence_pack,
)
from backend.app.services.findings import analyze_crawl  # noqa: E402
from backend.app.services.lighthouse_collector import collect_lighthouse  # noqa: E402
from backend.app.services.proposal_pdf import export_proposal_pdf  # noqa: E402
from backend.app.services.site_story import collect_site_story  # noqa: E402


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _pages_for_content(root: Path) -> list[dict]:
    pages_meta = _load(root / "evidence" / "pages.json") or {}
    pages = []
    for row in pages_meta.get("pages") or []:
        html = ""
        rel = row.get("html_file")
        if rel:
            path = root / rel
            if path.exists():
                html = path.read_text(encoding="utf-8", errors="replace")
        pages.append({"url": row.get("url") or "", "html": html})
    return pages


def process_crawl(crawl_root: Path) -> dict:
    domain = crawl_root.parents[1].name
    crawl_id = crawl_root.name
    notes = []

    pages = _pages_for_content(crawl_root)
    if pages:
        content = collect_content_seo(pages)
        (crawl_root / "seo").mkdir(parents=True, exist_ok=True)
        (crawl_root / "seo" / "content.json").write_text(
            json.dumps(content, indent=2), encoding="utf-8"
        )
        story = collect_site_story(pages)
        (crawl_root / "seo" / "site_story.json").write_text(
            json.dumps(story, indent=2), encoding="utf-8"
        )
        notes.append(f"content_seo={content.get('pages_analyzed', 0)}")
        notes.append(f"site_story={story.get('pages_used', 0)}")
    else:
        notes.append("content_seo=skipped")

    findings = analyze_crawl(crawl_root)
    (crawl_root / "evidence" / "findings.json").write_text(
        json.dumps(findings, indent=2), encoding="utf-8"
    )
    notes.append(f"findings={len(findings)}")

    annotated = annotate_screenshots(crawl_root)
    notes.append(f"annotated={len(annotated.get('images') or [])}")

    urls = [p.get("url") for p in pages[:3] if p.get("url")]
    if not urls:
        urls = ["https://" + domain]
    lighthouse = collect_lighthouse(crawl_root, urls, prefer_cli=False)
    (crawl_root / "lighthouse").mkdir(parents=True, exist_ok=True)
    (crawl_root / "lighthouse" / "summary.json").write_text(
        json.dumps(lighthouse, indent=2), encoding="utf-8"
    )
    overall = (lighthouse.get("aggregate") or {}).get("overall_out_of_10")
    notes.append(f"lighthouse={overall}/10 ({lighthouse.get('source')})")

    if (crawl_root / "proposal" / "proposal.md").exists():
        try:
            export_proposal_pdf(crawl_root)
            notes.append("pdf=yes")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"pdf=err:{exc}")

    pack = build_and_write_evidence_pack(
        crawl_root,
        website={"domain": domain},
        crawl={"id": crawl_id},
    )
    notes.append(f"pack_score={pack['scores']['overall']}/10")
    return {"crawl": str(crawl_root.relative_to(ROOT)), "notes": notes}


def main() -> int:
    data = ROOT / "data" / "websites"
    if not data.exists():
        print(f"No data directory at {data}")
        return 1

    done = 0
    for findings_path in sorted(data.glob("*/crawls/*/evidence/findings.json")):
        crawl_root = findings_path.parents[1]
        result = process_crawl(crawl_root)
        print(f"{result['crawl']}: " + ", ".join(result["notes"]))
        done += 1

    print(f"done: {done} crawl(s); packs at */{PACK_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
