"""Implementation checklist derived from brain priority actions + findings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.finding_clusters import cluster_summary

CHECKLIST_FILENAME = "evidence/checklist.json"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def build_checklist(
    root: Path,
    *,
    recommendations: dict | None = None,
    findings: list[dict] | None = None,
) -> dict[str, Any]:
    if recommendations is None:
        recommendations = _load(root / "evidence" / "recommendations.json")
    payload = recommendations or {}
    recs = payload.get("recommendations") or payload

    if findings is None:
        findings = _load(root / "evidence" / "findings.json") or []

    existing = _load(root / CHECKLIST_FILENAME) or {}
    done_map = {
        item.get("id"): bool(item.get("done"))
        for item in (existing.get("items") or [])
        if item.get("id")
    }

    items: list[dict] = []
    for idx, action in enumerate((recs.get("priority_actions") or [])[:12]):
        item_id = f"action-{idx}-{action.get('title', 'item')[:40]}".replace(" ", "-").lower()
        items.append(
            {
                "id": item_id,
                "source": "brain",
                "title": action.get("title") or "Action",
                "category": action.get("category") or "technical",
                "impact": action.get("impact") or "medium",
                "effort": action.get("effort") or "medium",
                "why": action.get("why") or "",
                "how": action.get("how") or "",
                "done": done_map.get(item_id, False),
            }
        )

    for idx, card in enumerate(cluster_summary(findings, max_items=8)):
        item_id = f"finding-{card.get('code') or idx}"
        if any(i["id"] == item_id for i in items):
            continue
        items.append(
            {
                "id": item_id,
                "source": "finding",
                "title": card.get("title") or card.get("code"),
                "category": card.get("category") or "technical",
                "impact": card.get("severity") or "medium",
                "effort": "medium",
                "why": card.get("description") or "",
                "how": "Resolve during implementation; verify with a re-crawl.",
                "done": done_map.get(item_id, False),
            }
        )

    for idx, win in enumerate((recs.get("quick_wins") or [])[:6]):
        item_id = f"quick-{idx}"
        items.append(
            {
                "id": item_id,
                "source": "quick_win",
                "title": str(win),
                "category": "content",
                "impact": "medium",
                "effort": "low",
                "why": "Quick win from the audit brain.",
                "how": str(win),
                "done": done_map.get(item_id, False),
            }
        )

    checklist = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "done_count": sum(1 for i in items if i.get("done")),
        "items": items,
    }
    out = root / CHECKLIST_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(checklist, indent=2), encoding="utf-8")
    return checklist


def load_checklist(root: Path) -> dict | None:
    return _load(root / CHECKLIST_FILENAME)


def update_checklist_items(root: Path, updates: list[dict]) -> dict:
    """Toggle done flags by id. Rebuilds from sources if missing."""
    checklist = load_checklist(root)
    if checklist is None:
        checklist = build_checklist(root)
    by_id = {i.get("id"): i for i in checklist.get("items") or []}
    for upd in updates or []:
        item_id = upd.get("id")
        if not item_id or item_id not in by_id:
            continue
        if "done" in upd:
            by_id[item_id]["done"] = bool(upd["done"])
    checklist["items"] = list(by_id.values())
    checklist["done_count"] = sum(1 for i in checklist["items"] if i.get("done"))
    checklist["total"] = len(checklist["items"])
    checklist["updated_at"] = datetime.now(timezone.utc).isoformat()
    (root / CHECKLIST_FILENAME).write_text(
        json.dumps(checklist, indent=2), encoding="utf-8"
    )
    return checklist
