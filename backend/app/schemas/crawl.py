import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.models.crawl import CrawlStatus


class CrawlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    website_id: uuid.UUID
    status: CrawlStatus
    pages_discovered: int
    pages_crawled: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
