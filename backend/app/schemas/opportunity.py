from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    website_id: uuid.UUID | None = None
    crawl_id: uuid.UUID
    source_finding_ids: list[Any] | None = None
    source_cluster_ids: list[Any] | None = None
    title: str
    client_title: str
    problem: str
    evidence: dict[str, Any] | None = None
    business_impact: str
    recommendation: str
    impact_business: int = 0
    impact_ux: int = 0
    impact_content: int = 0
    impact_technical: int = 0
    scope_complexity: int = 0
    category: str = "technical"
    priority: str = "medium"
    estimated_effort: str = "medium"
    estimated_value: float | None = None
    status: str
    proposal_status: str
    selected_package: str | None = None
    theme_key: str | None = None
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0
    commercial_score: int = 0


class OpportunityPatch(BaseModel):
    status: str | None = None
    proposal_status: str | None = None
    selected_package: str | None = None
    title: str | None = None
    client_title: str | None = None
    problem: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    priority: str | None = None
    estimated_effort: str | None = None
    estimated_value: float | None = None


class SellRecommendationOut(BaseModel):
    recommended_package: str
    package_name: str
    price: float | None = None
    currency: str = "EUR"
    duration_days: int | None = None
    summary: str = ""
    why: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    commercial_score: dict[str, Any] = Field(default_factory=dict)
    opportunity_counts: dict[str, int] = Field(default_factory=dict)
    accepted: bool = False
    packages: dict[str, Any] = Field(default_factory=dict)


class SellAcceptIn(BaseModel):
    package: str | None = None
    customize: bool = False
