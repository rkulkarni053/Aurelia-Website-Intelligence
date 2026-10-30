import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Website(Base):
    __tablename__ = "websites"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "domain",
            name="uq_websites_project_domain",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # primary | competitor — competitors share a project with the client site.
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="primary",
        server_default="primary",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship(
        "Project",
        back_populates="websites",
    )

    crawls = relationship(
        "Crawl",
        back_populates="website",
        cascade="all, delete-orphan",
    )
