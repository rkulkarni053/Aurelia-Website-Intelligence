"""Agency settings API — branding, packages, proposal defaults."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.agency_settings import (
    load_agency_settings,
    save_agency_settings,
)

router = APIRouter(prefix="/api/agency", tags=["agency"])


class AgencySettingsPatch(BaseModel):
    branding: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    currency: str | None = None
    packages: dict[str, Any] | None = None
    add_ons: dict[str, Any] | None = None
    out_of_scope_defaults: list[str] | None = None
    recommended_package_default: str | None = None


@router.get("/settings")
def get_agency_settings():
    return load_agency_settings()


@router.patch("/settings")
def patch_agency_settings(payload: AgencySettingsPatch):
    data = payload.model_dump(exclude_none=True)
    return save_agency_settings(data)


@router.put("/settings")
def put_agency_settings(payload: dict[str, Any]):
    return save_agency_settings(payload or {})
