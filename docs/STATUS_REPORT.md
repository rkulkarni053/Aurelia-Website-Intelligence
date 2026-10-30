# Website Intelligence — Status Report

**As of:** 2026-10-05  
**Overall readiness:** ~90% of the free/local product vision  
**Current focus area:** Parked — GPT-quality mock images / upgrade analysis

---

## Executive summary

End-to-end path works: crawl → content SEO + Lighthouse scores → annotated screenshots → evidence pack → Ollama recommendations → mockups → **business proposal (markdown + PDF)** → engagement workflow statuses. Edit pricing in `config/proposal.json`.

---

## What works today

- Create projects and websites; queue crawls as background jobs.
- Crawl same-domain pages (HTTP fetch, ~20 page cap).
- Collect and store:
  - Raw + rendered HTML  
  - Desktop/mobile screenshots (+ annotated finding overlays)  
  - SSL / HTTPS behavior  
  - robots.txt / sitemap SEO signals  
  - Content / word SEO (`seo/content.json`)  
  - Tech stack fingerprints  
  - Accessibility (axe)  
  - Performance timings (incl. LCP)  
  - Lighthouse CLI scores when installed, else local heuristic
- Turn evidence into **deterministic findings** (severity + category).
- Persist findings in Postgres; expose list/summary/compare APIs.
- Build `evidence/evidence_pack.json` (compact LLM context + scores).
- Local Ollama recommendations, mockups, proposal markdown + PDF.
- Dashboard: project/site/crawl picker, score cards, annotated gallery, workflow buttons, Export PDF.

Validated with crawls against `example.com` under `data/websites/`.

---

## Remaining gaps

| Goal | Gap |
|------|-----|
| GPT-quality site mock images | Parked — needs stronger local model / GPU |
| Upgrade opportunity analysis | Not started (outdated CMS/plugins) |
| Full audit PDF report | Proposal PDF only |
| Multi-tool AI agent | Single-shot Ollama today |
| In-UI proposal editor | Edit files/config instead |

---

## Architecture snapshot

```
Browser UI (frontend/index.html)
        ↓
FastAPI (projects, websites, crawls)
        ↓
Background crawl pipeline
  → crawl → SSL → SEO → content SEO → tech → browser → a11y
  → findings → annotate → lighthouse → evidence pack
  → project status: awaiting_approval
        ↓
Postgres (metadata) + data/websites/... (evidence files)
        ↓
Ollama brain → recommendations → mockups → proposal.md/pdf
```

---

## Related docs

- [Project Tracker](./PROJECT_TRACKER.md) — phase-by-phase checklist
