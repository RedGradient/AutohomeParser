from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_DATABASE_URL = "postgresql+psycopg://autohome:autohome@127.0.0.1:5432/autohome"


class DatabaseSessionManager:
    """Управлять асинхронным движком, пулом и сессиями API."""

    def __init__(self, database_url: str | None = None):
        url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Выдать отдельную асинхронную сессию на время HTTP-запроса."""
        async with self.session_factory() as session:
            yield session
