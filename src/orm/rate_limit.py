"""RateLimitEvent model for tracking rate limit events."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class RateLimitEvent(SqlalchemyBase):
    """Track rate limit events for users."""

    __tablename__ = "rate_limit_events"
    __table_args__ = (
        Index("idx_rate_limit_user_did_timestamp", "user_did", "event_timestamp"),
        Index("idx_rate_limit_event_timestamp", "event_timestamp"),
    )

    user_did: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mention_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
