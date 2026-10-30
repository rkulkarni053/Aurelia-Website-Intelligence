"""Helpers to deepen crawl quality — page priority + rendered HTML reuse."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from backend.app.services.crawler import normalize_url


def _path_rank(url: str) -> int:
    path = (urlparse(url).path or "/").lower().rstrip("/") or "/"
    rules = (
        (0, path == "/"),
        (1, "about" in path),
        (2, "contact" in path),
        (3, path.endswith("/services") or "/services/" in path + "/"),
        (4, "portfolio" in path or "work" in path or "projects" in path),
        (5, "case-stud" in path),
        (6, "blog" in path or "news" in path),
        (7, "pricing" in path or "quote" in path),
    )
    for rank, matched in rules:
        if matched:
            return rank
    return 20


def select_browser_targets(pages: list[dict], limit: int) -> list[dict]:
    """Prefer homepage / about / contact / services over long-tail URLs."""
    ranked = sorted(
        enumerate(pages),
        key=lambda item: (_path_rank(item[1].get("url") or ""), item[0]),
    )
    chosen = [page for _, page in ranked[: max(0, limit)]]
    # Keep original discovery order among the chosen set for stable UX.
    chosen_urls = {normalize_url(p.get("url") or "") for p in chosen}
    return [p for p in pages if normalize_url(p.get("url") or "") in chosen_urls][
        :limit
    ]


def enrich_pages_with_rendered_html(
    pages: list[dict],
    root: Path,
    browser_results: list[dict],
) -> list[dict]:
    """Swap in Playwright-rendered HTML when available (critical for Next.js)."""
    by_url: dict[str, dict] = {}
    for ev in browser_results or []:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        key = normalize_url(ev.get("final_url") or ev.get("url") or "")
        if key:
            by_url[key] = ev

    enriched: list[dict] = []
    for page in pages:
        row = dict(page)
        key = normalize_url(page.get("url") or "")
        ev = by_url.get(key)
        rendered_rel = (ev or {}).get("rendered_html_file")
        if rendered_rel:
            path = root / rendered_rel
            if path.is_file():
                try:
                    html = path.read_text(encoding="utf-8")
                except OSError:
                    html = ""
                if html.strip():
                    row["html"] = html
                    row["html_source"] = "rendered"
                    enriched.append(row)
                    continue
        row.setdefault("html_source", "static")
        enriched.append(row)
    return enriched
