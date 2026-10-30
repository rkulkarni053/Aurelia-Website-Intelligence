import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


WebsiteRole = Literal["primary", "competitor"]


class WebsiteCreate(BaseModel):
    url: HttpUrl
    role: WebsiteRole = "primary"


class WebsiteUpdate(BaseModel):
    url: HttpUrl | None = None
    role: WebsiteRole | None = None


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    url: str
    domain: str
    role: str = "primary"
    created_at: datetime
