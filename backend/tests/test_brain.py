from backend.app.services.brain import (
    normalize_recommendations,
    rule_based_recommendations,
    shrink_pack_for_prompt,
)
from backend.app.services.feedback_store import enrich_recommendations_from_examples
from backend.app.services.site_story import collect_site_story, extract_page_story


def test_site_story_extracts_about_and_home():
    home_html = """
    <html><head>
      <title>Acme Solar | Clean Energy</title>
      <meta name="description" content="Acme helps homeowners cut power bills with rooftop solar.">
    </head><body>
      <h1>Power your home with clean solar</h1>
      <h2>Installed in 14 days</h2>
      <p>We design and install residential solar systems across the region.
      Families save money while reducing carbon emissions. Get a free quote today.</p>
      <a href="/contact">Get a free quote</a>
    </body></html>
    """
    about_html = """
    <html><head><title>About Acme Solar</title></head>
    <body><h1>Our story</h1>
    <p>Founded by engineers, Acme Solar makes rooftop installs simple for busy homeowners.</p>
    </body></html>
    """
    story = collect_site_story(
        [
            {"url": "https://acme.example/", "html": home_html},
            {"url": "https://acme.example/about", "html": about_html},
        ]
    )
    assert story["home_present"] is True
    assert story["about_present"] is True
    assert "solar" in (story["value_prop_candidates"][0] or "").lower()
    assert any(p["role"] == "home" for p in story["pages"])
    page = extract_page_story("https://acme.example/", home_html)
    assert "Get a free quote" in page["ctas"]


def test_rule_based_includes_site_story_summary():
    pack = {
        "website": {"domain": "acme.example", "url": "https://acme.example"},
        "scores": {
            "overall": 7.5,
            "by_category": {"seo": 6.0, "security": 8.0},
        },
        "site_story": {
            "likely_business_name": "Acme Solar",
            "headlines": ["Power your home with clean solar"],
            "value_prop_candidates": [
                "Acme helps homeowners cut power bills with rooftop solar."
            ],
            "about_present": True,
            "home_present": True,
            "pages": [
                {
                    "role": "home",
                    "body_excerpt": "We design and install residential solar systems.",
                }
            ],
        },
        "findings": {
            "top": [
                {
                    "code": "missing_meta_description",
                    "severity": "medium",
                    "category": "seo",
                    "title": "Missing meta description",
                    "description": "No meta description",
                    "url": "https://acme.example/",
                }
            ]
        },
    }

    rec = rule_based_recommendations(pack)
    assert rec["site_story_summary"]["story"]
    assert "solar" in rec["site_story_summary"]["story"].lower()
    assert "acme" in rec["executive_summary"].lower()


def test_normalize_and_shrink_includes_story():
    pack = {
        "site_story": {
            "likely_business_name": "Acme",
            "headlines": ["Hello"],
            "pages": [
                {
                    "url": "https://acme.example/",
                    "role": "home",
                    "title": "Acme",
                    "h1": ["Welcome"],
                    "body_excerpt": "x" * 900,
                    "ctas": ["Contact"],
                }
            ],
        },
        "findings": {
            "total": 1,
            "top": [
                {
                    "code": "x",
                    "title": "t",
                    "detail": {"sample": [1, 2, 3]},
                }
            ],
        },
        "technologies": {
            "detections": [{"name": f"t{i}"} for i in range(20)]
        },
        "scores": {"overall": 8},
    }
    compact = shrink_pack_for_prompt(pack)
    assert "detail" not in compact["findings"]["top"][0]
    assert len(compact["technologies"]["detections"]) == 15
    assert compact["site_story"]["likely_business_name"] == "Acme"
    assert len(compact["site_story"]["pages"][0]["body_excerpt"]) <= 700

    raw = {
        "executive_summary": "Hello",
        "site_story_summary": {
            "business_type": "Solar installer",
            "story": "Helps homeowners go solar.",
            "gaps": "thin about page",
        },
        "priority_actions": [
            {"title": "Fix SSL", "impact": "high", "effort": "low"}
        ],
        "quick_wins": "single",
    }
    norm = normalize_recommendations(raw)
    assert norm["quick_wins"] == ["single"]
    assert norm["site_story_summary"]["business_type"] == "Solar installer"
    assert norm["site_story_summary"]["gaps"] == ["thin about page"]
    assert norm["priority_actions"][0]["category"] == "technical"


def test_social_content_includes_soundtracks():
    from backend.app.services.social_content import decide_social_content

    social = decide_social_content(
        {"website": {"domain": "www.exclusiveweddingfilms.com"}},
        {
            "industry": "wedding_films",
            "brand": {"display_name": "Exclusive Wedding Films"},
            "location": "Malta",
            "services": ["Wedding films"],
            "primary_cta": "Enquire about your date",
        },
        content_metadata={"cta_primary": "Enquire about your date"},
    )
    assert social["post_ideas"]
    assert social["soundtracks"]
    assert social["soundtracks"][0]["title"]
    assert "instagram" in social["platforms"]
    assert social["music_disclaimer"]


