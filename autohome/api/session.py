from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = (
    f"sqlite:///{(PROJECT_ROOT / 'data' / 'autohome.sqlite3').resolve()}"
)


def async_database_url(database_url: str) -> str:
    """Преобразовать синхронный URL SQLite в URL асинхронного драйвера."""
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return database_url


class DatabaseSessionManager:
    """Управлять асинхронным движком, пулом и сессиями API."""

    def __init__(self, database_url: str | None = None):
        url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.engine: AsyncEngine = create_async_engine(
            async_database_url(url), pool_pre_ping=True
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Выдать отдельную асинхронную сессию на время HTTP-запроса."""
        async with self.session_factory() as session:
            yield session
