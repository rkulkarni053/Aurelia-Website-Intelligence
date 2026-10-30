import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    crawl_id: uuid.UUID
    url: str
    status_code: int
    title: str | None
    html_file: str | None
    rendered_html_file: str | None
    desktop_screenshot: str | None
    mobile_screenshot: str | None
    created_at: datetime
