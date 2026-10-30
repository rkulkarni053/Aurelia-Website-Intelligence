"""Before/after verification report from crawl compare + score packs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.finding_clusters import cluster_summary
from backend.app.services.proposal_pdf import markdown_to_pdf

REPORT_DIR = "reports"
MARKDOWN_FILENAME = "reports/verification.md"
MANIFEST_FILENAME = "reports/verification.json"
PDF_FILENAME = "reports/verification.pdf"


def _load_pack(root: Path) -> dict:
    path = root / "evidence" / "evidence_pack.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _score_delta(before: dict | None, after: dict | None) -> dict:
    b = (before or {}).get("scores") or {}
    a = (after or {}).get("scores") or {}
    by_b = b.get("by_category") or {}
    by_a = a.get("by_category") or {}
    cats = sorted(set(by_b) | set(by_a))
    category_delta = {}
    for c in cats:
        vb = by_b.get(c)
        va = by_a.get(c)
        if vb is None or va is None:
            category_delta[c] = {"before": vb, "after": va, "delta": None}
        else:
            try:
                category_delta[c] = {
                    "before": vb,
                    "after": va,
                    "delta": round(float(va) - float(vb), 2),
                }
            except (TypeError, ValueError):
                category_delta[c] = {"before": vb, "after": va, "delta": None}
    overall_b = b.get("overall")
    overall_a = a.get("overall")
    overall_delta = None
    if overall_b is not None and overall_a is not None:
        try:
            overall_delta = round(float(overall_a) - float(overall_b), 2)
        except (TypeError, ValueError):
            overall_delta = None
    return {
        "overall_before": overall_b,
        "overall_after": overall_a,
        "overall_delta": overall_delta,
        "by_category": category_delta,
    }


def build_verification_markdown(
    *,
    domain: str,
    crawl_a: dict,
    crawl_b: dict,
    comparison: dict,
    score_delta: dict,
    resolved_cards: list,
    new_cards: list,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Verification report — before / after",
        "",
        f"**Site:** {domain}  ",
        f"**Date:** {generated}  ",
        f"**Baseline crawl:** `{crawl_a.get('id')}`  ",
        f"**Verification crawl:** `{crawl_b.get('id')}`  ",
        "",
        "---",
        "",
        "## Score movement",
        "",
    ]
    ob, oa, od = (
        score_delta.get("overall_before"),
        score_delta.get("overall_after"),
        score_delta.get("overall_delta"),
    )
    if ob is not None or oa is not None:
        delta_txt = f" ({od:+}/10)" if od is not None else ""
        lines.append(f"**Overall:** {ob if ob is not None else '—'} → {oa if oa is not None else '—'}{delta_txt}")
        lines.append("")
    by_cat = score_delta.get("by_category") or {}
    if by_cat:
        lines.append("| Category | Before | After | Delta |")
        lines.append("|---|---:|---:|---:|")
        for name, row in sorted(by_cat.items()):
            d = row.get("delta")
            dtxt = f"{d:+}" if d is not None else "—"
            lines.append(
                f"| {name} | {row.get('before') if row.get('before') is not None else '—'} | "
                f"{row.get('after') if row.get('after') is not None else '—'} | {dtxt} |"
            )
        lines.append("")

    summary = comparison.get("summary") or {}
    lines.extend(
        [
            "## Findings summary",
            "",
            f"- **Resolved:** {summary.get('resolved', 0)}",
            f"- **New:** {summary.get('new', 0)}",
            f"- **Unchanged:** {summary.get('unchanged', 0)}",
            "",
            "## What we fixed",
            "",
        ]
    )
    if resolved_cards:
        for card in resolved_cards:
            lines.append(
                f"- **{card.get('title')}** "
                f"({(card.get('severity') or '').upper()}) — {card.get('description')}"
            )
    else:
        lines.append("- No resolved findings between these crawls.")
    lines.append("")
    lines.append("## Remaining / new issues")
    lines.append("")
    if new_cards:
        for card in new_cards:
            lines.append(
                f"- **{card.get('title')}** "
                f"({(card.get('severity') or '').upper()}) — {card.get('description')}"
            )
    else:
        lines.append("- No new issues introduced.")
    lines.append("")
    lines.append("## Next recommendation")
    lines.append("")
    if summary.get("new", 0) or summary.get("unchanged", 0):
        lines.append(
            "Schedule a follow-up sprint for remaining medium/high items, "
            "or start monthly monitoring to catch regressions."
        )
    else:
        lines.append(
            "Baseline goals were met. Monthly monitoring will keep scores from drifting."
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by Aurelia verification*")
    lines.append("")
    return "\n".join(lines)


def generate_verification_report(
    root_b: Path,
    *,
    domain: str,
    crawl_a: dict,
    crawl_b: dict,
    comparison: dict,
    root_a: Path | None = None,
) -> dict[str, Any]:
    """Write verification markdown/PDF under the newer crawl root (root_b)."""
    pack_b = _load_pack(root_b)
    pack_a = _load_pack(root_a) if root_a else {}
    score_delta = _score_delta(pack_a, pack_b)

    resolved = comparison.get("resolved") or []
    new = comparison.get("new") or []
    resolved_cards = cluster_summary(resolved, max_items=12)
    new_cards = cluster_summary(new, max_items=12)

    markdown = build_verification_markdown(
        domain=domain,
        crawl_a=crawl_a,
        crawl_b=crawl_b,
        comparison=comparison,
        score_delta=score_delta,
        resolved_cards=resolved_cards,
        new_cards=new_cards,
    )

    out_dir = root_b / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = root_b / MARKDOWN_FILENAME
    md_path.write_text(markdown, encoding="utf-8")
    pdf_path = root_b / PDF_FILENAME
    markdown_to_pdf(markdown, pdf_path)

    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "crawl_a": crawl_a.get("id"),
        "crawl_b": crawl_b.get("id"),
        "summary": comparison.get("summary"),
        "score_delta": score_delta,
        "resolved": resolved_cards,
        "new": new_cards,
        "markdown_file": MARKDOWN_FILENAME,
        "pdf_file": PDF_FILENAME,
    }
    (root_b / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    manifest["markdown"] = markdown
    return manifest


def load_verification_report(root: Path) -> dict | None:
    path = root / MANIFEST_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    md = root / (data.get("markdown_file") or MARKDOWN_FILENAME)
    if md.exists():
        data["markdown"] = md.read_text(encoding="utf-8")
    return data
