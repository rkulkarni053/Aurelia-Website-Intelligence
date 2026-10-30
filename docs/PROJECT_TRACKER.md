# Website Intelligence — Project Tracker

**Last updated:** 2026-10-05  
**Product goal:** Crawl a target site → analyze (SEO technical + content, tech stack, SSL, upgrades, scores) → evidence & error screenshots → recommendations → redesign mockups → business proposal — powered by a **local free/open-source AI brain**.

**Current milestone:** Finish pass complete (content SEO, Lighthouse, annotated shots, workflow, PDF)  
**Parked for later:** GPT-quality “mock better website” AI images (needs stronger model/GPU research)

---

## Phase overview

| Phase | Name | Status | Goal |
|-------|------|--------|------|
| 0 | Foundations | Done | API, DB, projects/websites/crawls model |
| 1 | Evidence engine | Done enough | Crawl + collectors + findings + pack + content SEO + annotate |
| 2 | Scoring & dashboard | Done enough | Scores + picker + Lighthouse/heuristic scores |
| 3 | Local AI brain | Done enough | Ollama recommendations from evidence pack |
| 4 | Visual redesign | Partial / parked | TinySD works; better website mock images = future research |
| 5 | Business proposal | Done | Markdown + PDF export |
| 6 | Engagement workflow | Done enough | Status API + pipeline + dashboard controls |

---

## Phase 0 — Foundations

| Item | Status | Notes |
|------|--------|-------|
| FastAPI app + health | Done | `backend/app/main.py` |
| Postgres (Docker) | Done | `docker-compose.yml` |
| Projects / websites / crawls models | Done | SQLAlchemy models + routes |
| Pages + findings models | Done | Stored per crawl |
| Static frontend mount | Done | `/app` → `frontend/index.html` |
| README / docs | Partial | README empty; this tracker added |

---

## Phase 1 — Evidence engine

| Item | Status | Notes |
|------|--------|-------|
| Same-domain crawl (BFS) | Done | Cap ~20 pages (`crawler.py`) |
| Save raw HTML | Done | `data/websites/.../html/` |
| SSL / HTTPS evidence | Done | `ssl_collector.py` |
| SEO: robots + sitemap | Done | `seo_collector.py` |
| Tech stack detection | Done | Signature-based (`tech_detector.py`) |
| Browser screenshots (desktop/mobile) | Done | Playwright (`browser_collector.py`) |
| Rendered DOM evidence | Done | Titles, meta, headings, images, etc. |
| Performance timing (LCP, resources) | Done | Collected in browser pass |
| Accessibility (axe-core) | Done | `accessibility_collector.py` |
| Rule-based findings | Done | `findings.py` → SEO / a11y / security / technical / perf |
| Crawl compare API | Done | Diff findings between crawls |
| Brain-ready evidence pack | Done | `evidence/evidence_pack.json` + `GET .../evidence-pack` |
| Content / word SEO | Done | `content_seo.py` → `seo/content.json` + findings |
| Upgrade opportunity analysis | Not started | CMS/plugin outdatedness beyond fingerprints |
| Annotated error screenshots | Done | Banner overlays on desktop shots |
| Standalone `crawler/` package | Empty folder | Still inlined in backend |

---

## Phase 2 — Scoring & dashboard

| Item | Status | Notes |
|------|--------|-------|
| Findings list + severity summary UI | Done | Basic single-page dashboard |
| Crawl vs previous comparison UI | Partial | API exists; UI has compare section |
| Heuristic category scores /10 | Done | In evidence pack (`heuristic_v1`) |
| Score cards on dashboard | Done | Overall + SEO/perf/a11y/security |
| Project / website / crawl picker | Done | Selects + localStorage persistence |
| Lighthouse / PageSpeed scores | Done | CLI when available; else local heuristic |
| Composite SEO score /10 | Done | Content SEO feeds lighthouse heuristic + findings |
| Multi-website / project picker UI | Done | Replaces hardcoded website ID |
| PDF/HTML audit report export | Partial | Proposal PDF done; full audit report later |

---

## Phase 3 — Local AI brain (free / open source)

| Item | Status | Notes |
|------|--------|-------|
| Evidence pack schema for the brain | Done | `services/evidence_pack.py` → `evidence_pack.json` |
| Ollama (or equiv.) integration | Done | User-local Ollama + `llama3.2:3b` |
| Agent tools: read evidence, write recs | Partial | Pack → recommendations endpoint (single-shot) |
| Structured recommendations output | Done | `evidence/recommendations.json` + UI panel |
| Vision model for screenshot review | Optional later | e.g. LLaVA / Qwen2-VL via Ollama |
| No paid cloud LLM dependency | Requirement | Hard constraint — met |

---

## Phase 4 — Visual redesign

| Item | Status | Notes |
|------|--------|-------|
| Local image pipeline (ComfyUI / A1111) | Deferred | Needs GPU for larger models |
| Free local TinySD (Diffusers CPU) | Done (basic) | Works; quality limited on CPU |
| GPT-quality website mock images | Parked | Future research (stronger model / GPU) |
| Concept mockup renderer (Pillow) | Done | Fallback + proposal board |
| Prompt builder from recommendations | Done | Uses brain `mockup_prompts` + actions |
| Store mockups under crawl | Done | `mockups/` + `mockups/manifest.json` |
| UI gallery of before/after concepts | Done | Generate Mockups button + gallery |

---

## Phase 5 — Business proposal

| Item | Status | Notes |
|------|--------|-------|
| Proposal template (scope, timeline, offer) | Done | `config/proposal.json` + markdown builder |
| Brain drafts proposal from audit pack | Done | Ollama narratives + structured sections |
| Attach scores, findings, mockups | Done | Embedded in markdown |
| Human edit / approve step | Partial | Edit config + markdown file; no in-UI editor yet |
| PDF export | Done | `fpdf2` → `proposal/proposal.pdf` + Export PDF button |

---

## Phase 6 — Engagement workflow

| Item | Status | Notes |
|------|--------|-------|
| Project status enum | Done | created → … → completed |
| Drive status from pipeline stages | Done | Crawl → evidence → analyzing → awaiting approval |
| Approval / implementation / verify | Done | PATCH status + dashboard advance buttons |

---

## Near-term backlog (suggested order)

1. ~~Interactive design chat MVP (brief + regenerate mockups)~~  
2. Auth / multi-tenant  
3. Production deploy  
4. Create project/website UI  
5. User screenshot upload + local vision analysis  
6. Tech stack upgrade suggestions  
7. *(Parked)* GPT-quality website mock images  

### Local brain ops

```bash
export PATH="$HOME/.local/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/.local/lib/ollama:${LD_LIBRARY_PATH:-}"
ollama serve   # if not already running
# optional: OLLAMA_IGPU_ENABLE=1 for AMD iGPU
```

API:
- `GET /api/brain/status`
- `POST/GET /api/websites/{id}/crawls/{crawl_id}/recommendations`
- `POST/GET /api/websites/{id}/crawls/{crawl_id}/mockups`
- `POST/GET /api/websites/{id}/crawls/{crawl_id}/proposal`
- `POST /api/websites/{id}/crawls/{crawl_id}/proposal/pdf`
- `GET /api/projects/{id}/workflow`
- `PATCH /api/projects/{id}/status`

Backfill existing crawls:
```bash
.venv/bin/python -m scripts.backfill_finish_artifacts
```
