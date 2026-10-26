"""Изолированные PostgreSQL-схемы для интеграционных тестов."""

from __future__ import annotations

import os
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://autohome:autohome@127.0.0.1:5432/autohome"
)


class PostgreSQLTestSchema:
    """Создать временную схему и URL с настроенным search_path."""

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "TEST_DATABASE_URL",
            os.getenv("DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
        )
        self.schema = f"test_{uuid.uuid4().hex}"
        url = make_url(self.base_url).update_query_dict(
            {"options": f"-csearch_path={self.schema}"}
        )
        self.database_url = url.render_as_string(hide_password=False)

    def create(self) -> PostgreSQLTestSchema:
        """Создать пустую тестовую схему."""
        engine = create_engine(self.base_url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as connection:
                connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        finally:
            engine.dispose()
        return self

    def drop(self) -> None:
        """Удалить тестовую схему вместе со всеми объектами."""
        engine = create_engine(self.base_url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as connection:
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
                )
        finally:
            engine.dispose()

    def create_engine(self):
        """Создать синхронный engine внутри тестовой схемы."""
        return create_engine(self.database_url)
