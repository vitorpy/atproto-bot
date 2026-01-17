"""Database connection and session management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..orm.base import Base


class DatabaseService:
    """Manages database connection and session lifecycle."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # Create async SQLite engine
        db_url = f"sqlite+aiosqlite:///{self.database_path}"
        self.engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
        )

        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    async def initialize(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope for database operations."""
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """Close database engine."""
        await self.engine.dispose()


# Global database service instance
db_service: DatabaseService | None = None


def get_db_service() -> DatabaseService:
    """Get the global database service instance."""
    if db_service is None:
        raise RuntimeError("Database service not initialized")
    return db_service


async def init_db_service(database_path: str | Path) -> DatabaseService:
    """Initialize the global database service."""
    global db_service
    db_service = DatabaseService(database_path)
    await db_service.initialize()
    return db_service
