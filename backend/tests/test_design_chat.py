from pathlib import Path

from backend.app.services.design_chat import (
    merge_brief,
    process_chat_message,
    _advisory_fallback,
    _rule_based_turn,
)
from backend.app.services.mockups import generate_mockups


AUDIT = {
    "website": {"domain": "evp.example"},
    "scores": {"overall": 8.0},
    "site_story": {
        "business_type": "Video production / broadcast agency",
        "audience": "Corporate and broadcast clients",
        "story": (
            "Exclusive Video Productions: outside broadcasting, live streaming, "
            "corporate video in Malta and Gozo."
        ),
        "offer": "Outside broadcasting & live streaming",
        "gaps": ["Homepage CTA is weak"],
    },
    "findings_summary": {
        "top": [
            {
                "severity": "high",
                "category": "accessibility",
                "title": "Elements must meet minimum color contrast ratio thresholds",
            }
        ]
    },
    "priority_actions": [],
    "quick_wins": [],
    "executive_summary": "",
}


def test_rule_based_color_and_cta():
    brief = {
        "palette": {"accent": "#6366f1", "bg": "#0b1020"},
        "headline": "Old",
        "cta": "Start",
    }
    turn = _rule_based_turn("make accent navy and CTA: Book a demo", brief)
    assert turn["regenerate_mockups"] is True
    assert turn["design_brief_patch"]["palette"]["accent"] == "#0b1f3a"
    assert turn["design_brief_patch"]["cta"].lower().startswith("book")


def test_advisory_answers_differ_by_question():
    about = _advisory_fallback("What is this website about?", AUDIT)
    improve = _advisory_fallback("What should we improve first?", AUDIT)
    assert "Exclusive Video Productions" in about["assistant_message"]
    assert "Start with messaging" in improve["assistant_message"]
    assert about["assistant_message"] != improve["assistant_message"]
    assert "appears to be a local business" not in about["assistant_message"]


def test_process_chat_advisory_without_llm(tmp_path: Path):
    root = tmp_path
    (root / "evidence").mkdir()
    result = process_chat_message(
        root,
        "What is this website about?",
        recommendations={
            "website": {"domain": "evp.example"},
            "recommendations": {
                "executive_summary": "",
                "site_story_summary": AUDIT["site_story"],
                "priority_actions": [],
                "quick_wins": [],
            },
            "scores": {"overall": 8.0},
        },
        evidence_pack={
            "website": {"domain": "evp.example"},
            "scores": {"overall": 8.0},
            "findings": {"top": AUDIT["findings_summary"]["top"]},
        },
        prefer_ollama=False,
    )
    assert "Exclusive Video Productions" in result["assistant_message"]
    assert result["source"] == "rule_based"
    assert result["regenerate_mockups"] is False


def test_process_chat_persists_and_mockups_use_brief(tmp_path: Path):
    root = tmp_path
    (root / "evidence").mkdir()
    result = process_chat_message(
        root,
        "make accent gold",
        recommendations={
            "website": {"domain": "acme.example"},
            "recommendations": {
                "executive_summary": "Solar company site",
                "site_story_summary": {
                    "story": "Rooftop solar for homeowners",
                    "offer": "Free solar quote",
                },
                "mockup_prompts": ["solar homepage"],
                "priority_actions": [],
            },
            "scores": {"overall": 7},
        },
        prefer_ollama=False,
    )
    assert result["design_brief"]["palette"]["accent"] == "#f59e0b"
    assert (root / "design" / "brief.json").exists()
    assert (root / "design" / "chat.json").exists()
    assert result["regenerate_mockups"] is True

    merged = merge_brief(result["design_brief"], {"headline": "Go solar"})
    assert merged["headline"] == "Go solar"

    manifest = generate_mockups(
        root,
        recommendations={
            "website": {"domain": "acme.example"},
            "recommendations": {
                "executive_summary": "Solar",
                "priority_actions": [],
                "mockup_prompts": [],
            },
            "scores": {"overall": 7},
        },
        design_brief=result["design_brief"],
        backend="concept",
    )
    assert manifest["images"]
    assert (root / manifest["images"][0]["path"]).exists()
