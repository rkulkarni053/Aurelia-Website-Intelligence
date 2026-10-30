# Aurelia — Website Intelligence

Local-first agency workspace: **crawl → understand the company → Brain recommendations → Design chat + live HTML demo → concept boards → priced proposal**.

## Documentation

Full system documentation (architecture, pipelines, APIs, config, design decisions):

**[docs/PROJECT_DOCUMENTATION.md](./docs/PROJECT_DOCUMENTATION.md)**

Also:

- [Product requirements](./docs/PRODUCT_REQUIREMENTS.md)
- [Project tracker](./docs/PROJECT_TRACKER.md)
- [Earlier status report](./docs/STATUS_REPORT.md)

## Quick start

```bash
docker compose up -d
# Configure .env (DATABASE_URL, OLLAMA_*, MOCKUP_BACKEND=concept)

source .venv/bin/activate
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

cd frontend && npm install && npm run build
# App: http://127.0.0.1:8000/app/
```

Requires Postgres (Compose), optional [Ollama](https://ollama.com) with `qwen2.5:7b`, and Playwright browsers for crawl/demo previews.

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI (`Aurelia API`) |
| UI | React 19 + Vite |
| DB | PostgreSQL 18 |
| Local LLM | Ollama (`qwen2.5:7b` default) |
| Demos | Generated HTML + Playwright |
| Mockups | Pillow concept boards (default) |
