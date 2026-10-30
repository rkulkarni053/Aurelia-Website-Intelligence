import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    crawl_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rendered_html_file: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    desktop_screenshot: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    mobile_screenshot: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    crawl = relationship("Crawl", back_populates="pages")
