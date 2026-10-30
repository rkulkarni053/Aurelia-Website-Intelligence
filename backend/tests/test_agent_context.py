"""Generative agent context + prompts."""

from pathlib import Path

from backend.app.services.agent_context import build_agent_context, compact_opportunities
from backend.app.services.agent_prompts import brain_system_prompt, chat_advisory_system_prompt
from backend.app.services.design_chat import _extract_brand_name, _advisory_fallback
from backend.app.services.feedback_store import format_few_shot_block, load_examples


def test_compact_opportunities_skips_rejected():
    items = compact_opportunities(
        [
            {"client_title": "A", "status": "approved"},
            {"client_title": "B", "status": "rejected"},
            {"client_title": "C", "status": "new"},
        ]
    )
    assert len(items) == 2
    assert {i["client_title"] for i in items} == {"A", "C"}


def test_brain_prompt_includes_agency():
    agency = {
        "branding": {"agency_name": "Studio North", "tagline": "Sites that sell"},
        "methodology": "Lead with conversion.",
        "packages": {"growth": {"name": "Growth", "price": 3500, "summary": "UX + content"}},
        "currency": "EUR",
    }
    prompt = brain_system_prompt(agency)
    assert "Studio North" in prompt
    assert "Lead with conversion" in prompt
    assert "Growth" in prompt


def test_advisory_prompt_includes_agency():
    agency = {"branding": {"agency_name": "Pixel Co"}, "methodology": "Sell projects."}
    assert "Pixel Co" in chat_advisory_system_prompt(agency)


def test_brand_extraction_generic():
    assert "Acme Dental" in _extract_brand_name("Acme Dental | Dentist Austin", "")
    assert "Bright Solar" in _extract_brand_name("Welcome to Bright Solar", "")


def test_advisory_uses_opportunities():
    audit = {
        "website": {"domain": "example.com"},
        "site_story": {
            "business_type": "Acme Dental",
            "story": "Family dentistry in Austin",
            "audience": "local families",
            "services": ["Cleanings", "Implants"],
        },
        "scores": {"overall": 7.2},
        "findings_summary": {"top": []},
        "opportunities": [
            {
                "client_title": "Improve homepage conversion",
                "priority": "high",
                "status": "new",
            }
        ],
        "sell_recommendation": {
            "package_name": "Growth",
            "recommended_package": "growth",
            "price": 3500,
        },
        "agency": {"agency_name": "Studio North"},
    }
    out = _advisory_fallback("What should we improve first?", audit)
    assert "Improve homepage conversion" in out["assistant_message"]
    assert "Growth" in out["assistant_message"]


def test_agent_context_builds(tmp_path: Path):
    pack = {
        "website": {"domain": "example.com"},
        "scores": {"overall": 8},
        "findings": {"total": 2, "top": [{"title": "Thin content", "severity": "medium", "category": "seo", "description": "x"}]},
        "site_story": {"headlines": ["Hello"], "value_prop_candidates": ["We help businesses grow"]},
        "conversion_path": {"strength": "weak", "gaps": ["No clear CTA"]},
        "technologies": {"detections": [{"name": "WordPress"}]},
    }
    ctx = build_agent_context(
        evidence_pack=pack,
        opportunities=[{"client_title": "Clarify CTA", "status": "new", "priority": "high"}],
        agency={"branding": {"agency_name": "Test Agency"}, "packages": {}},
        include_few_shot=False,
    )
    assert ctx["role"] == "agency_generative_agent"
    assert ctx["opportunities"][0]["client_title"] == "Clarify CTA"
    assert ctx["agency"]["agency_name"] == "Test Agency"


def test_few_shot_seed_loads():
    examples = load_examples(limit=5)
    block = format_few_shot_block(examples)
    # Seed example should exist after repo setup
    assert isinstance(block, str)
