"""Generate redesign concept mockup images from brain recommendations.

Primary backend is a local Pillow renderer (no GPU, free, deterministic).
Outputs proposal-ready homepage concepts stored under crawl/mockups/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from backend.app.services.site_design import reference_screenshot_path

MOCKUPS_DIR = "mockups"
MANIFEST_FILENAME = "mockups/manifest.json"

# Dark professional palette (readable for sales decks).
COLORS = {
    "bg": (11, 16, 32),
    "panel": (17, 25, 45),
    "panel_alt": (22, 32, 56),
    "stroke": (42, 54, 84),
    "text": (245, 247, 251),
    "muted": (141, 152, 181),
    "accent": (99, 102, 241),
    "accent_2": (52, 211, 153),
    "warn": (251, 191, 36),
    "white": (255, 255, 255),
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
        if bold
        else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _rounded(draw: ImageDraw.ImageDraw, box, fill, radius: int = 18, outline=None):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _hex_to_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def _palette_from_brief(brief: dict | None) -> dict[str, tuple[int, int, int]]:
    colors = dict(COLORS)
    if not isinstance(brief, dict):
        return colors
    palette = brief.get("palette") or {}
    mapping = {
        "bg": "bg",
        "panel": "panel",
        "accent": "accent",
        "accent_2": "accent_2",
        "text": "text",
        "muted": "muted",
    }
    for key, color_key in mapping.items():
        if key in palette:
            colors[color_key] = _hex_to_rgb(palette[key], colors[color_key])
    colors["panel_alt"] = colors["panel"]
    # Keep structural tokens.
    colors["stroke"] = COLORS["stroke"]
    colors["white"] = COLORS["white"]
    colors["warn"] = COLORS["warn"]
    return colors


def _context_from_recommendations(
    recs_payload: dict | None,
    pack: dict | None,
    design_brief: dict | None = None,
) -> dict:
    recs_payload = recs_payload or {}
    pack = pack or {}
    recs = recs_payload.get("recommendations") or {}
    website = recs_payload.get("website") or pack.get("website") or {}
    scores = recs_payload.get("scores") or pack.get("scores") or {}
    brief = design_brief or {}

    domain = website.get("domain") or "your-site.com"
    company = recs_payload.get("company_profile") or recs.get("company_profile") or {}
    brand = (
        brief.get("brand_name")
        or company.get("brand")
        or domain
    )
    summary = (
        brief.get("subheadline")
        or company.get("one_liner")
        or recs.get("executive_summary")
        or f"Redesign concept for {brand} based on the latest website audit."
    )
    actions = recs.get("priority_actions") or []
    if brief.get("services"):
        actions = [
            {"title": s.get("title"), "why": s.get("body")}
            for s in brief["services"][:3]
        ]
    elif company.get("services"):
        actions = [
            {"title": s, "why": "Core service line from the crawl profile."}
            for s in (company.get("services") or [])[:3]
        ]
    prompts = []
    if brief.get("image_prompt"):
        prompts.append(brief["image_prompt"])
    prompts.extend(recs.get("mockup_prompts") or [])
    quick = recs.get("quick_wins") or []

    headline = brief.get("headline") or f"A stronger website for {brand}"
    cta = brief.get("cta") or company.get("primary_cta") or "Get started"

    return {
        "domain": domain,
        "brand": brand,
        "url": website.get("url") or f"https://{domain}",
        "summary": summary,
        "headline": headline,
        "cta": cta,
        "style_notes": brief.get("style_notes") or "",
        "colors": _palette_from_brief(brief),
        "overall": (scores.get("overall") if isinstance(scores, dict) else None),
        "by_category": (scores.get("by_category") if isinstance(scores, dict) else {})
        or {},
        "actions": actions,
        "prompts": prompts,
        "quick_wins": quick,
        "source": recs_payload.get("source") or "concept",
        "design_brief": brief,
    }


def _paste_reference_shot(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    ctx: dict,
    box: tuple[int, int, int, int],
) -> None:
    rel = ctx.get("reference_screenshot")
    root = ctx.get("crawl_root")
    if not rel or not root:
        return
    path = root / rel
    if not path.is_file():
        return
    try:
        shot = Image.open(path).convert("RGB")
        x1, y1, x2, y2 = box
        target_w = x2 - x1
        target_h = y2 - y1
        shot.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        px = x1 + (target_w - shot.width) // 2
        py = y1 + (target_h - shot.height) // 2
        img.paste(shot, (px, py))
        draw.rounded_rectangle(box, radius=16, outline=ctx["colors"]["stroke"], width=1)
    except OSError:
        return


def _draw_desktop(ctx: dict) -> Image.Image:
    w, h = 1440, 900
    c = ctx.get("colors") or COLORS
    img = Image.new("RGB", (w, h), c["bg"])
    draw = ImageDraw.Draw(img)

    title_f = _font(22, bold=True)
    brand_f = _font(28, bold=True)
    hero_f = _font(46, bold=True)
    body_f = _font(20)
    small_f = _font(16)
    tiny_f = _font(13)

    # Browser chrome
    _rounded(draw, (40, 30, w - 40, h - 30), c["panel"], radius=24)
    draw.ellipse((70, 55, 90, 75), fill=(239, 68, 68))
    draw.ellipse((104, 55, 124, 75), fill=(251, 191, 36))
    draw.ellipse((138, 55, 158, 75), fill=(74, 222, 128))
    _rounded(draw, (190, 50, w - 70, 82), c["panel_alt"], radius=10)
    draw.text((210, 56), ctx["url"], font=tiny_f, fill=c["muted"])

    # Site canvas
    canvas = (60, 110, w - 60, h - 50)
    _rounded(draw, canvas, c["bg"], radius=18)

    # Nav
    brand = ctx.get("brand") or ctx["domain"].split(".")[0].title()
    draw.text((100, 140), _truncate(str(brand), 28), font=brand_f, fill=c["text"])
    for i, label in enumerate(["Home", "Services", "About", "Contact"]):
        draw.text((980 + i * 95, 150), label, font=small_f, fill=c["muted"])
    _rounded(draw, (1280, 140, 1360, 175), c["accent"], radius=10)
    draw.text((1298, 148), _truncate(ctx.get("cta") or "Start", 8), font=tiny_f, fill=c.get("white", (255,255,255)))

    # Hero
    headline = _truncate(
        ctx.get("headline")
        or (ctx["prompts"][0] if ctx.get("prompts") else None)
        or f"A clearer, faster website for {ctx['domain']}",
        70,
    )
    y = 230
    for line in _wrap(draw, headline, hero_f, 780)[:3]:
        draw.text((100, y), line, font=hero_f, fill=c["text"])
        y += 58

    for line in _wrap(draw, _truncate(ctx["summary"], 220), body_f, 760)[:3]:
        draw.text((100, y + 10), line, font=body_f, fill=c["muted"])
        y += 28

    _rounded(draw, (100, y + 40, 310, y + 90), c["accent"], radius=12)
    draw.text((130, y + 54), _truncate(ctx.get("cta") or "Get a proposal", 18), font=small_f, fill=c.get("white", (255,255,255)))
    _rounded(
        draw,
        (330, y + 40, 520, y + 90),
        c["panel_alt"],
        radius=12,
        outline=c["stroke"],
    )
    draw.text((360, y + 54), "See audit", font=small_f, fill=c["text"])

    _paste_reference_shot(img, draw, ctx, (820, 320, 1360, 600))

    if ctx["overall"] is not None:
        _rounded(draw, (1180, 220, 1360, 300), c["panel_alt"], radius=16)
        draw.text((1200, 235), "Audit score", font=tiny_f, fill=c["muted"])
        draw.text(
            (1200, 255),
            f"{ctx['overall']}/10",
            font=_font(36, bold=True),
            fill=c["accent_2"],
        )

    # Feature cards from priority actions
    cards = ctx["actions"][:3] or [
        {"title": "Improve SEO basics", "why": "Stronger discovery and clarity."},
        {"title": "Tighten security", "why": "HTTPS and trust signals."},
        {"title": "Polish UX", "why": "Clearer structure and CTAs."},
    ]
    card_y = 620
    card_w = 400
    gap = 24
    start_x = 100
    for i, action in enumerate(cards):
        x0 = start_x + i * (card_w + gap)
        x1 = x0 + card_w
        _rounded(
            draw,
            (x0, card_y, x1, 840),
            c["panel_alt"],
            radius=16,
            outline=c["stroke"],
        )
        draw.text(
            (x0 + 24, card_y + 24),
            _truncate(action.get("title") or "Improvement", 34),
            font=title_f,
            fill=c["text"],
        )
        why = action.get("why") or action.get("how") or ""
        yy = card_y + 70
        for line in _wrap(draw, _truncate(why, 140), small_f, card_w - 48)[:4]:
            draw.text((x0 + 24, yy), line, font=small_f, fill=c["muted"])
            yy += 24

    # Footer ribbon
    draw.text(
        (100, 860),
        "Website Intelligence · redesign concept (local, free)",
        font=tiny_f,
        fill=c["muted"],
    )
    return img


def _draw_mobile(ctx: dict) -> Image.Image:
    w, h = 390, 844
    c = ctx.get("colors") or COLORS
    img = Image.new("RGB", (w, h), c["bg"])
    draw = ImageDraw.Draw(img)

    brand_f = _font(22, bold=True)
    hero_f = _font(28, bold=True)
    body_f = _font(15)
    small_f = _font(13)
    tiny_f = _font(11)

    _rounded(draw, (12, 12, w - 12, h - 12), c["panel"], radius=28)
    _rounded(draw, (24, 40, w - 24, h - 28), c["bg"], radius=22)

    draw.text((40, 60), ctx["domain"].split(".")[0].title(), font=brand_f, fill=c["text"])
    _rounded(draw, (300, 58, 350, 88), c["accent"], radius=10)
    draw.text((312, 65), "Go", font=tiny_f, fill=c["white"])

    headline = _truncate(
        (ctx["prompts"][1] if len(ctx["prompts"]) > 1 else None)
        or (ctx["prompts"][0] if ctx["prompts"] else None)
        or f"Mobile-first redesign for {ctx['domain']}",
        48,
    )
    y = 120
    for line in _wrap(draw, headline, hero_f, 300)[:4]:
        draw.text((40, y), line, font=hero_f, fill=c["text"])
        y += 34

    for line in _wrap(draw, _truncate(ctx["summary"], 160), body_f, 300)[:4]:
        draw.text((40, y + 8), line, font=body_f, fill=c["muted"])
        y += 22

    _rounded(draw, (40, y + 24, 220, y + 64), c["accent"], radius=12)
    draw.text((58, y + 36), "Request proposal", font=small_f, fill=c["white"])

    y = y + 90
    items = ctx["quick_wins"][:4] or [
        a.get("title") for a in ctx["actions"][:4]
    ]
    for item in items:
        _rounded(
            draw,
            (40, y, w - 40, y + 70),
            c["panel_alt"],
            radius=14,
            outline=c["stroke"],
        )
        draw.text(
            (58, y + 24),
            _truncate(str(item), 36),
            font=small_f,
            fill=c["text"],
        )
        y += 84

    if ctx["overall"] is not None:
        draw.text(
            (40, h - 70),
            f"Audit {ctx['overall']}/10 · concept mockup",
            font=tiny_f,
            fill=c["muted"],
        )
    return img


def _draw_board(ctx: dict) -> Image.Image:
    """One-pager concept board for proposals."""
    w, h = 1600, 1000
    c = ctx.get("colors") or COLORS
    img = Image.new("RGB", (w, h), c["bg"])
    draw = ImageDraw.Draw(img)

    h1 = _font(40, bold=True)
    h2 = _font(24, bold=True)
    body = _font(18)
    small = _font(15)
    tiny = _font(13)

    draw.text((60, 50), "Redesign concept board", font=h1, fill=c["text"])
    draw.text((60, 110), ctx["domain"], font=h2, fill=c["accent"])
    if ctx["overall"] is not None:
        draw.text(
            (1280, 60),
            f"{ctx['overall']}/10",
            font=_font(48, bold=True),
            fill=c["accent_2"],
        )
        draw.text((1280, 120), "current audit", font=tiny, fill=c["muted"])

    y = 170
    for line in _wrap(draw, _truncate(ctx["summary"], 320), body, 1480)[:4]:
        draw.text((60, y), line, font=body, fill=c["muted"])
        y += 28

    # Columns: priorities / quick wins / proposal angles from prompts
    cols = [
        (
            "Priority fixes",
            [
                a.get("title") or "Fix"
                for a in (ctx["actions"][:6] or [{"title": "Improve SEO"}])
            ],
        ),
        (
            "Quick wins",
            ctx["quick_wins"][:6] or ["Add meta description", "Improve headings"],
        ),
        (
            "Visual direction",
            ctx["prompts"][:4]
            or [
                "Clean modern homepage",
                "Strong CTA above the fold",
                "Mobile-first layout",
            ],
        ),
    ]

    col_w = 480
    top = 320
    for i, (title, items) in enumerate(cols):
        x0 = 60 + i * (col_w + 30)
        _rounded(
            draw,
            (x0, top, x0 + col_w, 920),
            c["panel"],
            radius=20,
            outline=c["stroke"],
        )
        draw.text((x0 + 28, top + 28), title, font=h2, fill=c["text"])
        yy = top + 90
        for item in items:
            _rounded(
                draw,
                (x0 + 24, yy, x0 + col_w - 24, yy + 70),
                c["panel_alt"],
                radius=12,
            )
            for line in _wrap(draw, _truncate(str(item), 70), small, col_w - 80)[:2]:
                draw.text((x0 + 40, yy + 18), line, font=small, fill=c["muted"])
                yy += 22
            yy += 40

    draw.text(
        (60, 950),
        "Generated locally by Website Intelligence · free/open-source pipeline",
        font=tiny,
        fill=c["muted"],
    )
    return img


def generate_mockups(
    root: Path,
    *,
    recommendations: dict | None = None,
    evidence_pack: dict | None = None,
    design_brief: dict | None = None,
    backend: str = "concept",
    image_model_id: str = "segmind/tiny-sd",
    image_steps: int = 8,
    image_size: int = 512,
) -> dict:
    """Create mockups into crawl/mockups and write a manifest.

    backend:
      - concept: Pillow concept boards only (default — fast, on-brand)
      - auto: try local Stable Diffusion, fall back to concept boards
      - ai: require local SD (raise on failure) — slow/fake on CPU, avoid
    """
    # Never silently burn minutes on CPU TinySD unless explicitly requested.
    if backend == "auto":
        backend = "concept"
    if recommendations is None:
        rec_path = root / "evidence" / "recommendations.json"
        if rec_path.exists():
            recommendations = json.loads(rec_path.read_text(encoding="utf-8"))

    if evidence_pack is None:
        pack_path = root / "evidence" / "evidence_pack.json"
        if pack_path.exists():
            evidence_pack = json.loads(pack_path.read_text(encoding="utf-8"))

    if design_brief is None:
        brief_path = root / "design" / "brief.json"
        if brief_path.exists():
            try:
                design_brief = json.loads(brief_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                design_brief = None

    # Prefer crawl company profile for brand/headline when Brain recs omit it.
    profile_path = root / "evidence" / "company_profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if recommendations is None:
                recommendations = {}
            if not recommendations.get("company_profile"):
                recommendations = {**recommendations, "company_profile": profile}
        except (json.JSONDecodeError, OSError):
            pass

    ctx = _context_from_recommendations(
        recommendations, evidence_pack, design_brief=design_brief
    )
    ctx["crawl_root"] = root
    ctx["reference_screenshot"] = reference_screenshot_path(root, evidence_pack)
    out_dir = root / MOCKUPS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    used_backend = "concept_pillow_v1"
    notes = (
        "Local free concept mockups rendered from audit recommendations. "
        "These are sales/design direction visuals, not production designs."
    )
    ai_error = None
    images: list[dict] = []
    prompts_used = list(ctx["prompts"] or [])

    want_ai = backend in {"auto", "ai"}
    if want_ai:
        try:
            from backend.app.services.image_gen import (
                build_website_prompt,
                diffusion_available,
                generate_ai_image,
            )

            avail = diffusion_available()
            if not avail.get("ok"):
                raise RuntimeError(avail.get("error") or "diffusers unavailable")

            ideas = prompts_used or [
                f"clean modern homepage redesign for {ctx['domain']}",
                f"mobile-first landing page for {ctx['domain']}",
            ]
            # Keep CPU generation bounded: 2 AI images + concept board.
            ai_jobs = [
                (
                    "ai-desktop-homepage.png",
                    "ai_desktop",
                    "AI redesign concept (desktop)",
                    "desktop",
                    ideas[0],
                    41,
                ),
                (
                    "ai-mobile-homepage.png",
                    "ai_mobile",
                    "AI redesign concept (mobile)",
                    "mobile",
                    ideas[1] if len(ideas) > 1 else ideas[0],
                    42,
                ),
            ]

            for filename, kind, label, viewport, idea, seed in ai_jobs:
                prompt = build_website_prompt(
                    domain=ctx["domain"],
                    idea=idea,
                    viewport=viewport,
                )
                prompts_used.append(prompt)
                image = generate_ai_image(
                    prompt,
                    model_id=image_model_id,
                    steps=image_steps,
                    width=image_size,
                    height=image_size,
                    seed=seed,
                )
                path = out_dir / filename
                image.save(path, format="PNG", optimize=True)
                images.append(
                    {
                        "kind": kind,
                        "label": label,
                        "path": f"{MOCKUPS_DIR}/{filename}",
                        "width": image.width,
                        "height": image.height,
                        "prompt": prompt,
                        "model": image_model_id,
                    }
                )

            used_backend = f"diffusers_cpu:{image_model_id}"
            notes = (
                "Free local open-source AI images (TinySD via Diffusers on CPU). "
                "Slow without a GPU; results are conceptual website visuals, "
                "not production designs."
            )
        except Exception as exc:
            ai_error = str(exc)
            images = []
            if backend == "ai":
                raise

    if not images:
        for filename, kind, label, renderer in [
            ("desktop-homepage.png", "desktop", "Homepage redesign concept (desktop)", _draw_desktop),
            ("mobile-homepage.png", "mobile", "Homepage redesign concept (mobile)", _draw_mobile),
            ("concept-board.png", "board", "Proposal concept board", _draw_board),
        ]:
            image = renderer(ctx)
            path = out_dir / filename
            image.save(path, format="PNG", optimize=True)
            images.append(
                {
                    "kind": kind,
                    "label": label,
                    "path": f"{MOCKUPS_DIR}/{filename}",
                    "width": image.width,
                    "height": image.height,
                }
            )
        used_backend = "concept_pillow_v1"
        if ai_error:
            notes = (
                "AI image generation failed or ran out of memory; "
                "showing free concept mockups instead. "
                f"AI error: {ai_error}"
            )
    else:
        board = _draw_board(ctx)
        board_path = out_dir / "concept-board.png"
        board.save(board_path, format="PNG", optimize=True)
        images.append(
            {
                "kind": "board",
                "label": "Proposal concept board",
                "path": f"{MOCKUPS_DIR}/concept-board.png",
                "width": board.width,
                "height": board.height,
            }
        )

    # Archive a timestamped copy of the latest primary mockup for chat history.
    history_dir = out_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if images:
        src = root / images[0]["path"]
        if src.exists():
            hist_name = f"{stamp}-{Path(images[0]['path']).name}"
            hist_path = history_dir / hist_name
            hist_path.write_bytes(src.read_bytes())
            images[0] = {
                **images[0],
                "history_path": f"{MOCKUPS_DIR}/history/{hist_name}",
            }

    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": used_backend,
        "notes": notes,
        "ai_error": ai_error,
        "domain": ctx["domain"],
        "prompts_used": prompts_used,
        "design_brief": design_brief or ctx.get("design_brief"),
        "images": images,
    }

    (root / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def load_mockups(root: Path) -> dict | None:
    path = root / MANIFEST_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
