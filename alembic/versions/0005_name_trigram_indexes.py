"""Добавить trigram-индексы для поиска по названиям.

Revision ID: 0005_name_trigram_indexes
Revises: 0004_api_filter_indexes
"""

from alembic import op

revision = "0005_name_trigram_indexes"
down_revision = "0004_api_filter_indexes"
branch_labels = None
depends_on = None

TRIGRAM_INDEXES = (
    ("ix_brands_name_lower_trgm", "brands"),
    ("ix_manufacturers_name_lower_trgm", "manufacturers"),
    ("ix_series_name_lower_trgm", "series"),
    ("ix_specs_name_lower_trgm", "specs"),
)


def upgrade() -> None:
    """Включить pg_trgm и создать GIN-индексы без блокировки таблиц."""
    if op.get_bind().dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for index_name, table_name in TRIGRAM_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} "
                f"ON {table_name} USING gin (lower(name) gin_trgm_ops)"
            )


def downgrade() -> None:
    """Удалить trigram-индексы, сохранив расширение для других потребителей."""
    if op.get_bind().dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        for index_name, _ in reversed(TRIGRAM_INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
