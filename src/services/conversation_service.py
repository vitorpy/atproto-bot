"""Service for managing conversation history."""

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import func, select

from ..orm.conversation import ConversationHistory
from .database import get_db_service


class ConversationService:
    """Service for managing conversation history."""

    async def store_conversation_turn(
        self,
        thread_uri: str,
        mention_id: str,
        user_message: str,
        assistant_message: str,
        author_did: str,
        user_post_uri: str,
        assistant_post_uri: str,
    ) -> tuple[ConversationHistory, ConversationHistory]:
        """Store a conversation turn (user message + assistant response)."""
        db = get_db_service()
        async with db.session() as session:
            # Get next sequence IDs
            max_seq_result = await session.execute(
                select(func.max(ConversationHistory.sequence_id))
            )
            max_seq = max_seq_result.scalar() or 0

            user_entry = ConversationHistory(
                thread_uri=thread_uri,
                mention_id=mention_id,
                role="user",
                content=user_message,
                author_did=author_did,
                post_uri=user_post_uri,
                sequence_id=max_seq + 1,
            )

            assistant_entry = ConversationHistory(
                thread_uri=thread_uri,
                mention_id=mention_id,
                role="assistant",
                content=assistant_message,
                author_did=None,  # Bot doesn't have DID in this context
                post_uri=assistant_post_uri,
                sequence_id=max_seq + 2,
            )

            session.add(user_entry)
            session.add(assistant_entry)
            await session.commit()
            await session.refresh(user_entry)
            await session.refresh(assistant_entry)

            return user_entry, assistant_entry

    async def get_thread_history(
        self, thread_uri: str, limit: int = 20
    ) -> List[ConversationHistory]:
        """Get conversation history for a thread."""
        db = get_db_service()
        async with db.session() as session:
            result = await session.execute(
                select(ConversationHistory)
                .where(
                    ConversationHistory.thread_uri == thread_uri,
                    ConversationHistory.is_deleted == False,  # noqa: E712
                )
                .order_by(ConversationHistory.sequence_id.desc())
                .limit(limit)
            )
            history = result.scalars().all()
            return list(reversed(history))  # Oldest first

    async def cleanup_old_history(self, days: int = 90):
        """Clean up conversation history older than N days."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with db.session() as session:
            result = await session.execute(
                select(ConversationHistory).where(
                    ConversationHistory.created_at < cutoff,
                    ConversationHistory.is_deleted == False,  # noqa: E712
                )
            )
            old_entries = result.scalars().all()
            for entry in old_entries:
                entry.is_deleted = True
            await session.commit()
