import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    company_id: uuid.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    company_id: uuid.UUID | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
