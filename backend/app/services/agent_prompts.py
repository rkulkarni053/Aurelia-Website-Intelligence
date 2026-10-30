"""Load and render agency-owned prompt playbooks for the generative agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PROMPTS_DIR = Path("config/agency/prompts")

DEFAULT_METHODOLOGY = (
    "- Turn website problems into priced projects, not SEO score reports.\n"
    "- Cluster technical noise into commercial opportunities before recommending packages.\n"
    "- Lead with conversion, positioning, and trust.\n"
    "- Agency human approves package and proposal before client send.\n"
    "- Client language first — no crawl IDs, WCAG codes, or collector names."
)


def _read(name: str, fallback: str = "") -> str:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return fallback.strip()


def methodology_text(agency: dict | None = None) -> str:
    agency = agency or {}
    custom = (agency.get("methodology") or "").strip()
    if custom:
        return custom
    return _read("methodology.default.md", DEFAULT_METHODOLOGY)


def package_positioning_text(agency: dict | None = None) -> str:
    agency = agency or {}
    packages = agency.get("packages") or {}
    if not packages:
        return "Packages are configured in Agency Settings."
    currency = (agency.get("currency") or "EUR").upper()
    symbol = "€" if currency == "EUR" else f"{currency} "
    lines = []
    for key, pkg in packages.items():
        name = pkg.get("name") or key
        price = pkg.get("price")
        summary = pkg.get("summary") or ""
        price_txt = f"{symbol}{int(price)}" if price is not None else "price TBC"
        lines.append(f"- {name} ({key}): {price_txt} — {summary}")
    return "\n".join(lines)


def render_prompt(template: str, *, agency: dict | None = None) -> str:
    agency = agency or {}
    branding = agency.get("branding") or {}
    name = branding.get("agency_name") or agency.get("company_name") or "Aurelia"
    tagline = (branding.get("tagline") or "").strip()
    tagline_line = f"Tagline: {tagline}" if tagline else ""
    # Safe substitution — methodology/package text may contain braces.
    mapping = {
        "{agency_name}": name,
        "{tagline_line}": tagline_line,
        "{methodology}": methodology_text(agency),
        "{package_positioning}": package_positioning_text(agency),
    }
    out = template
    for key, value in mapping.items():
        out = out.replace(key, value)
    # Unescape doubled braces used for JSON examples in prompt files
    out = out.replace("{{", "{").replace("}}", "}")
    return out


def brain_system_prompt(agency: dict | None = None) -> str:
    fallback = (
        "You are the senior website strategist for {agency_name}.\n"
        "Return ONLY valid JSON with site_story_summary, executive_summary, "
        "priority_actions, quick_wins, strategic_improvements, proposal_angles, "
        "content_suggestions, mockup_prompts, agent_next_steps.\n"
        "Methodology:\n{methodology}\n"
        "Packages:\n{package_positioning}\n"
    )
    raw = _read("brain.system.md", fallback)
    return render_prompt(raw, agency=agency)


def chat_advisory_system_prompt(agency: dict | None = None) -> str:
    fallback = (
        "You are the generative AI strategist for {agency_name}.\n"
        "Answer using ONLY the audit context. Plain language only.\n"
        "Methodology:\n{methodology}\n"
    )
    raw = _read("chat.advisory.system.md", fallback)
    return render_prompt(raw, agency=agency)


def chat_design_system_prompt(agency: dict | None = None) -> str:
    fallback = (
        "You are the generative design agent for {agency_name}.\n"
        "Return ONLY valid JSON with assistant_message, suggestions, "
        "design_brief_patch, regenerate_mockups.\n"
        "Methodology:\n{methodology}\n"
    )
    raw = _read("chat.design.system.md", fallback)
    return render_prompt(raw, agency=agency)


def few_shot_examples(limit: int = 3) -> list[dict[str, Any]]:
    """Load approved feedback examples for few-shot injection."""
    from backend.app.services.feedback_store import load_examples

    return load_examples(limit=limit)
