from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.database import engine, settings
from backend.app.models import Base, Company, Opportunity  # noqa: F401 — register models
from backend.app.routes import agency, companies, crawls, projects, website_detail, websites
from backend.app.services.brain import ollama_available
from backend.app.services.schema_migrate import (
    ensure_company_schema,
    ensure_website_role_schema,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FRONTEND_SRC = ROOT / "frontend"
FRONTEND_DIST = FRONTEND_SRC / "dist"
FRONTEND_DIR = FRONTEND_DIST

DATA_DIR.mkdir(exist_ok=True)
FRONTEND_SRC.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.app.services.playwright_env import ensure_playwright_browsers_path

    ensure_playwright_browsers_path()
    Base.metadata.create_all(bind=engine)
    ensure_company_schema(engine)
    ensure_website_role_schema(engine)
    yield


app = FastAPI(
    title="Aurelia API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "website-intelligence-api",
    }


@app.get("/api/brain/status")
def brain_status():
    from backend.app.services.image_gen import diffusion_available
    from backend.app.services.llm_client import provider_status

    status = provider_status()
    ollama = status.get("ollama") or {}
    image = diffusion_available()
    return {
        "ok": status.get("ok"),
        "provider": status.get("provider"),
        "configured_model": status.get("configured_model"),
        "model_ready": status.get("model_ready"),
        "error": status.get("error"),
        "models": ollama.get("models") or [],
        "base_url": ollama.get("base_url") or settings.ollama_base_url,
        "openai": status.get("openai"),
        "anthropic": status.get("anthropic"),
        "ollama": ollama,
        "image_generation": {
            **image,
            "backend_setting": settings.mockup_backend,
            "model_id": settings.image_model_id,
        },
    }


app.include_router(companies.router)
app.include_router(projects.router)
app.include_router(websites.router)
app.include_router(website_detail.router)
app.include_router(crawls.router)
app.include_router(agency.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


# Local development only: exposes saved evidence (screenshots, HTML).
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

if (FRONTEND_DIST / "index.html").exists():
    def _app_index():
        # Prevent browsers from caching an old index.html after rebuilds.
        return FileResponse(
            FRONTEND_DIST / "index.html",
            media_type="text/html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    app.mount(
        "/app/assets",
        StaticFiles(directory=FRONTEND_DIR / "assets"),
        name="app-assets",
    )

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    def app_index(path: str = ""):
        # Client-side routes (/app/sites, /app/audit, ...) all serve the SPA.
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return _app_index()
else:
    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    def frontend_not_built():
        return {
            "error": "Frontend not built",
            "hint": "cd frontend && npm install && npm run build",
            "dev": "cd frontend && npm run dev  →  http://127.0.0.1:5173/app/",
        }
