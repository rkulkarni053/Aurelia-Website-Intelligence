"""Annotate desktop screenshots with finding callouts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int = 18):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def annotate_screenshots(root: Path, max_per_page: int = 6) -> dict:
    findings = _load(root / "evidence" / "findings.json") or []
    browser = _load(root / "evidence" / "browser.json") or []
    out_dir = root / "screenshots" / "annotated"
    out_dir.mkdir(parents=True, exist_ok=True)

    by_url: dict[str, list] = {}
    for f in findings:
        url = f.get("url") or ""
        by_url.setdefault(url, []).append(f)

    images = []
    font = _font(18)
    small = _font(14)

    for ev in browser:
        if ev.get("error"):
            continue
        url = ev.get("final_url") or ev.get("url") or ""
        shot = (ev.get("screenshots") or {}).get("desktop")
        if not shot:
            continue
        src = root / shot
        if not src.exists():
            continue

        page_findings = by_url.get(url) or by_url.get(ev.get("url") or "") or []
        # Also include domain-level findings (ssl etc.) on first page.
        if not page_findings:
            page_findings = [f for f in findings if not f.get("url")][:max_per_page]
        page_findings = sorted(
            page_findings,
            key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f.get("severity"), 9),
        )[:max_per_page]

        img = Image.open(src).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Banner
        banner_h = 54 + max(len(page_findings), 1) * 34
        banner_h = min(banner_h, img.height // 2)
        draw.rectangle((0, 0, img.width, banner_h), fill=(11, 16, 32, 210))
        draw.text((20, 14), "Audit findings on this page", font=font, fill=(245, 247, 251, 255))

        if not page_findings:
            draw.text(
                (20, 50),
                "No page-specific findings (showing baseline screenshot).",
                font=small,
                fill=(174, 184, 210, 255),
            )
        else:
            y = 52
            colors = {
                "high": (251, 113, 133, 255),
                "medium": (251, 191, 36, 255),
                "low": (74, 222, 128, 255),
                "info": (96, 165, 250, 255),
            }
            for f in page_findings:
                sev = f.get("severity") or "info"
                color = colors.get(sev, colors["info"])
                title = (f.get("title") or f.get("code") or "Finding")[:90]
                draw.ellipse((22, y + 4, 34, y + 16), fill=color)
                draw.text(
                    (44, y),
                    f"[{sev.upper()}] {title}",
                    font=small,
                    fill=(245, 247, 251, 255),
                )
                y += 34
                if y > banner_h - 20:
                    break

        composed = Image.alpha_composite(img, overlay).convert("RGB")
        filename = Path(shot).stem + "-annotated.png"
        rel = f"screenshots/annotated/{filename}"
        composed.save(root / rel, format="PNG", optimize=True)
        images.append(
            {
                "url": url,
                "source_screenshot": shot,
                "annotated_path": rel,
                "finding_count": len(page_findings),
            }
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": images,
    }
    (root / "evidence" / "annotated_screenshots.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
