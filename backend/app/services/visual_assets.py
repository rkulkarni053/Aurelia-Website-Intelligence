"""Open-source visuals for demos — Unsplash photos + light 3D accents.

Brain picks a pack from design_direction.theme. Images are downloaded into
demo/media/ so the local preview stays usable offline after first build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

MEDIA_DIR = "demo/media"
MANIFEST_NAME = "assets.json"

# Curated Unsplash photos (license: Unsplash License — free commercial use).
# Direct CDN URLs; no API key. Attribution listed in each entry.
THEME_VISUALS: dict[str, dict[str, Any]] = {
    "warm_romance": {
        "query": "wedding cinema couple golden hour",
        "hero": {
            "url": "https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=1600&q=80",
            "alt": "Couple at a wedding celebration",
            "credit": "Photo by Nathan Dumlao on Unsplash",
            "credit_url": "https://unsplash.com/photos/couple-standing-on-lawn-while-people-watching-them-NZPiCYK3I0g",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1465495976277-4387d4b0b4c6?auto=format&fit=crop&w=1200&q=80",
                "alt": "Wedding rings detail",
                "credit": "Photo by Sandy Millar on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1529636798458-92182e662485?auto=format&fit=crop&w=1200&q=80",
                "alt": "Bridal portrait soft light",
                "credit": "Photo by Jonathan Borba on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1511285560929-80b456fea0bc?auto=format&fit=crop&w=1200&q=80",
                "alt": "Reception celebration",
                "credit": "Photo by Jeremy Wong on Unsplash",
            },
        ],
        "accent_3d": "rings",
    },
    "dark_cinematic": {
        "query": "broadcast camera cinema production",
        "hero": {
            "url": "https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?auto=format&fit=crop&w=1600&q=80",
            "alt": "Cinematic camera on set",
            "credit": "Photo by Jakob Owens on Unsplash",
            "credit_url": "https://unsplash.com/photos/person-holding-dslr-camera-UAvYasdkzq8",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1574717024653-61fd2cf4d44d?auto=format&fit=crop&w=1200&q=80",
                "alt": "Video production desk",
                "credit": "Photo by Avel Chuklanov on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1478720568477-152d9b164e26?auto=format&fit=crop&w=1200&q=80",
                "alt": "Film projector light",
                "credit": "Photo by Myke Simon on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1485846234645-a62644f84728?auto=format&fit=crop&w=1200&q=80",
                "alt": "Cinema production set",
                "credit": "Photo by Jakob Owens on Unsplash",
            },
        ],
        "accent_3d": "camera",
    },
    "light_editorial": {
        "query": "creative studio workspace editorial",
        "hero": {
            "url": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1600&q=80",
            "alt": "Bright creative studio",
            "credit": "Photo by Nastuh Abootalebi on Unsplash",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&w=1200&q=80",
                "alt": "Modern desk and chair",
                "credit": "Photo by Inside Weather on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1558655146-d09347e92766?auto=format&fit=crop&w=1200&q=80",
                "alt": "Design tools on desk",
                "credit": "Photo by Hal Gatewood on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&q=80",
                "alt": "Analytics on laptop",
                "credit": "Photo by Carlos Muza on Unsplash",
            },
        ],
        "accent_3d": "orb",
    },
    "clean_corporate": {
        "query": "modern office trust professional",
        "hero": {
            "url": "https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1600&q=80",
            "alt": "Clean modern office interior",
            "credit": "Photo by Nastuh Abootalebi on Unsplash",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=1200&q=80",
                "alt": "Team collaboration meeting",
                "credit": "Photo by Amy Hirschi on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1200&q=80",
                "alt": "Laptop and documents",
                "credit": "Photo by Scott Graham on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=1200&q=80",
                "alt": "Professional portrait",
                "credit": "Photo by Albert Dera on Unsplash",
            },
        ],
        "accent_3d": "orb",
    },
    "warm_hospitality": {
        "query": "restaurant dining warm ambience",
        "hero": {
            "url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1600&q=80",
            "alt": "Warm restaurant interior",
            "credit": "Photo by Jay Wennington on Unsplash",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=80",
                "alt": "Plated fine dining dish",
                "credit": "Photo by Jay Wennington on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=1200&q=80",
                "alt": "Cocktail at a bar",
                "credit": "Photo by Adam Jaime on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=1200&q=80",
                "alt": "Restaurant seating",
                "credit": "Photo by Broissin on Unsplash",
            },
        ],
        "accent_3d": "plate",
    },
    "bold_tech": {
        "query": "abstract technology gradient product",
        "hero": {
            "url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1600&q=80",
            "alt": "Earth from space technology mood",
            "credit": "Photo by NASA on Unsplash",
        },
        "supporting": [
            {
                "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
                "alt": "Circuit board close-up",
                "credit": "Photo by Michael Dziedzic on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80",
                "alt": "Cybersecurity abstract",
                "credit": "Photo by Michael Gechtman on Unsplash",
            },
            {
                "url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1200&q=80",
                "alt": "Laptop with code",
                "credit": "Photo by damiano baschiera on Unsplash",
            },
        ],
        "accent_3d": "cube",
    },
}


def select_visual_pack(theme: str | None) -> dict[str, Any]:
    key = (theme or "light_editorial").strip()
    pack = THEME_VISUALS.get(key) or THEME_VISUALS["light_editorial"]
    return {
        "theme": key if key in THEME_VISUALS else "light_editorial",
        "query": pack["query"],
        "hero": dict(pack["hero"]),
        "supporting": [dict(x) for x in pack["supporting"]],
        "accent_3d": pack["accent_3d"],
        "license": "Unsplash License",
        "source": "open_unsplash_curated",
    }


def _filename_for(url: str, role: str) -> str:
    path = urlparse(url).path
    stem = Path(path).name.split("?")[0] or role
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    ext = ".jpg"
    if "." in stem and len(stem.split(".")[-1]) <= 4:
        ext = "." + stem.split(".")[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
    return f"{role}-{digest}{ext}"


def _download(url: str, dest: Path, *, timeout: float = 25.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        return True
    for attempt in range(2):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=8.0, read=timeout, write=15.0, pool=5.0),
                follow_redirects=True,
                headers={"User-Agent": "AureliaDemo/1.0 (local open-source media cache)"},
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            if dest.is_file() and dest.stat().st_size > 1000:
                return True
        except Exception:
            if attempt == 0:
                continue
            return False
    return False


def materialize_visuals(
    root: Path,
    *,
    theme: str | None,
    visual_override: dict | None = None,
) -> dict[str, Any]:
    """Download theme visuals into demo/media and return local relative paths."""
    pack = select_visual_pack(theme)
    if isinstance(visual_override, dict):
        # Allow Brain/LLM to swap accent or keep query notes.
        if visual_override.get("accent_3d"):
            pack["accent_3d"] = str(visual_override["accent_3d"])
        if visual_override.get("query"):
            pack["query"] = str(visual_override["query"])[:120]

    media_root = root / MEDIA_DIR
    media_root.mkdir(parents=True, exist_ok=True)

    hero_meta = dict(pack["hero"])
    hero_name = _filename_for(hero_meta["url"], "hero")
    hero_path = media_root / hero_name
    hero_ok = _download(hero_meta["url"], hero_path)
    hero_local = f"media/{hero_name}" if hero_ok else None

    supporting_local: list[dict[str, Any]] = []
    for idx, item in enumerate(pack["supporting"][:3], start=1):
        name = _filename_for(item["url"], f"support-{idx}")
        dest = media_root / name
        ok = _download(item["url"], dest)
        if ok:
            supporting_local.append(
                {
                    "path": f"media/{name}",
                    "alt": item.get("alt") or f"Gallery {idx}",
                    "credit": item.get("credit") or "",
                }
            )

    credits = []
    if hero_ok and hero_meta.get("credit"):
        credits.append(hero_meta["credit"])
    for item in supporting_local:
        if item.get("credit"):
            credits.append(item["credit"])

    out = {
        "theme": pack["theme"],
        "query": pack["query"],
        "accent_3d": pack["accent_3d"],
        "license": pack["license"],
        "hero": {
            "path": hero_local,
            "alt": hero_meta.get("alt") or "Hero visual",
            "credit": hero_meta.get("credit") or "",
            "credit_url": hero_meta.get("credit_url") or "",
            "remote_url": hero_meta.get("url"),
        },
        "supporting": supporting_local,
        "credits": list(dict.fromkeys(credits)),
        "source": pack["source"],
    }
    (media_root / MANIFEST_NAME).write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    return out


def render_accent_3d(kind: str | None) -> str:
    """Lightweight open CSS/SVG 3D accents — no proprietary generators."""
    kind = (kind or "orb").lower()
    if kind == "rings":
        return """
    <div class="accent-3d accent-rings" aria-hidden="true">
      <span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>
    </div>"""
    if kind == "camera":
        return """
    <div class="accent-3d accent-camera" aria-hidden="true">
      <svg viewBox="0 0 120 80" width="140" height="94" fill="none">
        <defs>
          <linearGradient id="cam" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="var(--accent-2)"/>
            <stop offset="100%" stop-color="var(--accent)"/>
          </linearGradient>
        </defs>
        <rect x="18" y="22" width="84" height="48" rx="10" fill="url(#cam)" opacity=".9"/>
        <circle cx="60" cy="46" r="16" stroke="var(--bg)" stroke-width="5" fill="color-mix(in srgb, var(--text) 20%, transparent)"/>
        <circle cx="60" cy="46" r="7" fill="var(--bg)"/>
        <rect x="28" y="12" width="22" height="12" rx="3" fill="var(--accent-2)"/>
      </svg>
    </div>"""
    if kind == "cube":
        return """
    <div class="accent-3d accent-cube" aria-hidden="true">
      <div class="cube"><span></span><span></span><span></span></div>
    </div>"""
    if kind == "plate":
        return """
    <div class="accent-3d accent-plate" aria-hidden="true">
      <span class="plate"></span><span class="plate-inner"></span>
    </div>"""
    # default orb
    return """
    <div class="accent-3d accent-orb" aria-hidden="true">
      <span class="orb o1"></span><span class="orb o2"></span>
    </div>"""


def accent_3d_css() -> str:
    return """
    .accent-3d {
      position: absolute; pointer-events: none; z-index: 3;
      filter: drop-shadow(0 18px 40px color-mix(in srgb, var(--accent) 35%, transparent));
    }
    .hero--split .accent-3d { right: 8%; bottom: 12%; }
    .hero--cinematic .accent-3d { right: 10%; top: 18%; }
    .hero--centered .accent-3d { right: 12%; top: 16%; opacity: .85; }
    .accent-rings { width: 160px; height: 160px; }
    .accent-rings .ring {
      position: absolute; inset: 18%; border-radius: 50%;
      border: 2px solid color-mix(in srgb, var(--accent-2) 80%, transparent);
      transform: rotateX(64deg) rotateZ(12deg);
      animation: spin3d 10s linear infinite;
    }
    .accent-rings .r2 { inset: 28%; animation-duration: 14s; border-color: var(--accent); }
    .accent-rings .r3 { inset: 38%; animation-duration: 18s; opacity: .7; }
    .accent-camera { transform: rotateY(-18deg) rotateX(8deg); animation: floaty 7s ease-in-out infinite alternate; }
    .accent-cube { perspective: 480px; width: 90px; height: 90px; }
    .accent-cube .cube {
      width: 70px; height: 70px; position: relative;
      transform-style: preserve-3d; animation: spin3d 12s linear infinite;
    }
    .accent-cube .cube span {
      position: absolute; inset: 0; border-radius: 12px;
      background: linear-gradient(145deg, var(--accent), var(--accent-2));
      opacity: .85;
    }
    .accent-cube .cube span:nth-child(1) { transform: translateZ(35px); }
    .accent-cube .cube span:nth-child(2) { transform: rotateY(90deg) translateZ(35px); opacity: .55; }
    .accent-cube .cube span:nth-child(3) { transform: rotateX(90deg) translateZ(35px); opacity: .4; }
    .accent-plate { width: 150px; height: 150px; }
    .accent-plate .plate, .accent-plate .plate-inner {
      position: absolute; border-radius: 50%;
      transform: rotateX(62deg);
      box-shadow: 0 20px 40px color-mix(in srgb, #000 35%, transparent);
    }
    .accent-plate .plate {
      inset: 0; background: radial-gradient(circle at 30% 30%, var(--accent-2), var(--accent));
      animation: floaty 8s ease-in-out infinite alternate;
    }
    .accent-plate .plate-inner {
      inset: 28%; background: color-mix(in srgb, var(--bg) 40%, transparent);
    }
    .accent-orb .orb {
      position: absolute; border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, color-mix(in srgb, var(--text) 55%, transparent), var(--accent));
      animation: floaty 9s ease-in-out infinite alternate;
    }
    .accent-orb .o1 { width: 110px; height: 110px; right: 0; top: 0; opacity: .75; }
    .accent-orb .o2 { width: 64px; height: 64px; right: 70px; top: 80px; opacity: .55; animation-delay: -2s; }
    @keyframes spin3d {
      from { transform: rotateX(64deg) rotateZ(0deg); }
      to { transform: rotateX(64deg) rotateZ(360deg); }
    }
    """
