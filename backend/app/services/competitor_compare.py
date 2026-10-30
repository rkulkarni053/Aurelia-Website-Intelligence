"""Compare primary site vs competitor crawls on scores, findings, messaging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_pack(root: Path) -> dict:
    path = root / "evidence" / "evidence_pack.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_story(root: Path) -> dict:
    path = root / "seo" / "site_story.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_conversion(root: Path) -> dict:
    path = root / "seo" / "conversion_path.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _site_snapshot(domain: str, role: str, root: Path, crawl_id: str | None) -> dict[str, Any]:
    pack = _load_pack(root)
    story = _load_story(root)
    conversion = _load_conversion(root)
    scores = pack.get("scores") or {}
    findings = pack.get("findings") or {}
    pages = story.get("pages") or []
    home = next((p for p in pages if p.get("role") == "home"), None) or {}
    return {
        "domain": domain,
        "role": role,
        "crawl_id": crawl_id,
        "scores": {
            "overall": scores.get("overall"),
            "by_category": scores.get("by_category") or {},
        },
        "findings_total": findings.get("total"),
        "findings_by_severity": findings.get("by_severity") or {},
        "headline": ((home.get("h1") or [None])[0]) or home.get("title"),
        "ctas": (home.get("ctas") or [])[:5],
        "conversion_strength": conversion.get("strength"),
        "tech": [
            d.get("name")
            for d in ((pack.get("technologies") or {}).get("detections") or [])[:8]
            if isinstance(d, dict) and d.get("name")
        ],
    }


def compare_competitors(
    primary: dict,
    competitors: list[dict],
) -> dict[str, Any]:
    """
    primary / competitor entries:
      { domain, role, root: Path, crawl_id }
    """
    primary_snap = _site_snapshot(
        primary["domain"],
        primary.get("role") or "primary",
        Path(primary["root"]),
        primary.get("crawl_id"),
    )
    comp_snaps = [
        _site_snapshot(
            c["domain"],
            c.get("role") or "competitor",
            Path(c["root"]),
            c.get("crawl_id"),
        )
        for c in competitors
    ]

    scoreboard = []
    for snap in [primary_snap, *comp_snaps]:
        scoreboard.append(
            {
                "domain": snap["domain"],
                "role": snap["role"],
                "overall": snap["scores"].get("overall"),
                "seo": (snap["scores"].get("by_category") or {}).get("seo"),
                "performance": (snap["scores"].get("by_category") or {}).get(
                    "performance"
                ),
                "accessibility": (snap["scores"].get("by_category") or {}).get(
                    "accessibility"
                ),
                "findings_total": snap.get("findings_total"),
                "conversion_strength": snap.get("conversion_strength"),
            }
        )

    insights: list[str] = []
    p_overall = primary_snap["scores"].get("overall")
    for c in comp_snaps:
        c_overall = c["scores"].get("overall")
        if p_overall is not None and c_overall is not None:
            try:
                delta = float(p_overall) - float(c_overall)
            except (TypeError, ValueError):
                delta = None
            if delta is not None:
                if delta < -0.5:
                    insights.append(
                        f"{c['domain']} currently scores higher overall "
                        f"({c_overall}/10 vs {p_overall}/10)."
                    )
                elif delta > 0.5:
                    insights.append(
                        f"You lead {c['domain']} on overall score "
                        f"({p_overall}/10 vs {c_overall}/10)."
                    )
        if c.get("ctas") and not primary_snap.get("ctas"):
            insights.append(
                f"{c['domain']} shows clearer homepage CTAs ({', '.join(c['ctas'][:2])})."
            )
        if c.get("conversion_strength") == "strong" and primary_snap.get(
            "conversion_strength"
        ) in {"weak", "mixed", None}:
            insights.append(
                f"{c['domain']} has a clearer conversion path — use that as a redesign angle."
            )

    if not insights:
        insights.append(
            "Scores are close; differentiate with messaging clarity and conversion CTAs."
        )

    return {
        "version": 1,
        "primary": primary_snap,
        "competitors": comp_snaps,
        "scoreboard": scoreboard,
        "insights": insights[:8],
    }
