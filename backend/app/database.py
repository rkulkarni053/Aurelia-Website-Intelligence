from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Settings(BaseSettings):
    database_url: str
    # Brain provider: ollama (local free) | openai | anthropic
    brain_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 300.0
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_base_url: str = "https://api.anthropic.com"
    # concept = instant Pillow boards (default). auto/ai = slow TinySD on CPU.
    mockup_backend: str = "concept"
    image_model_id: str = "segmind/tiny-sd"
    image_steps: int = 8
    image_size: int = 512
    # Full-site crawl coverage (WordPress / static HTML / JS SPAs)
    crawl_max_pages: int = 500
    crawl_max_browser_pages: int = 40
    crawl_max_content_pages: int = 200
    crawl_max_lighthouse_pages: int = 5
    crawl_siteone_max_urls: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
