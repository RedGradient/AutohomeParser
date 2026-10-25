"""Запуск Alembic и проверка версии схемы базы данных."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


class DatabaseSchemaError(RuntimeError):
    """Схема базы отсутствует или не соответствует текущим миграциям."""


def alembic_config(database_url: str | None = None) -> Config:
    """Создать конфигурацию Alembic для проекта и указанной базы."""
    config = Config(str(ALEMBIC_INI))
    if database_url is not None:
        config.attributes["database_url"] = database_url
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_database(database_url: str) -> None:
    """Применить к базе все миграции вплоть до текущего head."""
    command.upgrade(alembic_config(database_url), "head")


def require_current_schema(engine: Engine) -> None:
    """Убедиться, что версия схемы базы совпадает с Alembic head."""
    config = alembic_config()
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    with engine.connect() as connection:
        actual_heads = set(MigrationContext.configure(connection).get_current_heads())
    if actual_heads == expected_heads:
        return

    if not actual_heads:
        actual = "не инициализирована"
    else:
        actual = ", ".join(sorted(actual_heads))
    expected = ", ".join(sorted(expected_heads))
    raise DatabaseSchemaError(
        "Схема базы данных не подготовлена миграциями Alembic "
        f"(текущая версия: {actual}; требуется: {expected}). "
        "Выполните `alembic upgrade head` и повторите запуск."
    )


def require_current_database(database_url: str) -> None:
    """Подключиться к базе и проверить соответствие схемы Alembic head."""
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        require_current_schema(engine)
    finally:
        engine.dispose()
