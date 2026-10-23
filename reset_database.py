from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from autohome.models import Base

PROTECTED_DATABASES = {"postgres", "template0", "template1"}


def parse_arguments() -> argparse.Namespace:
    """Разобрать адрес базы и обязательное подтверждение удаления."""
    parser = argparse.ArgumentParser(
        description=(
            "Удалить целевую PostgreSQL целиком, создать её заново и "
            "развернуть актуальные таблицы SQLAlchemy."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL целевой PostgreSQL; по умолчанию DATABASE_URL.",
    )
    parser.add_argument(
        "--maintenance-database",
        default="postgres",
        help="Служебная база для DROP/CREATE DATABASE; по умолчанию postgres.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить безвозвратное удаление целевой базы со всеми данными.",
    )
    return parser.parse_args()


def validate_target(database_url: str, maintenance_database: str):
    """Проверить, что удаляется обычная PostgreSQL, а не служебная база."""
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Скрипт поддерживает только PostgreSQL")
    if not url.database:
        raise SystemExit("В DATABASE_URL не указано имя целевой базы")
    if url.database in PROTECTED_DATABASES:
        raise SystemExit(f"Удаление служебной базы {url.database!r} запрещено")
    if maintenance_database == url.database:
        raise SystemExit("Служебная и целевая базы должны отличаться")
    return url


def recreate_database(database_url: str, maintenance_database: str) -> str:
    """Удалить целевую базу, создать пустую и развернуть все таблицы."""
    target_url = validate_target(database_url, maintenance_database)
    database_name = target_url.database
    maintenance_url = target_url.set(database=maintenance_database)

    maintenance_engine = create_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        quoted_name = maintenance_engine.dialect.identifier_preparer.quote(
            database_name
        )
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)"
            )
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
    finally:
        maintenance_engine.dispose()

    target_engine = create_engine(target_url, pool_pre_ping=True)
    try:
        Base.metadata.create_all(target_engine)
    finally:
        target_engine.dispose()
    return database_name


def main() -> int:
    """Проверить подтверждение и полностью пересоздать целевую базу."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if not args.yes:
        raise SystemExit("Добавьте --yes для подтверждения удаления всей базы")

    database_name = recreate_database(
        args.database_url,
        args.maintenance_database,
    )
    print(
        f"База {database_name!r} пересоздана; "
        f"создано таблиц: {len(Base.metadata.tables)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
