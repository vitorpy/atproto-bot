"""Service for managing rate limits."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from ..orm.rate_limit import RateLimitEvent
from .database import get_db_service


class RateLimitService:
    """Service for managing rate limits."""

    def __init__(self, max_per_hour: int):
        self.max_per_hour = max_per_hour

    async def is_allowed(self, user_did: str) -> bool:
        """Check if a user is within rate limits."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

        async with db.session() as session:
            result = await session.execute(
                select(func.count(RateLimitEvent.id)).where(
                    RateLimitEvent.user_did == user_did,
                    RateLimitEvent.event_timestamp > cutoff,
                    RateLimitEvent.is_deleted == False,  # noqa: E712
                )
            )
            count = result.scalar_one()
            return count < self.max_per_hour

    async def record_request(self, user_did: str, mention_uri: Optional[str] = None):
        """Record a rate limit event."""
        db = get_db_service()
        async with db.session() as session:
            event = RateLimitEvent(
                user_did=user_did,
                event_timestamp=datetime.now(timezone.utc),
                mention_uri=mention_uri,
            )
            session.add(event)
            await session.commit()

    async def get_remaining(self, user_did: str) -> int:
        """Get remaining requests for a user."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

        async with db.session() as session:
            result = await session.execute(
                select(func.count(RateLimitEvent.id)).where(
                    RateLimitEvent.user_did == user_did,
                    RateLimitEvent.event_timestamp > cutoff,
                    RateLimitEvent.is_deleted == False,  # noqa: E712
                )
            )
            count = result.scalar_one()
            return max(0, self.max_per_hour - count)

    async def cleanup_old_events(self, days: int = 7):
        """Clean up rate limit events older than N days."""
        db = get_db_service()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with db.session() as session:
            result = await session.execute(
                select(RateLimitEvent).where(
                    RateLimitEvent.event_timestamp < cutoff,
                    RateLimitEvent.is_deleted == False,  # noqa: E712
                )
            )
            old_events = result.scalars().all()
            for event in old_events:
                event.is_deleted = True
            await session.commit()
