from pathlib import Path
import re
import uuid

DATA_ROOT = Path("data/websites")

CRAWL_SUBDIRS = [
    "html",
    "screenshots",
    "assets",
    "network",
    "ssl",
    "seo",
    "technologies",
    "evidence",
    "mockups",
    "demo",
    "proposal",
    "lighthouse",
    "design",
    "reports",
    "reports/siteone",
]


def get_crawl_root(domain: str, crawl_id: uuid.UUID) -> Path:
    return DATA_ROOT / domain / "crawls" / str(crawl_id)


def ensure_crawl_directories(domain: str, crawl_id: uuid.UUID) -> Path:
    root = get_crawl_root(domain, crawl_id)
    for name in CRAWL_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def slugify_url(url: str) -> str:
    slug = re.sub(r"^https?://", "", url)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-")
    return slug[:100] or "home"
