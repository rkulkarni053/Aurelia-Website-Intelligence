# Aurelia / Website Intelligence — Project Documentation

**Product name:** Aurelia (API title: `Aurelia API`)  
**Repository:** `website-intelligence`  
**Document date:** 2026-10-09  
**Scope:** Exact description of the system as implemented, with emphasis on the Base44-style local agent workstream (company understanding → Brain → Design chat → live demo → concept boards → proposal).

---

## 1. Product purpose

Aurelia is a **local-first website intelligence workspace** for an agency sales/delivery loop:

1. **Crawl** a client website and collect evidence (HTML, screenshots, SEO, SSL, tech, a11y, performance, Lighthouse).
2. **Understand the company** from crawl text (brand, services, use cases, CTA) — not generic SEO fluff.
3. **Diagnose** findings and score the site.
4. **Recommend** commercial actions (Brain) grounded in that company story.
5. **Design** a clickable HTML demo and iterate via chat (Base44-like).
6. **Propose** a priced package (markdown + PDF) and move the engagement through workflow statuses.

**Hard product constraints chosen for this work:**

- Prefer **free / local** intelligence (Ollama `qwen2.5:7b`) over paid Claude/GPT when possible.
- On **CPU + limited VRAM** (e.g. 4GB GTX 1660 + 32GB RAM), do **not** pretend a 7B chat model is Base44-fast. Ship **crawl-grounded company profiles** instantly; use LLM polish only when GPU/cloud is available.
- **Live HTML demos** are the primary visual deliverable. AI photo mockups (TinySD) are optional and disabled by default because they are slow and look fake on CPU.

---

## 2. What this workstream delivered

This section documents the concrete capabilities built/hardened in the Base44-style agent pass (beyond the earlier crawl → findings → proposal MVP).

| Capability | Status | Primary code |
|---|---|---|
| Crawl-grounded **company profile** (deterministic extraction) | Done | `backend/app/services/company_profile.py` |
| **Profile-first Brain** (~instant on CPU Ollama) | Done | `brain.py` + `config/agency.json` `agent.profile_first_brain` |
| Unified **LLM client** (Ollama / OpenAI / Anthropic) + Anthropic billing probe | Done | `llm_client.py` |
| Compact **agent context** for prompts | Done | `agent_context.py` |
| Design chat → brief → **regenerate live demo** | Done | `design_chat.py`, `demo_site.py`, `site_design.py` |
| Generative demo loop: prompt → spec → components → HTML → Playwright → QA | Done | `demo_builder.py` |
| Concept boards (Pillow) as default mockups; TinySD off by default | Done | `mockups.py`, `.env` `MOCKUP_BACKEND=concept` |
| Agency settings for agent behavior | Done | `agency_settings.py`, `config/agency.json` |
| Brain few-shot training (curated examples from external site patterns) | Done | `config/agency/examples/`, `feedback_store.py` |
| React UI modes (Overview → Diagnose/Brain → Design → Proposal → …) | Done | `frontend/src/` |

**Validated reference crawl:** `evp-website-one.vercel.app` — profile extracts brand **EVP Malta** / legal **Exclusive Video Productions**, services (OB, live streaming, corporate video, …), location Malta/Gozo, CTA “Start a project”.

