"""ORM model for tracking PR improvement iterations."""

from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class PRIteration(SqlalchemyBase):
    """Track iterative improvements made to PRs via comment feedback."""

    __tablename__ = "pr_iterations"
    __table_args__ = (
        Index("idx_pr_iteration_pr_number", "pr_number"),
        Index("idx_pr_iteration_comment_id", "comment_id"),
        Index("idx_pr_iteration_success", "success"),
        Index("idx_pr_iteration_created_at", "created_at"),
    )

    # PR and iteration identifiers
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    comment_id: Mapped[int] = mapped_column(Integer, nullable=False)  # GitHub comment ID
    comment_body: Mapped[str] = mapped_column(Text, nullable=False)

    # Git details
    commit_sha: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Performance metrics
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<PRIteration(id={self.id}, pr_number={self.pr_number}, "
            f"iteration={self.iteration_number}, success={self.success}, "
            f"commit_sha={self.commit_sha[:8] if self.commit_sha else None})>"
        )
