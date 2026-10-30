"""Social content ideas — posts, captions, hashtags, soundtrack references.

Rule-based from company profile / industry (works offline). LLM Brain may refine.
Music picks are mood-fit references commonly used for that industry — not live
chart scrapes (those need a Spotify/TikTok API when credits exist).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOCIAL_FILENAME = "design/social_content.json"

# Industry playbooks: pillars, hooks, hashtags, soundtrack mood references.
_INDUSTRY_SOCIAL: dict[str, dict[str, Any]] = {
    "wedding_films": {
        "platforms": ["instagram", "tiktok", "youtube", "pinterest"],
        "pillars": [
            "Behind the vows — quiet moments before the aisle",
            "Reception energy — first dance + crowd cutaways",
            "Vendor love — florist / venue micro-stories",
            "Couple testimonials — 15s emotional hooks",
        ],
        "post_ideas": [
            {
                "format": "Reel / TikTok",
                "hook": "The look before they see each other…",
                "body": "3-beat edit: prep → doors open → first reaction. End on your CTA.",
                "cta": "Enquire about your date",
            },
            {
                "format": "Carousel",
                "hook": "5 frames we always capture",
                "body": "Detail shot → walk-down → vows → kiss → dance floor. Educate buyers on craft.",
                "cta": "Save this for your wedding planning board",
            },
            {
                "format": "YouTube Short",
                "hook": "One song. One wedding. Full feeling.",
                "body": "Single-track highlight under 45s — prove cinematic pacing.",
                "cta": "Watch the full film",
            },
            {
                "format": "Story poll",
                "hook": "First dance song: classic or surprise?",
                "body": "Drive DMs; collect song preferences for future edits.",
                "cta": "DM us your song",
            },
        ],
        "hashtags": [
            "#WeddingFilms",
            "#CinematicWedding",
            "#WeddingVideographer",
            "#FirstDance",
            "#BridalInspo",
        ],
        "soundtracks": [
            {
                "title": "Beyond",
                "artist": "Leon Bridges",
                "mood": "warm, romantic, modern classic",
                "why": "Soft groove for aisle / portrait montages without overpowering vows.",
                "use_for": ["highlight film", "Instagram Reel"],
                "trend_note": "Evergreen wedding edit staple — check current Reels audio chart before posting.",
            },
            {
                "title": "Mysterious Fishes",
                "artist": "Jon Guerra (or soft indie alternative)",
                "mood": "intimate, reflective",
                "why": "Works under vow VO and quiet prep scenes.",
                "use_for": ["TikTok POV", "getting-ready cut"],
                "trend_note": "Swap for the week’s trending soft-indie Reel audio if available in your region.",
            },
            {
                "title": "Can't Help Falling in Love",
                "artist": "Cover versions (Kina Grannis / Twenty One Pilots style)",
                "mood": "timeless romance",
                "why": "Instant emotional recognition for first-dance teasers.",
                "use_for": ["first dance Reel", "YouTube Short"],
                "trend_note": "Cover variants trend cyclically — pick a current Reels-cleared cover.",
            },
            {
                "title": "Electric Feel",
                "artist": "MGMT (or edit-friendly instrumental)",
                "mood": "joyful reception energy",
                "why": "Crowd / dancing montages; keeps luxury without EDM cliché.",
                "use_for": ["reception montage"],
                "trend_note": "Pair with trending dance-floor audios when the algorithm favours uptempo.",
            },
        ],
        "caption_formulas": [
            "Moment → feeling → soft CTA",
            "Question hook → 1 craft tip → enquire link",
            "Client quote → 3 stills → book discovery call",
        ],
        "posting_cadence": "3–4 Reels/week + 2 carousels + daily Stories during peak season",
    },
    "video_production_broadcast": {
        "platforms": ["linkedin", "instagram", "youtube", "tiktok"],
        "pillars": [
            "OB / live-event proof",
            "Crew craft & kit without gear-flex spam",
            "Client outcome stories (sport, conference, launch)",
            "Process transparency — brief → broadcast",
        ],
        "post_ideas": [
            {
                "format": "LinkedIn carousel",
                "hook": "What ‘broadcast-ready’ actually means",
                "body": "5 slides: signal path, redundancy, crew roles, delivery, result metric.",
                "cta": "Start a project",
            },
            {
                "format": "Reel",
                "hook": "Stadium quiet → crowd roar in 12 seconds",
                "body": "Match-cut audio rise; show multicam discipline.",
                "cta": "See OB capability",
            },
            {
                "format": "YouTube",
                "hook": "Conference stream: before / after clarity",
                "body": "Side-by-side weak vs graded program feed.",
                "cta": "Request a quote",
            },
            {
                "format": "Case tile",
                "hook": "One launch. One crew. National delivery.",
                "body": "Single KPI (viewers / uptime) + stills.",
                "cta": "Brief the crew",
            },
        ],
        "hashtags": [
            "#OutsideBroadcast",
            "#LiveStreaming",
            "#CorporateVideo",
            "#BroadcastProduction",
            "#LiveEvents",
        ],
        "soundtracks": [
            {
                "title": "Time",
                "artist": "Hans Zimmer (trailer-safe edits / inspired instrumentals)",
                "mood": "epic, controlled power",
                "why": "Sports OB and launch films need gravity without pop lyrics fighting VO.",
                "use_for": ["showreel", "LinkedIn native video"],
                "trend_note": "Use royalty-cleared trailer beds or Epidemic-style equivalents for ads.",
            },
            {
                "title": "Nightcall",
                "artist": "Kavinsky",
                "mood": "neon, modern, tech-forward",
                "why": "Corporate / product launch cuts; memorable without wedding softness.",
                "use_for": ["Instagram Reel", "TikTok craft cut"],
                "trend_note": "Synthwave beds trend in tech/event edits — clear rights before paid boost.",
            },
            {
                "title": "The Ecstasy of Gold",
                "artist": "Ennio Morricone (or modern remix)",
                "mood": "cinematic tension → triumph",
                "why": "Classic for sports builds and finale montages.",
                "use_for": ["highlight reel finale"],
                "trend_note": "Remixes spike on Reels; prefer cleared library versions for client delivery.",
            },
        ],
        "caption_formulas": [
            "Problem on site → how the crew fixed it → outcome",
            "One still + one number + CTA",
            "Myth about live streaming → correction → book call",
        ],
        "posting_cadence": "2 LinkedIn posts/week + 2 Reels + 1 short case film/month",
    },
    "restaurant": {
        "platforms": ["instagram", "tiktok", "google", "facebook"],
        "pillars": ["Dish drops", "Room atmosphere", "Chef / team", "Reservations FOMO"],
        "post_ideas": [
            {
                "format": "Reel",
                "hook": "Tonight’s special in 8 seconds",
                "body": "Sizzle → plate → first bite reaction.",
                "cta": "Reserve a table",
            },
            {
                "format": "Carousel",
                "hook": "How we plate the signature",
                "body": "Step stills; end on booking sticker.",
                "cta": "Book tonight",
            },
        ],
        "hashtags": ["#Restaurant", "#Foodie", "#Reservations", "#ChefSpecial"],
        "soundtracks": [
            {
                "title": "La Vie en Rose",
                "artist": "Édith Piaf (or modern cover)",
                "mood": "warm hospitality classic",
                "why": "Dining atmosphere Reels; instant ‘evening out’ cue.",
                "use_for": ["ambiance Reel"],
                "trend_note": "Swap for trending bistro/jazz audios in Reels library weekly.",
            },
            {
                "title": "Electric Feel",
                "artist": "MGMT",
                "mood": "upbeat service energy",
                "why": "Kitchen pass / Friday night crowd cuts.",
                "use_for": ["service montage"],
                "trend_note": "Pair with current trending food-audio on TikTok when relevant.",
            },
        ],
        "caption_formulas": ["Sensory detail → scarce seats → reserve"],
        "posting_cadence": "5–7 short videos/week + daily Stories",
    },
    "saas": {
        "platforms": ["linkedin", "x", "youtube", "tiktok"],
        "pillars": ["Product moments", "Customer wins", "Founder POV", "Feature education"],
        "post_ideas": [
            {
                "format": "LinkedIn",
                "hook": "We deleted 4 clicks from onboarding",
                "body": "Screen recording + before/after time-to-value.",
                "cta": "Book a demo",
            },
            {
                "format": "TikTok / Reel",
                "hook": "POV: your dashboard finally makes sense",
                "body": "Fast UI tour to one aha metric.",
                "cta": "Start free",
            },
        ],
        "hashtags": ["#SaaS", "#ProductHunt", "#B2B", "#BuildInPublic"],
        "soundtracks": [
            {
                "title": "Midnight City",
                "artist": "M83",
                "mood": "optimistic tech energy",
                "why": "Product launches and roadmap films.",
                "use_for": ["launch Reel"],
                "trend_note": "Tech creators cycle synth beds — refresh from Reels trending weekly.",
            }
        ],
        "caption_formulas": ["Pain → product moment → CTA"],
        "posting_cadence": "3 LinkedIn/week + 2 short demos",
    },
    "agency": {
        "platforms": ["instagram", "linkedin", "behance", "tiktok"],
        "pillars": ["Work reveals", "Process", "Culture", "Client outcomes"],
        "post_ideas": [
            {
                "format": "Reel",
                "hook": "Brand system in 10 seconds",
                "body": "Logo → type → colour → application.",
                "cta": "Start a project",
            }
        ],
        "hashtags": ["#CreativeAgency", "#Branding", "#DesignStudio"],
        "soundtracks": [
            {
                "title": "Genesis",
                "artist": "Justice",
                "mood": "sharp, modern, studio",
                "why": "Portfolio drops and motion showreels.",
                "use_for": ["case Reel"],
                "trend_note": "Check Reels for current electronic beds before boost.",
            }
        ],
        "caption_formulas": ["Craft detail → business result → CTA"],
        "posting_cadence": "3–4 posts/week",
    },
    "services": {
        "platforms": ["instagram", "facebook", "google", "linkedin"],
        "pillars": ["Proof", "How it works", "FAQ myths", "Offers"],
        "post_ideas": [
            {
                "format": "Carousel",
                "hook": "3 things to check before you hire",
                "body": "Educate → trust → enquire.",
                "cta": "Request a quote",
            }
        ],
        "hashtags": ["#LocalBusiness", "#Services"],
        "soundtracks": [
            {
                "title": "Feel Good Inc.",
                "artist": "Gorillaz (or cleared instrumental)",
                "mood": "approachable energy",
                "why": "General service promos without sounding corporate-stiff.",
                "use_for": ["promo Reel"],
                "trend_note": "Prefer library audio for paid ads.",
            }
        ],
        "caption_formulas": ["Problem → proof → CTA"],
        "posting_cadence": "3 posts/week",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide_social_content(
    pack: dict | None = None,
    profile: dict | None = None,
    *,
    design_direction: dict | None = None,
    content_metadata: dict | None = None,
    llm_override: dict | None = None,
) -> dict[str, Any]:
    """Build social ideas + soundtrack references for this company."""
    profile = profile or {}
    industry = str(profile.get("industry") or "services")
    playbook = _INDUSTRY_SOCIAL.get(industry) or _INDUSTRY_SOCIAL["services"]

    brand = ""
    if isinstance(profile.get("brand"), dict):
        brand = str(profile["brand"].get("display_name") or "")
    if not brand:
        brand = str(
            ((pack or {}).get("site_story") or {}).get("likely_business_name")
            or "the brand"
        )

    location = str(profile.get("location") or "")
    services = [str(s) for s in (profile.get("services") or [])[:4]]
    cta = str(
        (content_metadata or {}).get("cta_primary")
        or profile.get("primary_cta")
        or "Get in touch"
    )
    theme = str(
        (design_direction or {}).get("theme_label")
        or (design_direction or {}).get("theme")
        or ""
    )

    # Localize hooks with brand / services when possible.
    ideas = []
    for raw in playbook["post_ideas"]:
        idea = dict(raw)
        if services and "{service}" not in str(idea.get("body")):
            idea["body"] = (
                f"{idea.get('body')} Tie it to {services[0]}."
                if services
                else idea.get("body")
            )
        if cta and not idea.get("cta"):
            idea["cta"] = cta
        elif cta and str(idea.get("cta") or "").lower() in {
            "learn more",
            "contact",
            "contact us",
        }:
            idea["cta"] = cta
        ideas.append(idea)

    hashtags = list(playbook["hashtags"])
    if location:
        tag = "#" + "".join(ch for ch in location.title() if ch.isalnum())
        if tag not in hashtags:
            hashtags.append(tag)
    if brand:
        compact = "#" + "".join(ch for ch in brand.title() if ch.isalnum())[:28]
        if compact not in hashtags:
            hashtags.append(compact)

    soundtracks = [dict(s) for s in playbook["soundtracks"]]
    disclaimer = (
        "Soundtrack titles are mood-fit references for this industry — verify "
        "Reels/TikTok availability and licensing before publishing. For live "
        "trending audio, refresh inside Meta/TikTok creative tools the week you post."
    )

    out = {
        "version": 1,
        "generated_at": _now(),
        "brand": brand,
        "industry": industry,
        "theme": theme or None,
        "platforms": list(playbook["platforms"]),
        "content_pillars": list(playbook["pillars"]),
        "post_ideas": ideas,
        "hashtags": hashtags[:12],
        "caption_formulas": list(playbook["caption_formulas"]),
        "posting_cadence": playbook["posting_cadence"],
        "soundtracks": soundtracks,
        "music_disclaimer": disclaimer,
        "week_plan": [
            f"Mon — {ideas[0]['format']}: {ideas[0]['hook']}" if ideas else "Mon — craft Reel",
            f"Wed — {ideas[1]['format']}: {ideas[1]['hook']}"
            if len(ideas) > 1
            else "Wed — proof carousel",
            f"Fri — {ideas[2]['format']}: {ideas[2]['hook']}"
            if len(ideas) > 2
            else "Fri — testimonial cut",
            "Daily — Stories/polls using tone_words from content metadata",
        ],
        "source": "company_profile",
    }

    if isinstance(llm_override, dict):
        for key in (
            "platforms",
            "content_pillars",
            "post_ideas",
            "hashtags",
            "caption_formulas",
            "soundtracks",
            "week_plan",
        ):
            val = llm_override.get(key)
            if isinstance(val, list) and val:
                out[key] = val
        if isinstance(llm_override.get("posting_cadence"), str):
            out["posting_cadence"] = llm_override["posting_cadence"][:160]
        out["source"] = "llm"

    return out


def write_social_content(root: Path, payload: dict) -> Path:
    path = root / SOCIAL_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_social_content(root: Path) -> dict | None:
    path = root / SOCIAL_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
