"""Service for managing processed DMs."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from ..orm.processed_dm import ProcessedDM
from .database import get_db_service


class DMService:
    """Service for managing processed direct messages."""

    async def is_processed(self, message_id: str) -> bool:
        """Check if a DM has already been processed."""
        db = get_db_service()
        async with db.session() as session:
            result = await session.execute(
                select(ProcessedDM).where(
                    ProcessedDM.message_id == message_id,
                    ProcessedDM.is_deleted == False,  # noqa: E712
                )
            )
            return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        convo_id: str,
        message_id: str,
        sender_did: str,
        sender_handle: str,
        message_text: str,
        reply_message_id: Optional[str] = None,
    ) -> ProcessedDM:
        """Mark a DM as processed."""
        db = get_db_service()
        async with db.session() as session:
            dm = ProcessedDM(
                convo_id=convo_id,
                message_id=message_id,
                sender_did=sender_did,
                sender_handle=sender_handle,
                message_text=message_text,
                reply_message_id=reply_message_id,
            )
            session.add(dm)
            await session.commit()
            await session.refresh(dm)
            return dm

    async def cleanup_old_dms(self, days: int = 30):
        """Clean up DMs older than N days (soft delete)."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with db.session() as session:
            result = await session.execute(
                select(ProcessedDM).where(
                    ProcessedDM.created_at < cutoff,
                    ProcessedDM.is_deleted == False,  # noqa: E712
                )
            )
            old_dms = result.scalars().all()
            for dm in old_dms:
                dm.is_deleted = True
            await session.commit()
