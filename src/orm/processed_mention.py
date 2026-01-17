"""ProcessedMention model for tracking processed mentions."""

from typing import Optional

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class ProcessedMention(SqlalchemyBase):
    """Track processed mentions to prevent duplicate replies."""

    __tablename__ = "processed_mentions"
    __table_args__ = (
        Index("idx_processed_mentions_mention_uri", "mention_uri", unique=True),
        Index("idx_processed_mentions_author_did", "author_did"),
        Index("idx_processed_mentions_created_at", "created_at"),
    )

    mention_uri: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    author_did: Mapped[str] = mapped_column(String, nullable=False)
    author_handle: Mapped[str] = mapped_column(String, nullable=False)
    mention_text: Mapped[str] = mapped_column(String, nullable=False)
    reply_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thread_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
