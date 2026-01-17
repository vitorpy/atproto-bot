"""ORM model for tracking processed PR comments."""

from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class PRComment(SqlalchemyBase):
    """Track processed PR comments to prevent duplicate processing."""

    __tablename__ = "pr_comments"
    __table_args__ = (
        Index("idx_pr_comment_comment_id", "comment_id", unique=True),
        Index("idx_pr_comment_pr_number", "pr_number"),
        Index("idx_pr_comment_processed", "processed"),
        Index("idx_pr_comment_created_at", "created_at"),
    )

    # PR and comment identifiers
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    comment_id: Mapped[int] = mapped_column(Integer, nullable=False)  # GitHub comment ID
    comment_body: Mapped[str] = mapped_column(Text, nullable=False)
    commenter_login: Mapped[str] = mapped_column(String, nullable=False)

    # Processing state
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Link to original self-improvement request (if applicable)
    selfimprovement_request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<PRComment(id={self.id}, pr_number={self.pr_number}, "
            f"comment_id={self.comment_id}, commenter={self.commenter_login}, "
            f"processed={self.processed})>"
        )
