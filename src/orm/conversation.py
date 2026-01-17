"""ConversationHistory model for storing conversation history."""

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class ConversationHistory(SqlalchemyBase):
    """Store conversation history for context-aware responses."""

    __tablename__ = "conversation_history"
    __table_args__ = (
        Index("idx_conversation_thread_uri", "thread_uri"),
        Index("idx_conversation_created_at", "created_at"),
        Index("idx_conversation_sequence", "sequence_id", unique=True),
        Index("idx_conversation_mention_id", "mention_id"),
    )

    thread_uri: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mention_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("processed_mentions.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(String, nullable=False)
    author_did: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    post_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sequence_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
