# Website Intelligence — Product Requirements (owner intent)

Last updated: 2026-10-05

## North star

Use Website Intelligence as the **only source / daily workspace for the business** — not just a one-shot audit tool.

## Required product shape

1. **Interactive design agent (primary)**
   - Chat with the AI about a site/project
   - State changes in natural language (e.g. “make hero navy/gold”, “bigger CTA”)
   - AI updates a design brief and **regenerates mockup images**
   - Conversation history persisted per website/crawl

2. **Site story understanding**
   - AI must know what the business is about from crawled Home/About/Services copy
   - Recommendations and design changes must be grounded in that story

3. **Audit brain (intake)**
   - Crawl → SEO (tech + content) → SSL → tech stack → scores → findings
   - Annotated screenshots of issues
   - Local free OSS brain (Ollama: Llama / Qwen / Gemma / DeepSeek — no paid APIs)

4. **Screenshot analysis (planned)**
   - User provides a screenshot and asks for changes
   - Needs local vision model later (e.g. LLaVA / Qwen2.5-VL via Ollama)

5. **Image generation**
   - Local only (TinySD / Diffusers / Pillow concepts)
   - Driven by chat + design brief, not only one-shot buttons

6. **Tech stack**
   - Detect today; later: suggest upgrades / migrations

7. **Business proposal**
   - Markdown + PDF from audit + story + mockups

8. **Hard constraint**
   - Free / open-source / local — no paid Claude/GPT/Gemini/Perplexity APIs unless explicitly reconsidered

## Launch blockers (still open)

- Auth / multi-tenant
- Production deploy
- Create project/website UI

## Explicitly out of MVP chat loop

- Multi-user auth
- Live CSS/code editing of client sites
- GPT-quality Figma-level mockups (parked until stronger GPU/model)
