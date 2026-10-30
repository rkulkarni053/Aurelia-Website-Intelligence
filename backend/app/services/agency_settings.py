"""Agency branding, packages, and proposal defaults (replaces hand-edited JSON over time)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.app.services.proposal import load_proposal_config

AGENCY_PATH = Path("config/agency.json")
PROPOSAL_PATH = Path("config/proposal.json")


def _default_from_proposal() -> dict[str, Any]:
    cfg = load_proposal_config(PROPOSAL_PATH)
    return {
        "version": 1,
        "branding": {
            "agency_name": cfg.get("company_name") or "Aurelia",
            "tagline": cfg.get("company_tagline") or "",
            "logo_path": None,
            "primary_color": "#4a3f66",
            "secondary_color": "#b08d4a",
            "font": "Inter",
            "website": "",
            "contact_email": cfg.get("contact_email") or "proposals@example.com",
            "contact_phone": "",
        },
        "proposal": {
            "introduction": "",
            "payment_terms": "50% on acceptance, 50% on launch.",
            "footer": "",
            "disclaimer": "This proposal is valid for 30 days.",
            "terms": "Work begins after written acceptance of the selected package.",
        },
        "currency": cfg.get("currency") or "EUR",
        "packages": cfg.get("packages") or {},
        "add_ons": {
            "monitoring": cfg.get("monitoring")
            or {
                "name": "Monthly monitoring",
                "price": 250,
                "summary": "Monthly re-crawl, score tracking, and findings diff report.",
            }
        },
        "out_of_scope_defaults": cfg.get("out_of_scope_defaults") or [],
        "recommended_package_default": cfg.get("recommended_package_default") or "growth",
        "methodology": (
            "Turn website problems into priced projects.\n"
            "Cluster technical noise into commercial opportunities before recommending packages.\n"
            "Lead with conversion, positioning, and trust.\n"
            "Human approves package and proposal before client send.\n"
            "Client language first — no crawl IDs, WCAG codes, or collector names."
        ),
        "agent": {
            "enabled": True,
            "use_ollama_for_advisory": True,
            # Company understanding = crawl profile (instant). Tiny model for chat polish.
            "prefer_fast_chat_model": True,
            "prefer_fast_brain_model": True,
            "profile_first_brain": True,
            "brain_timeout_seconds": 45,
        },
    }


def load_agency_settings() -> dict[str, Any]:
    if AGENCY_PATH.exists():
        try:
            data = json.loads(AGENCY_PATH.read_text(encoding="utf-8"))
            base = _default_from_proposal()
            return _deep_merge(base, data)
        except (json.JSONDecodeError, OSError):
            pass
    return _default_from_proposal()


def save_agency_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_agency_settings()
    merged = _deep_merge(current, payload or {})
    AGENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENCY_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    # Keep proposal.json in sync for existing proposal code paths.
    _sync_proposal_json(merged)
    return merged


def proposal_config_from_agency(settings: dict | None = None) -> dict[str, Any]:
    """Shape agency settings into the dict proposal.py expects."""
    s = settings or load_agency_settings()
    branding = s.get("branding") or {}
    return {
        "company_name": branding.get("agency_name") or "Aurelia",
        "company_tagline": branding.get("tagline") or "",
        "contact_email": branding.get("contact_email") or "proposals@example.com",
        "currency": s.get("currency") or "EUR",
        "packages": deepcopy(s.get("packages") or {}),
        "monitoring": deepcopy((s.get("add_ons") or {}).get("monitoring") or {}),
        "out_of_scope_defaults": list(s.get("out_of_scope_defaults") or []),
        "recommended_package_default": s.get("recommended_package_default") or "growth",
        "payment_terms": (s.get("proposal") or {}).get("payment_terms"),
        "terms": (s.get("proposal") or {}).get("terms"),
        "disclaimer": (s.get("proposal") or {}).get("disclaimer"),
        "footer": (s.get("proposal") or {}).get("footer"),
        "introduction": (s.get("proposal") or {}).get("introduction"),
        "branding": branding,
    }


def _sync_proposal_json(settings: dict) -> None:
    cfg = proposal_config_from_agency(settings)
    slim = {
        "company_name": cfg["company_name"],
        "company_tagline": cfg["company_tagline"],
        "contact_email": cfg["contact_email"],
        "currency": cfg["currency"],
        "packages": cfg["packages"],
        "monitoring": cfg["monitoring"],
        "out_of_scope_defaults": cfg["out_of_scope_defaults"],
        "recommended_package_default": cfg["recommended_package_default"],
    }
    PROPOSAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROPOSAL_PATH.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
