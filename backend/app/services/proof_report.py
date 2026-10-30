"""Build downloadable proof packages: SiteOne reports + screenshots + evidence."""

from __future__ import annotations

import html
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORTS_DIR = "reports"
MANIFEST_FILENAME = "reports/manifest.json"
PROOF_ZIP = "reports/proof-pack.zip"
PROOF_INDEX = "reports/index.html"

# Relative paths / globs to include in the proof ZIP when present.
PROOF_INCLUDE = (
    "reports/siteone/report.html",
    "reports/siteone/report.json",
    "reports/siteone/report.txt",
    "seo/siteone_summary.json",
    "seo/analysis.json",
    "seo/content.json",
    "seo/robots.txt",
    "seo/sitemap.xml",
    "ssl/certificate.json",
    "technologies/technologies.json",
    "lighthouse/summary.json",
    "evidence/findings.json",
    "evidence/evidence_pack.json",
    "evidence/pages.json",
    "evidence/browser.json",
    "evidence/performance.json",
    "evidence/accessibility.json",
    "evidence/annotated_screenshots.json",
    "proposal/proposal.md",
    "proposal/proposal.pdf",
)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _iter_screenshots(root: Path) -> list[str]:
    shots_dir = root / "screenshots"
    if not shots_dir.is_dir():
        return []
    paths = []
    for path in sorted(shots_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            paths.append(str(path.relative_to(root)))
    return paths


def _data_url(domain: str, crawl_id: str, rel: str) -> str:
    return f"/data/websites/{domain}/crawls/{crawl_id}/{rel}"


def build_reports_index_html(
    *,
    domain: str,
    crawl_id: str,
    website_url: str | None,
    manifest: dict,
) -> str:
    downloads = manifest.get("downloads") or []
    screenshots = manifest.get("screenshots") or []
    siteone = manifest.get("siteone") or {}
    scores = (siteone.get("scores") or {}) if isinstance(siteone, dict) else {}

    def link_row(item: dict) -> str:
        href = html.escape(item.get("url") or "#")
        label = html.escape(item.get("label") or item.get("path") or "Download")
        kind = html.escape(item.get("kind") or "")
        avail = item.get("available", True)
        if not avail:
            return (
                f'<li class="missing"><span>{label}</span>'
                f'<em>not available</em></li>'
            )
        return (
            f'<li><a href="{href}" download target="_blank" rel="noopener">'
            f"{label}</a> <span class='kind'>{kind}</span></li>"
        )

    shot_cards = []
    for shot in screenshots:
        href = html.escape(shot.get("url") or "")
        caption = html.escape(shot.get("label") or shot.get("path") or "")
        shot_cards.append(
            f'<figure><a href="{href}" target="_blank" rel="noopener">'
            f'<img src="{href}" alt="{caption}" loading="lazy" /></a>'
            f"<figcaption>{caption}</figcaption></figure>"
        )

    score_bits = []
    if scores.get("overall") is not None:
        score_bits.append(f"Overall {scores['overall']}/10")
    by_cat = scores.get("by_category") or {}
    for key in ("seo", "performance", "accessibility", "security", "best-practices"):
        if by_cat.get(key) is not None:
            score_bits.append(f"{key} {by_cat[key]}/10")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Audit proofs — {html.escape(domain)}</title>
  <style>
    :root {{
      --ink: #132033; --muted: #5b6b7c; --line: #d9e0ea; --bg: #f4f7fb; --card: #fff;
      --accent: #1f4b99;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink); background:
        radial-gradient(1200px 500px at 10% -10%, #d9e8ff 0%, transparent 55%),
        linear-gradient(180deg, #eef3f9, var(--bg));
    }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
    h1 {{ font-size: 1.6rem; margin: 0 0 6px; letter-spacing: -0.02em; }}
    .sub {{ color: var(--muted); margin-bottom: 24px; }}
    section {{
      background: var(--card); border: 1px solid var(--line); border-radius: 14px;
      padding: 18px 20px; margin-bottom: 16px;
    }}
    h2 {{ font-size: 1rem; margin: 0 0 12px; }}
    ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }}
    li {{ display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }}
    a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .kind, em {{ color: var(--muted); font-size: 0.85rem; font-style: normal; }}
    .missing {{ opacity: 0.55; }}
    .scores {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    .chip {{
      background: #eaf1ff; color: #1f4b99; border-radius: 999px;
      padding: 4px 10px; font-size: 0.8rem; font-weight: 600;
    }}
    .gallery {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 12px;
    }}
    figure {{ margin: 0; }}
    img {{
      width: 100%; aspect-ratio: 16/10; object-fit: cover; object-position: top;
      border: 1px solid var(--line); border-radius: 10px; background: #f0f3f7;
    }}
    figcaption {{ font-size: 0.78rem; color: var(--muted); margin-top: 6px; word-break: break-all; }}
  </style>
</head>
<body>
  <main>
    <h1>Audit proofs</h1>
    <p class="sub">
      {html.escape(domain)}
      {(" · " + html.escape(website_url)) if website_url else ""}
      · crawl {html.escape(str(crawl_id))}
      · generated {html.escape(manifest.get("generated_at") or "")}
    </p>

    <section>
      <h2>SiteOne quality scores</h2>
      <div class="scores">
        {"".join(f'<span class="chip">{html.escape(s)}</span>' for s in score_bits) or "<span class='kind'>No SiteOne scores yet</span>"}
      </div>
    </section>

    <section>
      <h2>Downloadable reports</h2>
      <ul>
        {"".join(link_row(item) for item in downloads) or "<li class='missing'>No reports</li>"}
      </ul>
    </section>

    <section>
      <h2>Screenshot proofs</h2>
      <div class="gallery">
        {"".join(shot_cards) or "<p class='kind'>No screenshots captured for this crawl.</p>"}
      </div>
    </section>
  </main>
</body>
</html>
"""


def build_proof_pack(
    root: Path,
    *,
    domain: str,
    crawl_id: str,
    website_url: str | None = None,
) -> dict:
    """Write proof ZIP + HTML index + manifest under reports/."""
    reports = root / REPORTS_DIR
    reports.mkdir(parents=True, exist_ok=True)

    siteone = _load(root / "seo" / "siteone_summary.json") or {}
    annotated = _load(root / "evidence" / "annotated_screenshots.json") or {}
    annotated_images = annotated.get("images") or []

    screenshot_rels = _iter_screenshots(root)
    screenshot_entries = []
    for rel in screenshot_rels:
        label = Path(rel).name
        kind = "annotated" if "/annotated/" in rel.replace("\\", "/") else "screenshot"
        screenshot_entries.append(
            {
                "path": rel,
                "label": label,
                "kind": kind,
                "url": _data_url(domain, crawl_id, rel),
            }
        )

    download_specs = [
        ("Proof pack (ZIP)", PROOF_ZIP, "zip"),
        ("Proof index (HTML)", PROOF_INDEX, "html"),
        ("SiteOne audit report (HTML)", "reports/siteone/report.html", "siteone"),
        ("SiteOne audit data (JSON)", "reports/siteone/report.json", "siteone"),
        ("SiteOne audit text", "reports/siteone/report.txt", "siteone"),
        ("SiteOne summary", "seo/siteone_summary.json", "siteone"),
        ("Findings", "evidence/findings.json", "evidence"),
        ("Evidence pack", "evidence/evidence_pack.json", "evidence"),
        ("Content SEO", "seo/content.json", "seo"),
        ("Technical SEO", "seo/analysis.json", "seo"),
        ("Lighthouse summary", "lighthouse/summary.json", "performance"),
        ("SSL certificate", "ssl/certificate.json", "security"),
        ("Proposal (PDF)", "proposal/proposal.pdf", "proposal"),
        ("Proposal (Markdown)", "proposal/proposal.md", "proposal"),
    ]

    downloads = []
    for label, rel, kind in download_specs:
        exists = (root / rel).exists()
        # ZIP is created below; mark available once written.
        downloads.append(
            {
                "label": label,
                "path": rel,
                "kind": kind,
                "available": exists or rel == PROOF_ZIP or rel == PROOF_INDEX,
                "url": _data_url(domain, crawl_id, rel),
            }
        )

    # Prefer annotated shots first in the gallery.
    annotated_first = sorted(
        screenshot_entries,
        key=lambda s: (0 if s["kind"] == "annotated" else 1, s["path"]),
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "crawl_id": str(crawl_id),
        "website_url": website_url,
        "siteone": {
            "ok": siteone.get("ok"),
            "available": siteone.get("available"),
            "error": siteone.get("error"),
            "scores": siteone.get("scores"),
            "files": siteone.get("files") or {},
            "visited_urls": siteone.get("visited_urls"),
        },
        "downloads": downloads,
        "screenshots": annotated_first,
        "annotated_count": len(annotated_images),
        "screenshot_count": len(screenshot_entries),
    }

    index_html = build_reports_index_html(
        domain=domain,
        crawl_id=str(crawl_id),
        website_url=website_url,
        manifest=manifest,
    )
    (root / PROOF_INDEX).write_text(index_html, encoding="utf-8")

    zip_path = root / PROOF_ZIP
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", index_html)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for rel in PROOF_INCLUDE:
            path = root / rel
            if path.is_file():
                zf.write(path, arcname=rel)
        for rel in screenshot_rels:
            path = root / rel
            if path.is_file():
                zf.write(path, arcname=rel)

    # Refresh availability flags now that ZIP/index exist.
    for item in downloads:
        item["available"] = (root / item["path"]).exists()

    manifest["downloads"] = downloads
    (root / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def load_reports_manifest(root: Path) -> dict | None:
    return _load(root / MANIFEST_FILENAME)
