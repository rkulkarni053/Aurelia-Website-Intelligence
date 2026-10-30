"""Lighthouse-like scoring.

Prefers real Lighthouse CLI when available; otherwise builds a free local
heuristic score from collected performance / a11y / SEO evidence.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _clamp_100(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _to_10(score_100: int | float | None) -> float | None:
    if score_100 is None:
        return None
    return round(float(score_100) / 10.0, 1)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _heuristic_from_evidence(root: Path, url: str) -> dict:
    perf_rows = _load(root / "evidence" / "performance.json") or []
    a11y_rows = _load(root / "evidence" / "accessibility.json") or []
    seo = _load(root / "seo" / "analysis.json") or {}
    content = _load(root / "seo" / "content.json") or {}
    findings = _load(root / "evidence" / "findings.json") or []

    # Performance from LCP
    lcp = None
    for row in perf_rows:
        if (row.get("final_url") or row.get("url")) == url or not lcp:
            perf = row.get("performance") or {}
            if isinstance(perf.get("lcp_ms"), (int, float)):
                lcp = perf["lcp_ms"]
                break
    if lcp is None:
        performance = 70
    elif lcp <= 2500:
        performance = 95
    elif lcp <= 4000:
        performance = 75
    elif lcp <= 6000:
        performance = 50
    else:
        performance = 30

    # Accessibility from axe violation counts
    violations = 0
    for row in a11y_rows:
        if (row.get("url") or row.get("final_url")) == url or violations == 0:
            violations = len(row.get("violations") or [])
    accessibility = _clamp_100(100 - violations * 8)

    # SEO from robots/sitemap + content signals + finding penalties
    seo_score = 80
    if not seo.get("sitemap_found"):
        seo_score -= 15
    robots = seo.get("robots") or {}
    if not robots.get("found"):
        seo_score -= 10
    for page in (content.get("pages") or [])[:3]:
        if page.get("thin_content"):
            seo_score -= 8
        if page.get("missing_h1"):
            seo_score -= 8
        if page.get("title_too_long") or page.get("title_too_short"):
            seo_score -= 5
    for f in findings:
        if f.get("category") == "seo" and f.get("severity") == "high":
            seo_score -= 5
    seo_score = _clamp_100(seo_score)

    # Best-practice / technical proxy
    best_practices = 85
    for f in findings:
        if f.get("category") in {"security", "technical"} and f.get("severity") in {
            "high",
            "medium",
        }:
            best_practices -= 6
    best_practices = _clamp_100(best_practices)

    categories = {
        "performance": performance,
        "accessibility": accessibility,
        "best_practices": best_practices,
        "seo": seo_score,
    }
    overall = _clamp_100(sum(categories.values()) / 4)
    return {
        "url": url,
        "source": "heuristic_v1",
        "scores": categories,
        "scores_out_of_10": {k: _to_10(v) for k, v in categories.items()},
        "overall": overall,
        "overall_out_of_10": _to_10(overall),
        "lcp_ms": lcp,
        "error": None,
    }


def _run_lighthouse_cli(url: str, out_json: Path) -> dict | None:
    binary = shutil.which("lighthouse")
    cmd = None
    if binary:
        cmd = [
            binary,
            url,
            "--quiet",
            "--chrome-flags=--headless --no-sandbox --disable-gpu",
            "--output=json",
            f"--output-path={out_json}",
            "--only-categories=performance,accessibility,best-practices,seo",
        ]
    elif shutil.which("npx"):
        cmd = [
            "npx",
            "--yes",
            "lighthouse@12",
            url,
            "--quiet",
            "--chrome-flags=--headless --no-sandbox --disable-gpu",
            "--output=json",
            f"--output-path={out_json}",
            "--only-categories=performance,accessibility,best-practices,seo",
        ]
    if not cmd:
        return None

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if not out_json.exists():
        return {
            "url": url,
            "source": "lighthouse_cli",
            "error": proc.stderr[-500:] if proc.stderr else "lighthouse produced no output",
        }

    raw = json.loads(out_json.read_text(encoding="utf-8"))
    cats = raw.get("categories") or {}
    scores = {}
    for key, alias in [
        ("performance", "performance"),
        ("accessibility", "accessibility"),
        ("best-practices", "best_practices"),
        ("seo", "seo"),
    ]:
        val = (cats.get(key) or {}).get("score")
        scores[alias] = _clamp_100((val or 0) * 100) if val is not None else None

    present = [v for v in scores.values() if v is not None]
    overall = _clamp_100(sum(present) / len(present)) if present else None
    return {
        "url": url,
        "source": "lighthouse_cli",
        "scores": scores,
        "scores_out_of_10": {k: _to_10(v) for k, v in scores.items()},
        "overall": overall,
        "overall_out_of_10": _to_10(overall),
        "raw_report_file": str(out_json.name),
        "error": None,
    }


def collect_lighthouse(root: Path, urls: list[str], prefer_cli: bool = True) -> dict:
    out_dir = root / "lighthouse"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for i, url in enumerate(urls[:10]):
        report = None
        if prefer_cli:
            report_path = out_dir / f"page-{i + 1}.json"
            report = _run_lighthouse_cli(url, report_path)
        if not report or report.get("error") or report.get("source") != "lighthouse_cli":
            # Always ensure a usable score.
            report = _heuristic_from_evidence(root, url)
            report["fallback_note"] = (
                "Lighthouse CLI unavailable or failed; used local heuristic scores."
            )
        pages.append(report)

    # Aggregate
    overalls = [p.get("overall") for p in pages if p.get("overall") is not None]
    summary_scores = {"performance": [], "accessibility": [], "best_practices": [], "seo": []}
    for page in pages:
        for key in summary_scores:
            val = (page.get("scores") or {}).get(key)
            if val is not None:
                summary_scores[key].append(val)

    aggregated = {
        key: _clamp_100(sum(vals) / len(vals)) if vals else None
        for key, vals in summary_scores.items()
    }
    overall = _clamp_100(sum(overalls) / len(overalls)) if overalls else None

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": pages[0].get("source") if pages else "none",
        "pages": pages,
        "aggregate": {
            "scores": aggregated,
            "scores_out_of_10": {k: _to_10(v) for k, v in aggregated.items()},
            "overall": overall,
            "overall_out_of_10": _to_10(overall),
        },
    }
