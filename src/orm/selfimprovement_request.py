"""ORM model for self-improvement requests."""

from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class SelfImprovementRequest(SqlalchemyBase):
    """Track self-improvement command executions."""

    __tablename__ = "selfimprovement_requests"
    __table_args__ = (
        Index("idx_selfimprovement_requester_did", "requester_did"),
        Index("idx_selfimprovement_conversation_id", "conversation_id"),
        Index("idx_selfimprovement_created_at", "created_at"),
    )

    # Request details
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    requester_did: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Git/GitHub details
    branch_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Performance metrics
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<SelfImprovementRequest(id={self.id}, requester={self.requester_did}, "
            f"success={self.success}, pr_number={self.pr_number})>"
        )
