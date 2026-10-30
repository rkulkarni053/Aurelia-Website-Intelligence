"""Build a business proposal from crawl evidence + recommendations + mockups."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROPOSAL_DIR = "proposal"
MARKDOWN_FILENAME = "proposal/proposal.md"
MANIFEST_FILENAME = "proposal/proposal.json"
DEFAULT_CONFIG_PATH = Path("config/proposal.json")
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


class ProposalError(RuntimeError):
    pass


def load_proposal_config(path: Path | None = None) -> dict:
    config_path = path or DEFAULT_CONFIG_PATH
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "company_name": "Aurelia",
            "company_tagline": "Audit, improve, and prove website performance",
            "contact_email": "proposals@example.com",
            "currency": "EUR",
            "packages": {},
            "monitoring": {},
            "out_of_scope_defaults": [],
            "recommended_package_default": "growth",
        }


def _money(amount: Any, currency: str = "EUR") -> str:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    code = (currency or "EUR").upper()
    if code == "EUR":
        return f"€{value:,.0f}"
    if code == "USD":
        return f"${value:,.0f}"
    return f"{value:,.0f} {code}"


def _weakest_categories(scores: dict) -> list[tuple[str, float]]:
    by_cat = (scores or {}).get("by_category") or {}
    return sorted(by_cat.items(), key=lambda kv: kv[1])[:3]


def _recommend_package(scores: dict, findings_total: int, config: dict) -> str:
    """Deprecated finding-count path — kept only as last-resort fallback."""
    del findings_total  # never use raw finding counts for commercial decisions
    default = config.get("recommended_package_default") or "growth"
    overall = (scores or {}).get("overall")
    if overall is None:
        return default
    if overall < 6:
        return "redesign" if "redesign" in (config.get("packages") or {}) else default
    if overall < 8:
        return "growth" if "growth" in (config.get("packages") or {}) else default
    return "essentials" if "essentials" in (config.get("packages") or {}) else default


def build_scoped_packages(
    config: dict,
    findings: list,
    recommendations: dict,
    opportunities: list | None = None,
) -> dict:
    """Merge static package includes with selected Opportunities (preferred)."""
    packages = {k: dict(v) for k, v in (config.get("packages") or {}).items()}

    selected = []
    if opportunities:
        from backend.app.services.opportunities import selected_for_proposal

        selected = selected_for_proposal(opportunities)
        if not selected:
            selected = [
                o
                for o in opportunities
                if (o.get("status") or "").lower() not in {"rejected", "deferred"}
            ]

    extras_by_pkg: dict[str, list[str]] = {k: [] for k in packages} or {
        "essentials": [],
        "growth": [],
        "redesign": [],
    }
    if not extras_by_pkg:
        extras_by_pkg = {"essentials": [], "growth": [], "redesign": []}

    if selected:
        order = ["essentials", "growth", "redesign"]
        for opp in selected:
            line = opp.get("client_title") or opp.get("title") or "Scoped improvement"
            rec = (opp.get("recommendation") or "").strip()
            bullet = f"{line}" + (f" — {rec}" if rec else "")
            pkg_hint = (opp.get("selected_package") or "growth").lower()
            start = order.index(pkg_hint) if pkg_hint in order else 1
            for key in order[start:]:
                extras_by_pkg.setdefault(key, [])
                if bullet not in extras_by_pkg[key]:
                    extras_by_pkg[key].append(bullet)
    else:
        # Fallback: clustered client titles (never raw axe duplicates)
        from backend.app.services.finding_clusters import cluster_summary

        cards = cluster_summary(findings, max_items=8)
        for card in cards:
            title = card.get("title") or "Improvement"
            line = f"{title}"
            for key in extras_by_pkg:
                extras_by_pkg[key].append(line)

    for key, pkg in packages.items():
        base = list(pkg.get("includes") or [])
        extras = extras_by_pkg.get(key) or []
        seen: set[str] = set()
        merged = []
        for item in base + extras:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        pkg["includes"] = merged
        pkg["scoped_from_opportunities"] = bool(selected)
        pkg["scoped_from_audit"] = not bool(selected)
    return packages


def _rule_narratives(
    domain: str,
    scores: dict,
    recs: dict,
    findings: list,
    opportunities: list | None = None,
) -> dict:
    overall = scores.get("overall")
    selected = []
    if opportunities:
        from backend.app.services.opportunities import selected_for_proposal

        selected = selected_for_proposal(opportunities) or [
            o
            for o in opportunities
            if (o.get("status") or "").lower() not in {"rejected", "deferred"}
        ]
    if selected:
        titles = [o.get("client_title") or o.get("title") for o in selected[:4]]
        summary = (
            f"We reviewed {domain} and identified {len(selected)} commercial opportunities "
            f"that affect how the website builds trust, explains the offer, and converts visitors. "
            f"Priority areas include: {', '.join(t for t in titles if t)}."
        )
        opportunity = (
            "These are not isolated technical tickets. Together they indicate where a focused "
            "website engagement will improve clarity, usability, and enquiry quality."
        )
        return {
            "executive_summary": summary,
            "opportunity": opportunity,
            "closing": (
                "Approve the recommended package to begin. We will deliver the agreed scope, "
                "then re-crawl to show measurable before/after improvement."
            ),
        }

    weak = _weakest_categories(scores)
    weak_txt = (
        ", ".join(f"{name} ({score}/10)" for name, score in weak)
        if weak
        else "key technical areas"
    )
    top = findings[:3]
    risks = [
        f.get("title") or f.get("code") or "Unresolved issue"
        for f in top
    ]
    summary = recs.get("executive_summary") or (
        f"{domain} currently scores {overall}/10 in our audit. "
        f"The weakest areas are {weak_txt}."
    )
    opportunity = (
        f"Addressing {weak_txt} can improve trust, discoverability, and conversion. "
        f"Priority risks include: {', '.join(risks) or 'the findings listed below'}."
    )
    return {
        "executive_summary": summary,
        "opportunity": opportunity,
        "closing": (
            "Approve a package to begin. We will implement the agreed scope, "
            "then re-crawl to show before/after improvement."
        ),
    }


def _ollama_narratives(
    *,
    domain: str,
    scores: dict,
    recs: dict,
    findings: list,
    model: str | None = None,
    base_url: str | None = None,
    provider: str | None = None,
) -> dict:
    from backend.app.services.llm_client import LLMError, chat_json

    compact = {
        "domain": domain,
        "scores": scores,
        "executive_summary": recs.get("executive_summary"),
        "priority_actions": (recs.get("priority_actions") or [])[:6],
        "proposal_angles": (recs.get("proposal_angles") or [])[:4],
        "top_findings": [
            {
                "title": f.get("title"),
                "severity": f.get("severity"),
                "category": f.get("category"),
            }
            for f in findings[:8]
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You write concise website improvement business proposals. "
                "Return ONLY JSON with keys: executive_summary, opportunity, closing. "
                "Each value is 2-4 sentences, business-owner friendly, no prices."
            ),
        },
        {
            "role": "user",
            "content": (
                "Write proposal narrative sections for this audit context:\n"
                + json.dumps(compact)
            ),
        },
    ]
    try:
        parsed, _provider, _model = chat_json(
            messages,
            provider=provider,
            model=model,
            temperature=0.3,
            max_tokens=900,
        )
    except LLMError as exc:
        raise ProposalError(str(exc)) from exc
    return {
        "executive_summary": str(parsed.get("executive_summary") or "").strip(),
        "opportunity": str(parsed.get("opportunity") or "").strip(),
        "closing": str(parsed.get("closing") or "").strip(),
    }


def build_proposal_markdown(
    *,
    config: dict,
    website: dict,
    crawl: dict,
    scores: dict,
    findings: list,
    recommendations: dict,
    mockups: dict | None,
    narratives: dict,
    recommended_package_key: str,
    packages_override: dict | None = None,
    opportunities: list | None = None,
    sell_why: list | None = None,
    client_mode: bool = True,
) -> str:
    """Compile a client-safe proposal from Opportunities → package → price."""
    del findings  # proposals must not dump raw findings
    domain = website.get("domain") or "website"
    url = website.get("url") or f"https://{domain}"
    company = config.get("company_name") or "Aurelia"
    tagline = config.get("company_tagline") or ""
    currency = config.get("currency") or "EUR"
    packages = packages_override or build_scoped_packages(
        config, [], recommendations, opportunities=opportunities
    )
    monitoring = config.get("monitoring") or {}
    out_of_scope = config.get("out_of_scope_defaults") or []
    rec_pkg = packages.get(recommended_package_key) or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from backend.app.services.opportunities import selected_for_proposal

    selected = selected_for_proposal(opportunities or [])
    if not selected and opportunities:
        selected = [
            o
            for o in opportunities
            if (o.get("status") or "").lower() not in {"rejected", "deferred"}
        ]

    lines: list[str] = []
    lines.append("# Website Improvement Proposal")
    lines.append("")
    lines.append(f"**Prepared by:** {company}  ")
    if tagline:
        lines.append(f"**Focus:** {tagline}  ")
    lines.append(f"**Client site:** [{domain}]({url})  ")
    lines.append(f"**Date:** {generated}  ")
    lines.append("")
    if config.get("introduction"):
        lines.append(str(config["introduction"]))
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(narratives.get("executive_summary") or "")
    lines.append("")
    lines.append(
        f"**Recommended engagement:** {rec_pkg.get('name') or recommended_package_key} — "
        f"{_money(rec_pkg.get('price'), currency)}"
        + (
            f" (~{rec_pkg.get('duration_days')} days)"
            if rec_pkg.get("duration_days")
            else ""
        )
        + "."
    )
    lines.append("")

    lines.append("## 2. Current website")
    lines.append("")
    lines.append(narratives.get("opportunity") or "")
    lines.append("")

    lines.append("## 3. Key opportunities")
    lines.append("")
    if selected:
        for opp in selected[:10]:
            title = opp.get("client_title") or opp.get("title")
            problem = opp.get("problem") or ""
            impact = opp.get("business_impact") or ""
            lines.append(f"### {title}")
            lines.append("")
            if problem:
                lines.append(problem)
                lines.append("")
            if impact:
                lines.append(f"**Why it matters:** {impact}")
                lines.append("")
            if opp.get("recommendation"):
                lines.append(f"**Recommended action:** {opp['recommendation']}")
                lines.append("")
    else:
        lines.append("_Approve opportunities in Aurelia to populate this section._")
        lines.append("")

    lines.append("## 4. Recommended direction")
    lines.append("")
    lines.append(
        f"We recommend the **{rec_pkg.get('name') or recommended_package_key}** package "
        f"({_money(rec_pkg.get('price'), currency)})."
    )
    lines.append("")
    why = sell_why or []
    if why:
        lines.append("**Why this package**")
        lines.append("")
        for item in why[:8]:
            lines.append(f"- {item}")
        lines.append("")
    angles = recommendations.get("proposal_angles") or []
    if angles and not client_mode:
        lines.append("### Internal angles")
        lines.append("")
        for angle in angles[:5]:
            lines.append(f"- {angle}")
        lines.append("")

    images = (mockups or {}).get("images") or []
    if images:
        lines.append("## 5. Visual direction")
        lines.append("")
        lines.append(
            "The following concepts illustrate a stronger direction. "
            "They are directional, not final production designs."
        )
        lines.append("")
        for img in images:
            label = img.get("label") or img.get("kind") or "Concept"
            path = img.get("path") or ""
            lines.append(f"- **{label}:** `{path}`")
        lines.append("")
        scope_n = 6
    else:
        scope_n = 5

    lines.append(f"## {scope_n}. Scope & deliverables")
    lines.append("")
    if packages:
        for key, pkg in packages.items():
            marker = " **(recommended)**" if key == recommended_package_key else ""
            lines.append(
                f"### {pkg.get('name') or key}{marker} — "
                f"{_money(pkg.get('price'), currency)}"
                + (
                    f" / ~{pkg.get('duration_days')} days"
                    if pkg.get("duration_days")
                    else ""
                )
            )
            lines.append("")
            if pkg.get("summary"):
                lines.append(pkg["summary"])
                lines.append("")
            for item in pkg.get("includes") or []:
                lines.append(f"- {item}")
            lines.append("")
    if out_of_scope:
        lines.append("### Out of scope")
        lines.append("")
        for item in out_of_scope:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(f"## {scope_n + 1}. Timeline")
    lines.append("")
    days = rec_pkg.get("duration_days") or 21
    lines.append(
        f"Suggested timeline for **{rec_pkg.get('name') or recommended_package_key}** "
        f"(~{days} days):"
    )
    lines.append("")
    lines.append("1. Kickoff and priority confirmation")
    lines.append("2. Design and content direction")
    lines.append("3. Implementation sprint")
    lines.append("4. QA and verification re-crawl")
    lines.append("5. Before/after report handover")
    lines.append("")

    lines.append(f"## {scope_n + 2}. Investment")
    lines.append("")
    if packages:
        lines.append("| Package | Investment | Timeline |")
        lines.append("|---|---:|---:|")
        for key, pkg in packages.items():
            star = " ★" if key == recommended_package_key else ""
            lines.append(
                f"| {pkg.get('name') or key}{star} | "
                f"{_money(pkg.get('price'), currency)} | "
                f"~{pkg.get('duration_days', '—')} days |"
            )
        lines.append("")
    if monitoring:
        lines.append(
            f"**Optional service:** {monitoring.get('name') or 'Monitoring'} — "
            f"{_money(monitoring.get('price'), currency)}/month. "
            f"{monitoring.get('summary') or ''}"
        )
        lines.append("")
    if config.get("payment_terms"):
        lines.append(f"**Payment terms:** {config['payment_terms']}")
        lines.append("")

    lines.append(f"## {scope_n + 3}. Next steps")
    lines.append("")
    lines.append(narratives.get("closing") or "")
    lines.append("")
    lines.append(
        f"Reply to **{config.get('contact_email') or 'your contact'}** confirming the "
        f"**{rec_pkg.get('name') or recommended_package_key}** package to proceed."
    )
    lines.append("")
    if config.get("terms"):
        lines.append("## Terms")
        lines.append("")
        lines.append(str(config["terms"]))
        lines.append("")
    if config.get("disclaimer"):
        lines.append(f"_{config['disclaimer']}_")
        lines.append("")
    lines.append("---")
    lines.append("")
    footer = config.get("footer") or f"{company}"
    lines.append(f"*{footer}*")
    lines.append("")
    # silence unused crawl id in client docs — available in manifest only
    _ = crawl
    return "\n".join(lines)


def generate_proposal(
    root: Path,
    *,
    website: dict | None = None,
    crawl: dict | None = None,
    evidence_pack: dict | None = None,
    recommendations: dict | None = None,
    mockups: dict | None = None,
    config: dict | None = None,
    opportunities: list | None = None,
    sell_recommendation: dict | None = None,
    prefer_ollama: bool = True,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> dict:
    if config is None:
        try:
            from backend.app.services.agency_settings import proposal_config_from_agency

            config = proposal_config_from_agency()
        except Exception:
            config = load_proposal_config()

    if evidence_pack is None:
        pack_path = root / "evidence" / "evidence_pack.json"
        if pack_path.exists():
            evidence_pack = json.loads(pack_path.read_text(encoding="utf-8"))
    evidence_pack = evidence_pack or {}

    if recommendations is None:
        rec_path = root / "evidence" / "recommendations.json"
        if rec_path.exists():
            recommendations = json.loads(rec_path.read_text(encoding="utf-8"))
    recommendations_payload = recommendations or {}
    recs = recommendations_payload.get("recommendations") or recommendations_payload

    if mockups is None:
        mock_path = root / "mockups" / "manifest.json"
        if mock_path.exists():
            mockups = json.loads(mock_path.read_text(encoding="utf-8"))

    website = website or evidence_pack.get("website") or recommendations_payload.get("website") or {}
    crawl = crawl or evidence_pack.get("crawl") or recommendations_payload.get("crawl") or {}
    scores = (
        evidence_pack.get("scores")
        or recommendations_payload.get("scores")
        or {}
    )
    # Compact client-facing cards only — never raw axe rows in the proposal body.
    from backend.app.services.finding_clusters import cluster_summary

    raw_top = ((evidence_pack.get("findings") or {}).get("top")) or []
    findings = cluster_summary(raw_top, max_items=8)
    domain = website.get("domain") or "website"
    opportunities = opportunities or []

    from backend.app.services.llm_client import resolve_provider
    from backend.app.services.commercial_score import recommend_package_from_opportunities

    source = "rule_based"
    error = None
    narratives = _rule_narratives(domain, scores, recs, findings, opportunities)
    # When opportunities drive the proposal, keep narratives fast/local unless forced.
    use_llm = prefer_ollama and not opportunities
    if use_llm:
        try:
            narratives = _ollama_narratives(
                domain=domain,
                scores=scores,
                recs=recs,
                findings=findings,
                model=model,
                base_url=base_url,
            )
            fallback = _rule_narratives(domain, scores, recs, findings, opportunities)
            for key, value in fallback.items():
                if not narratives.get(key):
                    narratives[key] = value
            source = resolve_provider()
        except Exception as exc:
            error = str(exc)
            source = "rule_based_fallback"

    if sell_recommendation and sell_recommendation.get("recommended_package"):
        recommended_key = sell_recommendation["recommended_package"]
        sell_why = sell_recommendation.get("why") or sell_recommendation.get("reasons") or []
    elif opportunities:
        sell = recommend_package_from_opportunities(opportunities, config=config)
        recommended_key = sell["recommended_package"]
        sell_why = sell.get("why") or []
        sell_recommendation = sell
    else:
        recommended_key = _recommend_package(scores, 0, config)
        sell_why = ["Based on overall site health pending opportunity review."]
        sell_recommendation = {
            "recommended_package": recommended_key,
            "why": sell_why,
        }

    scoped_packages = build_scoped_packages(
        config, findings, recs, opportunities=opportunities
    )
    markdown = build_proposal_markdown(
        config=config,
        website=website,
        crawl=crawl,
        scores=scores,
        findings=findings,
        recommendations=recs,
        mockups=mockups,
        narratives=narratives,
        recommended_package_key=recommended_key,
        packages_override=scoped_packages,
        opportunities=opportunities,
        sell_why=sell_why,
        client_mode=True,
    )

    out_dir = root / PROPOSAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = root / MARKDOWN_FILENAME
    md_path.write_text(markdown, encoding="utf-8")

    opp_snapshot = [
        {
            "id": str(o.get("id")) if o.get("id") else None,
            "client_title": o.get("client_title") or o.get("title"),
            "priority": o.get("priority"),
            "status": o.get("status"),
            "proposal_status": o.get("proposal_status"),
            "selected_package": o.get("selected_package"),
            "recommendation": o.get("recommendation"),
        }
        for o in opportunities
    ]

    manifest = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "model": model if source in {"ollama", "openai", "anthropic"} else None,
        "error": error,
        "domain": domain,
        "recommended_package": recommended_key,
        "sell_recommendation": sell_recommendation,
        "scores": scores,
        "markdown_file": MARKDOWN_FILENAME,
        "mockup_images": [
            img.get("path") for img in ((mockups or {}).get("images") or [])
        ],
        "company_name": config.get("company_name"),
        "narratives": narratives,
        "packages": scoped_packages,
        "out_of_scope": config.get("out_of_scope_defaults") or [],
        "website": website,
        "crawl": {"id": crawl.get("id")},  # internal only — not in client markdown
        "opportunities": opp_snapshot,
        "findings_top": findings[:12],
        "recommendations_snapshot": {
            "quick_wins": (recs.get("quick_wins") or [])[:8],
            "priority_actions": (recs.get("priority_actions") or [])[:8],
            "strategic_improvements": (recs.get("strategic_improvements") or [])[:6],
            "proposal_angles": (recs.get("proposal_angles") or [])[:5],
        },
        "mockups": mockups,
        "config_snapshot": {
            "currency": config.get("currency"),
            "monitoring": config.get("monitoring"),
            "contact_email": config.get("contact_email"),
            "company_tagline": config.get("company_tagline"),
            "payment_terms": config.get("payment_terms"),
        },
    }
    (root / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    manifest["markdown"] = markdown
    return manifest


def update_proposal(
    root: Path,
    *,
    narratives: dict | None = None,
    recommended_package: str | None = None,
    packages: dict | None = None,
    out_of_scope: list | None = None,
    markdown: str | None = None,
    config: dict | None = None,
) -> dict:
    """Patch an existing proposal and regenerate markdown (unless raw markdown set)."""
    existing = load_proposal(root)
    if existing is None:
        raise ProposalError("Proposal not generated yet")

    config = config or load_proposal_config()
    website = existing.get("website") or {"domain": existing.get("domain")}
    crawl = existing.get("crawl") or {"id": None}
    scores = existing.get("scores") or {}
    findings = existing.get("findings_top") or []
    recs = existing.get("recommendations_snapshot") or {}
    mockups = existing.get("mockups")

    merged_narratives = dict(existing.get("narratives") or {})
    if narratives:
        for key in ("executive_summary", "opportunity", "closing"):
            if key in narratives and narratives[key] is not None:
                merged_narratives[key] = str(narratives[key])

    pkg_key = recommended_package or existing.get("recommended_package") or "growth"
    scoped = packages if packages is not None else (
        existing.get("packages") or build_scoped_packages(config, findings, recs)
    )
    scope_list = (
        out_of_scope
        if out_of_scope is not None
        else existing.get("out_of_scope")
        or config.get("out_of_scope_defaults")
        or []
    )

    cfg = dict(config)
    cfg["packages"] = scoped
    cfg["out_of_scope_defaults"] = scope_list

    opportunities = existing.get("opportunities") or []
    sell_why = (existing.get("sell_recommendation") or {}).get("why") or []
    if recommended_package and existing.get("sell_recommendation"):
        existing_sell = dict(existing.get("sell_recommendation") or {})
        existing_sell["recommended_package"] = pkg_key
        pkg_meta = scoped.get(pkg_key) or {}
        existing_sell["package_name"] = pkg_meta.get("name") or pkg_key
        existing_sell["price"] = pkg_meta.get("price")
        existing["sell_recommendation"] = existing_sell

    if markdown is not None:
        md_text = markdown
    else:
        md_text = build_proposal_markdown(
            config=cfg,
            website=website,
            crawl=crawl,
            scores=scores,
            findings=findings,
            recommendations=recs,
            mockups=mockups,
            narratives=merged_narratives,
            recommended_package_key=pkg_key,
            packages_override=scoped,
            opportunities=opportunities,
            sell_why=sell_why,
            client_mode=True,
        )

    md_path = root / MARKDOWN_FILENAME
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")

    manifest = {
        **{k: v for k, v in existing.items() if k != "markdown"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "recommended_package": pkg_key,
        "narratives": merged_narratives,
        "packages": scoped,
        "out_of_scope": scope_list,
        "markdown_file": MARKDOWN_FILENAME,
        "edited": True,
    }
    # Drop PDF until re-exported so UI doesn't show stale file as current.
    manifest.pop("pdf_file", None)
    pdf_path = root / "proposal" / "proposal.pdf"
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except OSError:
            pass

    (root / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    manifest["markdown"] = md_text
    return manifest


def load_proposal(root: Path) -> dict | None:
    path = root / MANIFEST_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    md_rel = data.get("markdown_file") or MARKDOWN_FILENAME
    md_path = root / md_rel
    if md_path.exists():
        data["markdown"] = md_path.read_text(encoding="utf-8")
    pdf_rel = data.get("pdf_file") or "proposal/proposal.pdf"
    if (root / pdf_rel).exists():
        data["pdf_file"] = pdf_rel
    else:
        data.pop("pdf_file", None)
    return data