---

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  React SPA (Vite)  →  /app/                                     │
│  Modes: Overview · Diagnose · Opportunities · Design · Proposal │
│         Deliver · Verify                                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP /api/*
┌───────────────────────────────▼─────────────────────────────────┐
│  FastAPI  (backend/app/main.py)  — “Aurelia API”                │
│  Routers: companies, projects, websites, website_detail,        │
│           crawls, agency                                        │
└───────┬───────────────────────────────┬─────────────────────────┘
        │                               │
        ▼                               ▼
┌───────────────────┐         ┌───────────────────────────────────┐
│ Postgres          │         │ Filesystem evidence               │
│ (metadata,        │         │ data/websites/<domain>/crawls/<id>/│
│  findings,        │         │   evidence/ seo/ ssl/ lighthouse/ │
│  opportunities,   │         │   demo/ design/ mockups/ proposal/│
│  crawl status)    │         └───────────────────────────────────┘
└───────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ Local services                                                    │
│  Ollama (qwen2.5:7b) · Playwright · SiteOne crawler (optional)    │
│  Pillow concept boards · (optional) Diffusers/TinySD              │
└───────────────────────────────────────────────────────────────────┘
```

**Runtime split:**

| Layer | Role |
|---|---|
| Postgres | Projects, companies, websites, crawls, findings rows, opportunities, workflow status |
| `data/websites/...` | All heavy evidence artifacts (HTML, screenshots, JSON packs, demos, PDFs) |
| Ollama | Optional LLM polish for Brain, Design chat, generative demo specs/QA |
| Playwright | Browser capture during crawl; demo preview screenshots |

---

## 4. Repository layout

```
website-intelligence/
├── backend/app/
│   ├── main.py                 # FastAPI app, /health, /api/brain/status, static mounts
│   ├── database.py             # Settings (.env) + SQLAlchemy engine
│   ├── models/                 # ORM: Company, Project, Website, Crawl, Finding, …
│   ├── routes/                 # HTTP API
│   │   ├── crawls.py           # Main crawl lifecycle + Brain/Design/Demo/Proposal APIs
│   │   ├── websites.py, website_detail.py, projects.py, companies.py, agency.py
│   ├── services/               # Business logic (see §6–§12)
│   └── schemas/
├── frontend/                   # React 19 + Vite SPA (aurelia-frontend)
│   └── src/
│       ├── App.jsx             # Routing + mode tabs
│       ├── hooks/useWorkspace.js
│       └── components/modes/   # Overview, Audit, Brain, Design, Opportunities, Proposal
├── config/
│   ├── agency.json             # Branding, packages, agent flags
│   ├── proposal.json           # Proposal pricing defaults
│   └── agency/prompts/         # System prompts (brain, chat.design, chat.advisory)
├── data/websites/              # Per-site crawl artifacts (gitignored in practice)
├── docs/                       # This documentation + older PRD/tracker
├── bin/siteone-crawler         # Optional SiteOne binary wrapper
├── scripts/                    # Backfills / install helpers
├── docker-compose.yml          # Postgres 18 only
└── .env                        # Local secrets + model/mockup settings
```

---

## 5. Configuration

### 5.1 Environment (`.env` / `database.py` Settings)

| Variable | Default / intent |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `BRAIN_PROVIDER` | `ollama` \| `openai` \| `anthropic` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `qwen2.5:7b` |
| `OLLAMA_TIMEOUT_SECONDS` | `300` |
| `OPENAI_*` / `ANTHROPIC_*` | Optional cloud keys + model names |
| `MOCKUP_BACKEND` | **`concept`** (recommended). `auto`/`ai` = TinySD path (slow/fake on CPU) |
| `IMAGE_MODEL_ID` | `segmind/tiny-sd` (only if AI mockups enabled) |
| `CRAWL_MAX_PAGES` | `500` (HTTP discovery cap) |
| `CRAWL_MAX_BROWSER_PAGES` | `40` |
| `CRAWL_MAX_CONTENT_PAGES` | `200` |
| `CRAWL_MAX_LIGHTHOUSE_PAGES` | `5` |
| `CRAWL_SITEONE_MAX_URLS` | `200` |

**Important:** Uvicorn `--reload` hot-reloads Python code. **Changing `.env` requires an API process restart** to reload Settings.

### 5.2 Agency agent flags (`config/agency.json` → `agent`)

```json
{
  "enabled": true,
  "use_ollama_for_advisory": true,
  "prefer_fast_chat_model": true,
  "prefer_fast_brain_model": true,
  "profile_first_brain": true,
  "brain_timeout_seconds": 45
}
```

When `profile_first_brain` is true and the active provider is Ollama **not on GPU**, Brain skips the LLM and returns the company-profile + rule-based commercial plan immediately.

---

## 6. End-to-end data pipeline

```
Create Company → Project → Website
        ↓
POST crawl (background job)
        ↓
┌──────────────────────────────────────────────────────────┐
│ Crawl pipeline                                           │
│  HTTP crawl (same-domain)                                │
│  → SSL / SEO / content SEO / SiteOne (optional)          │
│  → Playwright browser pages (priority: home/about/…)     │
│  → Accessibility (axe) · Performance · Lighthouse        │
│  → Tech detection · Findings · Annotated screenshots     │
│  → Evidence pack · Site story · Conversion path          │
│  → Company profile (deterministic)                       │
└──────────────────────────────────────────────────────────┘
        ↓
Ask Brain  →  recommendations.json (+ company_profile)
        ↓
Design mode
  ├─ Live HTML demo (demo_site / demo_builder)
  ├─ Design chat (brief.json + chat.json)
  └─ Concept boards (mockups/*.png)
        ↓
Opportunities → Sell recommendation → Proposal (md + PDF)
        ↓
Workflow: awaiting_approval → approved → implementation → verification → completed
```

### 6.1 Crawl artifact tree (exact)

For crawl id `{CRAWL}` of domain `{DOMAIN}`:

```
data/websites/{DOMAIN}/crawls/{CRAWL}/
├── evidence/
│   ├── evidence_pack.json          # Compact LLM/audit context
│   ├── company_profile.json        # Deterministic company intelligence
│   ├── recommendations.json        # Brain output
│   ├── findings.json
│   ├── pages.json
│   ├── checklist.json
│   ├── opportunities.json
│   ├── annotated_screenshots.json
│   ├── accessibility.json
│   ├── browser.json
│   └── performance.json
├── seo/          # analysis, content, site_story, conversion_path, siteone_summary
├── ssl/certificate.json
├── technologies/technologies.json, upgrades.json
├── lighthouse/summary.json
├── screenshots/  # desktop/mobile captures
├── html/         # raw + rendered HTML
├── design/
│   ├── brief.json                  # Editable design direction
│   └── chat.json                   # Persisted Design chat history
├── demo/
│   ├── index.html                  # Clickable client preview
│   ├── manifest.json
│   ├── site_spec.json              # Generative builder spec (when used)
│   ├── preview-desktop.png
│   └── build_log.json
├── mockups/
│   ├── desktop-homepage.png
│   ├── mobile-homepage.png
│   ├── concept-board.png
│   └── manifest.json
├── proposal/
│   ├── proposal.md
│   ├── proposal.json
│   └── proposal.pdf (when generated)
└── reports/      # proof / SiteOne / manifests
```

Artifacts are also served at:

`/data/websites/{DOMAIN}/crawls/{CRAWL}/...`

---

## 7. Company profile (crawl intelligence)

**File:** `backend/app/services/company_profile.py`  
**Output:** `evidence/company_profile.json`

### 7.1 Why it exists

Local 7B models on CPU cannot reliably “rediscover” the business on every Brain click without hanging for minutes. The profile is a **deterministic extractor** over `site_story` + page excerpts so the product always knows:

- Who the brand is (display vs legal vs SEO title)
- Industry / location
- Services and use cases
- One-liner and primary CTA
- Proof points (years in business, resolution claims, etc.)

### 7.2 Extraction behavior (exact)

`build_company_profile(pack)`:

1. Reads `pack.site_story` pages, headlines, value props, CTAs, scores.
2. `_extract_brand_names` prefers real studio names over SEO niche titles  
   (e.g. rejects “Video Production Malta” when “Exclusive Video Productions” / “EVP Malta” are present).
3. Infers industry (`video_production_broadcast`, etc.), location patterns, service lists, use cases, audience, proof regexes.
4. Builds `one_liner`, `usecase_summary`, `story_for_brain`.

`ensure_company_profile(root, pack)` loads existing file or builds + writes.

`profile_for_prompt(profile)` produces a compact string for LLM system/user context.

### 7.3 Example shape (EVP)

```json
{
  "brand": {
    "display_name": "EVP Malta",
    "legal_name": "Exclusive Video Productions",
    "seo_title_name": "Video Production Malta"
  },
  "industry": "video_production_broadcast",
  "location": "Malta and Gozo",
  "services": ["Outside Broadcasting", "Live Streaming", "Corporate Video", "..."],
  "use_cases": ["Sports and stadium coverage", "Concerts and live events", "..."],
  "primary_cta": "Start a project",
  "one_liner": "EVP Malta is Malta's video production and live broadcast studio. ..."
}
```

Consumers: Brain baseline, Design chat advisory, agent context, concept mockups, demo copy.

---

## 8. Brain (recommendations)

**File:** `backend/app/services/brain.py`  
**API:** `GET/POST /api/websites/{id}/crawls/{crawl_id}/recommendations`

### 8.1 `generate_recommendations` algorithm (exact)

1. Load/build **company profile**.
2. Build **rule-based baseline** from pack + opportunities + profile (`rule_based_recommendations`).
3. Resolve provider via `llm_client.resolve_provider`.
4. If `profile_first_brain` and provider is Ollama and model is **not on GPU** → **return baseline immediately** (`source: "company_profile"`). No multi-minute CPU generate.
5. Else call `generate_with_llm`, merge with baseline, fall back cloud↔Ollama on failure.
6. Always ensure `site_story_summary`, `content_suggestions`, and nested `company_profile` summary exist.
7. Persist via `write_recommendations`.

### 8.2 Recommendation payload shape

Top-level wrapper:

- `version`, `generated_at`, `source`, `provider`, `model`, `error`
- `company_profile` (summary for UI)
- `website`, `crawl`, `scores`
- `recommendations` (inner object):
  - `site_story_summary`
  - `executive_summary`
  - `priority_actions[]` (title, category, impact, effort, why, how)
  - `quick_wins[]`, `strategic_improvements[]`, `proposal_angles[]`
  - `content_suggestions[]` (area, current, suggested, why)
  - `mockup_prompts[]`

### 8.3 Agent context shrink

`agent_context.build_agent_context` / `shrink_for_brain` produce a compact pack (few findings, company profile, opportunities, agency snippet) so prompts stay small on 7B context windows.

---

## 9. Design chat + design brief

**Files:** `design_chat.py`, `site_design.py`  
**APIs:**

- `GET/POST .../design/chat`
- `GET .../design/brief`

### 9.1 Brief

`design/brief.json` holds editable visual/copy direction:

- Brand name, headline, subheadline, CTA
- Palette colors
- Services blocks
- Style notes / image prompt
- Chat overrides preserved across Brain sync (`sync_brief_from_brain(..., preserve_chat_overrides=True)`)

### 9.2 Chat turn routing (`process_chat_message`)

Exact priority order:

1. **Generative build prompts** (`looks_like_build_prompt`) → `demo_builder.build_demo_from_prompt`  
   Starters include: “build me”, “create a”, “make me a”, “design a website”, “scaffold”, …
2. **Advisory** questions about the business/audit → LLM or company-profile fallback answers.
3. **Design edits** (colors, headline, CTA, layout language) → brief patch → regenerate live demo.

Chat history persists in `design/chat.json`.

### 9.3 Design vs advisory tone

Prompts live under `config/agency/prompts/`:

- `chat.design.system.md` — brief patches / visual direction
- `chat.advisory.system.md` — business Q&A
- `brain.system.md` — recommendations
- `methodology.default.md` — commercial methodology text

---

## 10. Live HTML demo

Two generators exist; both write under `demo/`.

### 10.1 Story-grounded demo (`demo_site.py`)

**API:** `POST .../demo`

Builds a multi-section marketing page from:

- Brain recommendations / content suggestions
- Company profile / site story
- Design brief palette + headline/CTA
- Optional reference screenshot embedding

Output: `demo/index.html` + `demo/manifest.json`.

This is the default “refresh demo from Brain/brief” path used after Design chat brief edits.

### 10.2 Generative builder (`demo_builder.py`) — Base44-style loop

**API:** `POST .../demo/build` with `{ "prompt": "...", "max_fix_iters": 1 }`  
Also triggered from Design chat when the message looks like a build request.

Exact loop:

```
User prompt
  → prompt_to_site_spec()     # Qwen JSON site specification
  → select_components()       # Map sections to component variants
  → generate_code()           # Full HTML document
  → write_demo_artifacts()
  → screenshot_and_extract()  # Playwright desktop preview + DOM extract
  → examine_result()          # QA (issues + optional spec_patch)
  → apply_spec_patch / regenerate (up to max_fix_iters)
  → build_log.json + preview-desktop.png
```

**Section types:** hero, menu, services, about, gallery, process, reservations, testimonials, contact, footer.

**Component variants** (examples): hero=`cinematic|split|centered`, services=`cards|mosaic`, etc.

The builder prefers structured local generation over inventing production React apps.

---

## 11. Concept boards (mockups)

**File:** `mockups.py`  
**API:** `GET/POST .../mockups`

### 11.1 Decision (2026-10-08)

TinySD via Diffusers on CPU (`MOCKUP_BACKEND=auto`) took minutes and produced invalid/fake-looking images. Product default is now:

- `MOCKUP_BACKEND=concept`
- `generate_mockups(..., backend="concept")` default
- `backend=="auto"` coerced to `concept` in code
- Crawl route forces concept even if settings still say `auto`/`ai` until env restart

### 11.2 Concept board contents

Pillow renders three boards (~0.5–1s total):

| File | Purpose |
|---|---|
| `mockups/desktop-homepage.png` | Browser-chrome homepage layout comps |
| `mockups/mobile-homepage.png` | Mobile frame layout |
| `mockups/concept-board.png` | Proposal-oriented board |

Context comes from brief + recommendations + **company_profile** (brand, headline, CTA, actions). Optional reference screenshot is pasted into the desktop hero area when available.

**UI copy:** Design mode labels these “Concept boards / Instant layout comps · not AI photos”. Topbar action: **Concept Boards**.

Live HTML demo remains the primary client preview.

---

## 12. LLM client

**File:** `llm_client.py`

- `chat_text` / `chat_json` across Ollama, OpenAI, Anthropic
- `provider_status()` for Settings + `/api/brain/status`
- Anthropic **billing probe**: if a key exists, a tiny Messages call detects credit/auth failures so Settings can warn instead of hanging Brain/chat later

Brain provider selection: `.env` `BRAIN_PROVIDER`. Cloud keys are optional; product remains usable fully offline via profile-first + rule-based paths.

---

## 13. Opportunities, sell recommendation, proposal

| Step | Service / API |
|---|---|
| Cluster findings → commercial opportunities | `opportunities.py`, `finding_clusters.py` |
| Generate / patch opportunities | `POST/PATCH .../opportunities` |
| Sell recommendation (package pick) | `GET/POST .../sell-recommendation` |
| Proposal markdown | `proposal.py` → `POST .../proposal` |
| Proposal PDF | `proposal_pdf.py` → `POST .../proposal/pdf` |
| Proposal edit | `PATCH .../proposal` |

Packages/pricing come from `config/agency.json` (`essentials` / `growth` / `redesign` + add-ons) and `config/proposal.json`.

Methodology (client language first, human approves before send) is stored in agency settings.

---

## 14. Engagement workflow

**File:** `workflow.py`

Allowed transitions:

```
created → crawling → evidence_collected → analyzing → awaiting_approval
  → approved → implementation → verification → completed
  (verification may re-enter crawling; completed may start a new cycle)
```

---

## 15. HTTP API map (crawl-centric)

Base: `/api/websites/{website_id}/crawls/...`

| Method | Path | Purpose |
|---|---|---|
| POST | `/` (create crawl) | Start crawl job |
| GET | `/{crawl_id}` | Crawl metadata |
| GET | `/{crawl_id}/progress` | Live progress |
| GET | `/{crawl_id}/findings` | Findings list |
| GET | `/{crawl_id}/evidence-pack` | Evidence pack |
| GET/POST | `/{crawl_id}/recommendations` | Brain |
| GET/POST | `/{crawl_id}/design/chat` | Design/advisory chat |
| GET | `/{crawl_id}/design/brief` | Design brief |
| GET/POST | `/{crawl_id}/mockups` | Concept boards |
| GET/POST | `/{crawl_id}/demo` | Story-grounded HTML demo |
| POST | `/{crawl_id}/demo/build` | Generative demo loop |
| GET/POST | `/{crawl_id}/proposal` | Proposal |
| POST | `/{crawl_id}/proposal/pdf` | PDF export |
| GET/POST | `/{crawl_id}/opportunities...` | Commercial opportunities |
| GET/POST | `/{crawl_id}/sell-recommendation` | Package recommendation |
| GET/POST | `/{crawl_id}/verification` | Verification re-crawl artifacts |
| GET/PATCH | `/{crawl_id}/checklist` | Delivery checklist |
| GET | `/{crawl_id}/upgrades` | Tech upgrade hints |
| GET | `/{crawl_id}/conversion-path` | Conversion analysis |
| GET | `/{crawl_id}/screenshots` | Screenshot index |
| POST | `/{crawl_id}/vision` | Vision review hook |

Also:

- `GET /health`
- `GET /api/brain/status` — provider readiness + image backend setting
- Agency routes under `/api/agency/...`
- Companies / projects / websites CRUD routers

---

## 16. Frontend (exact UX map)

**Stack:** React 19, Vite 6, single SPA served at `/app/` (built into `frontend/dist`).

### 16.1 Navigation

- **Views:** Dashboard, Projects, Sites, Crawls, Settings
- **Dashboard modes** (`MODE_TABS` in `App.jsx`):
  1. Overview
  2. Diagnose (Audit + Brain panel)
  3. Opportunities
  4. Design (chat + live demo + concept boards)
  5. Proposal
  6. Deliver
  7. Verify

### 16.2 Workspace hook

`useWorkspace.js` owns website/crawl selection, crawl actions, Brain, Design chat, mockups, demo, proposal, brain status alerts.

### 16.3 Design mode behavior

- Primary surface: **live demo iframe/link**
- Chat drives brief edits or generative builds
- Concept boards are secondary, explicitly labeled as layout comps
- Buttons: Build boards / Refresh boards (not “AI photos”)

### 16.4 Settings

Shows Brain provider status, Ollama models, Anthropic billing probe results, mockup backend setting.

---

## 17. How to run (local)

### 17.1 Infrastructure

```bash
docker compose up -d          # Postgres on 127.0.0.1:5432
# Ensure .env DATABASE_URL matches docker-compose credentials
```

### 17.2 Backend

```bash
source .venv/bin/activate
# Example (adjust to your usual start script):
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### 17.3 Frontend (dev)

```bash
cd frontend && npm install && npm run dev
# or build for API-served SPA:
npm run build
```

### 17.4 Ollama

```bash
ollama pull qwen2.5:7b
# OLLAMA_BASE_URL must reach the daemon
```

### 17.5 Typical operator loop

1. Add company → project → website URL  
2. Run crawl; wait until `completed`  
3. Open Diagnose → **Ask Brain** (profile-first → fast)  
4. Open Design → chat (“make CTA gold”, or “Build me a modern …”)  
5. Open live demo; refresh concept boards if needed  
6. Opportunities → accept sell recommendation → Generate proposal / PDF  

---

## 18. Design decisions (why the system looks like this)

| Decision | Rationale |
|---|---|
| Company profile before LLM | CPU 7B cannot be both fast and deep; crawl text already has the company |
| Profile-first Brain default | Matches Base44 “instant understanding” feel on local hardware |
| Live HTML demo > AI images | Clients click real pages; TinySD comps waste time and look fake |
| `MOCKUP_BACKEND=concept` | Sub-second on-brand boards; AI path remains optional |
| Generative demo builder | Chat “build me a …” creates a full page with Playwright QA, not just copy edits |
| Unified LLM client | Same Brain/chat/proposal path can use Ollama or cloud when credits exist |
| Agency packages in JSON | Pricing editable without code deploys |
| Evidence on disk + metadata in Postgres | Large binaries/HTML stay filesystem-cheap; DB stays queryable |

---

## 19. Known limitations / non-goals (current)

- No multi-tenant auth / production hardening as a product gate yet  
- GPT-quality photographic mockups **parked** (needs stronger GPU/model)  
- Generative demo is a **one-page marketing HTML** system, not a full CMS builder  
- Vision-from-arbitrary-screenshot chat is stubbed (`POST .../vision`) pending local VL models  
- SiteOne / Lighthouse quality depends on local binaries being installed  
- `.env` changes need API restart; Python module changes hot-reload with `--reload`

---

## 20. Related documents

| Doc | Role |
|---|---|
| `docs/PRODUCT_REQUIREMENTS.md` | Original owner intent (2026-10-05) |
| `docs/PROJECT_TRACKER.md` | Phase checklist (partially superseded by this doc) |
| `docs/STATUS_REPORT.md` | Earlier ~90% MVP status (pre profile-first / demo_builder) |
| `docs/PROJECT_DOCUMENTATION.md` | **This file — authoritative system description as of 2026-10-09** |
| `config/agency/prompts/*.md` | Live agent system prompts |

---

## 21. Key module index

| Module | Responsibility |
|---|---|
| `crawler.py` / `crawl_enrichment.py` | Page discovery + browser target priority |
| `seo_collector.py` / `content_seo.py` / `site_story.py` | SEO + narrative excerpts |
| `browser_collector.py` / `playwright_env.py` | Screenshots + rendered HTML |
| `findings.py` / `annotate.py` | Deterministic findings + overlays |
| `evidence_pack.py` | Compact pack for LLMs/UI |
| `company_profile.py` | Brand/services/use-case extraction |
| `brain.py` | Recommendations (profile-first + LLM) |
| `agent_context.py` | Shared compact context builder |
| `llm_client.py` | Multi-provider chat |
| `design_chat.py` / `site_design.py` | Chat + brief |
| `demo_site.py` | Story-grounded HTML demo |
| `demo_builder.py` | Generative Base44-style build loop |
| `mockups.py` / `image_gen.py` | Concept boards / optional TinySD |
| `opportunities.py` / `proposal.py` / `proposal_pdf.py` | Commercial close |
| `workflow.py` | Project status machine |
| `agency_settings.py` | Load/merge `config/agency.json` |

---

*End of project documentation.*
