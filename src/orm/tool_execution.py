"""ToolExecution model for tracking tool usage."""

from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class ToolExecution(SqlalchemyBase):
    """Track tool executions for debugging and monitoring."""

    __tablename__ = "tool_executions"
    __table_args__ = (
        Index("idx_tool_executions_conversation", "conversation_id"),
        Index("idx_tool_executions_tool_name", "tool_name"),
        Index("idx_tool_executions_created_at", "created_at"),
    )

    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String, nullable=False)
    input_args: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    output_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Token tracking for cost analysis
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_creation_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_read_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Extended thinking content for debugging
    thinking_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
