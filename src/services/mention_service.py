"""Service for managing processed mentions."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from ..orm.processed_mention import ProcessedMention
from .database import get_db_service


class MentionService:
    """Service for managing processed mentions."""

    async def is_processed(self, mention_uri: str) -> bool:
        """Check if a mention has already been processed."""
        db = get_db_service()
        async with db.session() as session:
            result = await session.execute(
                select(ProcessedMention).where(
                    ProcessedMention.mention_uri == mention_uri,
                    ProcessedMention.is_deleted == False,  # noqa: E712
                )
            )
            return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        mention_uri: str,
        author_did: str,
        author_handle: str,
        mention_text: str,
        reply_uri: Optional[str] = None,
        thread_uri: Optional[str] = None,
    ) -> ProcessedMention:
        """Mark a mention as processed."""
        db = get_db_service()
        async with db.session() as session:
            mention = ProcessedMention(
                mention_uri=mention_uri,
                author_did=author_did,
                author_handle=author_handle,
                mention_text=mention_text,
                reply_uri=reply_uri,
                thread_uri=thread_uri,
            )
            session.add(mention)
            await session.commit()
            await session.refresh(mention)
            return mention

    async def cleanup_old_mentions(self, days: int = 30):
        """Clean up mentions older than N days (soft delete)."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with db.session() as session:
            result = await session.execute(
                select(ProcessedMention).where(
                    ProcessedMention.created_at < cutoff,
                    ProcessedMention.is_deleted == False,  # noqa: E712
                )
            )
            old_mentions = result.scalars().all()
            for mention in old_mentions:
                mention.is_deleted = True
            await session.commit()
