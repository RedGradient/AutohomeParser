"""Переименовать область применения цвета.

Revision ID: 0002_rename_color_type
Revises: 0001_existing_schema
"""

from sqlalchemy import inspect

from alembic import op

revision = "0002_rename_color_type"
down_revision = "0001_existing_schema"
branch_labels = None
depends_on = None

TABLES = (
    "series_gallery_colors",
    "series_photo_colors",
    "gallery_crawl_tasks",
)


def _rename_if_present(old_name: str, new_name: str) -> None:
    """Переименовать столбец, если база ещё содержит старое имя."""
    inspector = inspect(op.get_bind())
    table_names = set(inspector.get_table_names())
    for table_name in TABLES:
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if old_name in columns and new_name not in columns:
            op.alter_column(table_name, old_name, new_column_name=new_name)


def upgrade() -> None:
    """Переименовать color_type в color_scope."""
    _rename_if_present("color_type", "color_scope")


def downgrade() -> None:
    """Вернуть прежнее имя color_type."""
    _rename_if_present("color_scope", "color_type")
