"""Commercial Opportunity — bridge between findings and proposals."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OpportunityStatus(str, enum.Enum):
    NEW = "new"
    REVIEW = "review"
    APPROVED = "approved"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    SOLD = "sold"
    COMPLETED = "completed"
    VERIFIED = "verified"


class ProposalItemStatus(str, enum.Enum):
    NOT_IN_PROPOSAL = "not_in_proposal"
    SELECTED = "selected"
    INCLUDED = "included"


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    website_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    crawl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_finding_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_cluster_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    client_title: Mapped[str] = mapped_column(String(255), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    business_impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)

    # commercial / UX / content / technical / complexity — each 0–5
    impact_business: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_ux: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_content: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_technical: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scope_complexity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category: Mapped[str] = mapped_column(String(50), default="technical", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    estimated_effort: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    estimated_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, name="opportunity_status", values_callable=lambda e: [x.value for x in e]),
        default=OpportunityStatus.NEW,
        nullable=False,
    )
    proposal_status: Mapped[ProposalItemStatus] = mapped_column(
        Enum(ProposalItemStatus, name="proposal_item_status", values_callable=lambda e: [x.value for x in e]),
        default=ProposalItemStatus.NOT_IN_PROPOSAL,
        nullable=False,
    )
    selected_package: Mapped[str | None] = mapped_column(String(50), nullable=True)
    theme_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