def test_content_metadata_best_words():
    from backend.app.services.content_metadata import decide_content_metadata

    meta = decide_content_metadata(
        {
            "website": {"domain": "www.exclusiveweddingfilms.com"},
            "site_story": {
                "likely_business_name": "Exclusive Wedding Films",
                "value_prop_candidates": ["Cinematic wedding films in Malta"],
            },
        },
        {
            "industry": "wedding_films",
            "brand": {"display_name": "Exclusive Wedding Films"},
            "location": "Malta",
            "services": ["Wedding films", "Engagement stories"],
            "primary_cta": "Enquire about your date",
            "one_liner": "Cinematic wedding films for couples across Malta.",
        },
        content_suggestions=[
            {
                "area": "Hero headline",
                "suggested": "Your day, filmed like a love story.",
            }
        ],
    )
    assert "Exclusive Wedding Films" in meta["page_title"]
    assert meta["primary_keywords"]
    assert meta["cta_primary"]
    assert "romantic" in meta["tone_words"] or "cinematic" in meta["tone_words"]
    assert meta["h1"]
    assert len(meta["meta_description"]) <= 155


def test_design_direction_differs_by_industry():
    from backend.app.services.design_direction import decide_design_direction

    wedding = decide_design_direction(
        {
            "site_story": {
                "likely_business_name": "Exclusive Wedding Films",
                "headlines": ["Wedding Films Malta"],
                "value_prop_candidates": ["Cinematic wedding films for couples"],
            }
        },
        {
            "industry": "wedding_films",
            "industry_label": "Wedding films",
            "brand": {"display_name": "Exclusive Wedding Films"},
            "services": ["Wedding films", "Engagement stories"],
        },
    )
    broadcast = decide_design_direction(
        {
            "site_story": {
                "likely_business_name": "EVP Malta",
                "headlines": ["Outside Broadcasting"],
                "value_prop_candidates": ["Live streaming and OB"],
            }
        },
        {
            "industry": "video_production_broadcast",
            "industry_label": "Video production",
            "brand": {"display_name": "EVP Malta"},
            "services": ["Outside Broadcasting", "Live Streaming"],
        },
    )
    assert wedding["theme"] == "warm_romance"
    assert wedding["hero_variant"] == "split"
    assert broadcast["theme"] == "dark_cinematic"
    assert wedding["theme"] != broadcast["theme"]


def test_rule_based_prefers_story_over_strong_score_themes():
    """High perf/a11y scores must not crowd out commercial messaging actions."""
    pack = {
        "website": {"domain": "evp.example", "url": "https://evp.example"},
        "scores": {
            "overall": 8.5,
            "by_category": {
                "seo": 8.0,
                "performance": 9.5,
                "accessibility": 9.0,
                "security": 8.0,
                "technical": 6.9,
            },
        },
        "site_story": {
            "likely_business_name": "EVP Malta",
            "headlines": ["Video Production Malta | EVP"],
            "calls_to_action": ["Contact"],
            "value_prop_candidates": [
                "EVP Malta is Malta's video production and live broadcast studio."
            ],
            "pages": [
                {
                    "role": "home",
                    "title": "Video Production Malta | EVP – Live Broadcast",
                    "h1": ["Video Production Malta | EVP"],
                    "body_excerpt": "Outside broadcast and live streaming.",
                }
            ],
        },
        "findings": {"top": []},
        "performance": {"pages": []},
        "conversion_path": {"gaps": []},
    }
    profile = {
        "brand": {"display_name": "EVP Malta"},
        "industry": "video_production_broadcast",
        "industry_label": "Video production & live broadcast",
        "location": "Malta and Gozo",
        "services": ["Outside Broadcasting", "Live Streaming", "Corporate Video"],
        "use_cases": ["Sports and stadium coverage", "Concerts and live events"],
        "proof_points": ["Over 20 years", "Up to 8K"],
        "primary_cta": "Start a project",
        "one_liner": "EVP Malta is Malta's video production and live broadcast studio.",
        "usecase_summary": "Prospects use the site to understand capability and start a project.",
        "story_for_brain": {
            "business_type": "Video production / broadcast agency",
            "audience": "Brands and event organisers",
            "story": "EVP Malta is Malta's video production and live broadcast studio.",
            "offer": "Outside Broadcasting, Live Streaming, Corporate Video",
            "tone": "professional",
            "gaps": [],
        },
    }
    opportunities = [
        {
            "client_title": "Make the website feel faster, especially on mobile",
            "theme_key": "performance",
            "category": "performance",
            "priority": "high",
            "business_impact": "Slow first paint.",
            "recommendation": "Optimize hero media.",
            "status": "proposed",
        },
        {
            "client_title": "Improve accessibility and readability across the website",
            "theme_key": "accessibility",
            "category": "accessibility",
            "priority": "high",
            "business_impact": "Hard to read.",
            "recommendation": "Fix contrast.",
            "status": "proposed",
        },
        {
            "client_title": "Clean up technical quality issues affecting reliability",
            "theme_key": "technical",
            "category": "technical",
            "priority": "medium",
            "business_impact": "Technical debt.",
            "recommendation": "Address technical issues.",
            "status": "proposed",
        },
    ]

    rec = rule_based_recommendations(pack, opportunities=opportunities, profile=profile)
    titles = [a["title"].lower() for a in rec["priority_actions"]]

    assert any("benefit" in t or "seo" in t for t in titles)
    assert any("service" in t or "buyer" in t or "job" in t for t in titles)
    assert not any("feel faster" in t for t in titles[:3])
    assert "overall score is" not in rec["executive_summary"].lower()
    assert "commercial gap" in rec["executive_summary"].lower()

    enriched = enrich_recommendations_from_examples(
        rec, industry="video_production_broadcast"
    )
    enriched_titles = [
        a["title"].lower() for a in enriched.get("priority_actions") or []
    ]
    assert enriched_titles
    assert not any("feel faster" in t for t in enriched_titles[:2])
