"""ProcessedDM model for tracking processed direct messages."""

from typing import Optional

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import SqlalchemyBase


class ProcessedDM(SqlalchemyBase):
    """Track processed DMs to prevent duplicate replies."""

    __tablename__ = "processed_dms"
    __table_args__ = (
        Index("idx_processed_dms_message_id", "message_id", unique=True),
        Index("idx_processed_dms_convo_id", "convo_id"),
        Index("idx_processed_dms_created_at", "created_at"),
    )

    convo_id: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    sender_did: Mapped[str] = mapped_column(String, nullable=False)
    sender_handle: Mapped[str] = mapped_column(String, nullable=False)
    message_text: Mapped[str] = mapped_column(String, nullable=False)
    reply_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
