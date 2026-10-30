"""Run SiteOne Crawler as a local CLI and capture HTML/JSON/TXT audit reports.

SiteOne is free/open-source. There is no hosted REST API — we shell out to the
binary and store its reports under the crawl root for downloadable proof.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SITEONE_DIR = "reports/siteone"
SUMMARY_FILENAME = "seo/siteone_summary.json"
DEFAULT_MAX_URLS = 200
DEFAULT_TIMEOUT_SEC = 15
DEFAULT_RUN_TIMEOUT_SEC = 300

# Candidate binary locations (first hit wins).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CANDIDATE_BINS = (
    Path(os.environ["SITEONE_CRAWLER_BIN"])
    if os.environ.get("SITEONE_CRAWLER_BIN")
    else None,
    _PROJECT_ROOT / "bin" / "siteone-crawler",
    Path.home() / ".local" / "bin" / "siteone-crawler",
)


def resolve_siteone_binary() -> str | None:
    """Return path/name of siteone-crawler, or None if unavailable."""
    for candidate in _CANDIDATE_BINS:
        if candidate is None:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("siteone-crawler")


def _empty_summary(*, url: str, error: str | None = None, skipped: bool = False) -> dict:
    return {
        "tool": "siteone-crawler",
        "url": url,
        "available": False,
        "skipped": skipped,
        "ok": False,
        "error": error,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scores": None,
        "summary_items": [],
        "visited_urls": 0,
        "files": {},
    }


def _table_row_count(tables: dict | None, key: str) -> int:
    table = (tables or {}).get(key) or {}
    rows = table.get("rows")
    return len(rows) if isinstance(rows, list) else 0


def _summarize_json(payload: dict, *, url: str, files: dict) -> dict:
    scores_raw = payload.get("qualityScores") or {}
    categories = {}
    for cat in scores_raw.get("categories") or []:
        code = cat.get("code")
        if not code:
            continue
        categories[code] = {
            "score": cat.get("score"),
            "label": cat.get("label"),
            "name": cat.get("name"),
            "deductions": [
                {
                    "reason": d.get("reason"),
                    "fix": d.get("fix"),
                    "points": d.get("points"),
                }
                for d in (cat.get("deductions") or [])[:12]
            ],
        }
    overall = scores_raw.get("overall") or {}
    summary_items = []
    for item in (payload.get("summary") or {}).get("items") or []:
        summary_items.append(
            {
                "code": item.get("aplCode"),
                "status": item.get("status"),
                "text": item.get("text"),
            }
        )

    tables = payload.get("tables") or {}
    results = payload.get("results") or []
    return {
        "tool": "siteone-crawler",
        "url": url,
        "available": True,
        "skipped": False,
        "ok": True,
        "error": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scores": {
            "overall": overall.get("score"),
            "overall_label": overall.get("label"),
            "by_category": {k: v.get("score") for k, v in categories.items()},
            "categories": categories,
        },
        "summary_items": summary_items[:80],
        "visited_urls": len(results),
        "counts": {
            "seo_pages": _table_row_count(tables, "seo"),
            "404": _table_row_count(tables, "404"),
            "redirects": _table_row_count(tables, "redirects"),
            "security": _table_row_count(tables, "security"),
            "accessibility": _table_row_count(tables, "accessibility"),
        },
        "files": files,
        "errors": payload.get("error") or [],
    }


def collect_siteone(
    site_url: str,
    root: Path,
    *,
    max_urls: int = DEFAULT_MAX_URLS,
    request_timeout: int = DEFAULT_TIMEOUT_SEC,
    run_timeout: int = DEFAULT_RUN_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Run SiteOne against site_url and write reports under root.

    Never raises — returns a summary dict (ok=False on failure/skip).
    """
    out_dir = root / SITEONE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "report.html"
    json_path = out_dir / "report.json"
    txt_path = out_dir / "report.txt"
    files = {
        "html": f"{SITEONE_DIR}/report.html",
        "json": f"{SITEONE_DIR}/report.json",
        "txt": f"{SITEONE_DIR}/report.txt",
    }

    binary = resolve_siteone_binary()
    if not binary:
        summary = _empty_summary(
            url=site_url,
            error=(
                "siteone-crawler binary not found. Install with "
                "scripts/install_siteone.sh or set SITEONE_CRAWLER_BIN."
            ),
            skipped=True,
        )
        (root / SUMMARY_FILENAME).parent.mkdir(parents=True, exist_ok=True)
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    cmd = [
        binary,
        f"--url={site_url}",
        f"--max-visited-urls={max(1, int(max_urls))}",
        f"--timeout={max(5, int(request_timeout))}",
        "--workers=3",
        "--max-reqs-per-sec=8",
        "--disable-javascript",
        "--no-cache",
        "--hide-progress-bar",
        "--no-color",
        f"--output-html-report={html_path}",
        f"--output-json-file={json_path}",
        f"--output-text-file={txt_path}",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=run_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        summary = _empty_summary(
            url=site_url,
            error=f"SiteOne timed out after {run_timeout}s",
        )
        summary["available"] = True
        summary["files"] = files
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary
    except OSError as exc:
        summary = _empty_summary(url=site_url, error=f"Failed to start SiteOne: {exc}")
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    if not json_path.exists():
        err = (proc.stderr or proc.stdout or "SiteOne produced no JSON report").strip()
        summary = _empty_summary(url=site_url, error=err[:1000])
        summary["available"] = True
        summary["exit_code"] = proc.returncode
        summary["files"] = {
            k: v for k, v in files.items() if (root / v).exists()
        }
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        summary = _empty_summary(url=site_url, error=f"Invalid SiteOne JSON: {exc}")
        summary["available"] = True
        summary["files"] = files
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    if not isinstance(payload, dict):
        summary = _empty_summary(url=site_url, error="Unexpected SiteOne JSON shape")
        summary["available"] = True
        summary["files"] = files
        (root / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    summary = _summarize_json(
        payload,
        url=site_url,
        files={k: v for k, v in files.items() if (root / v).exists()},
    )
    summary["exit_code"] = proc.returncode
    # SiteOne may still emit useful scores even when some URLs timed out.
    if payload.get("error"):
        summary["warnings"] = payload.get("error")

    (root / SUMMARY_FILENAME).write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def load_siteone_summary(root: Path) -> dict | None:
    path = root / SUMMARY_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
