import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    crawl_id: uuid.UUID
    code: str
    severity: str
    category: str
    title: str
    description: str
    url: str | None
    evidence_file: str | None
    detail: dict | None
    created_at: datetime
