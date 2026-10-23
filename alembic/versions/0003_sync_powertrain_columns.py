"""Дополнить старые схемы нормализованными полями силовой установки.

Revision ID: 0003_sync_powertrain_columns
Revises: 0002_rename_color_type
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0003_sync_powertrain_columns"
down_revision = "0002_rename_color_type"
branch_labels = None
depends_on = None

TABLES = ("modifications", "spec_powertrains")


def _columns() -> tuple[sa.Column, ...]:
    """Создать независимый набор добавляемых столбцов."""
    return (
        sa.Column("engine_power_hp", sa.Numeric(12, 3), nullable=True),
        sa.Column("clutch_type", sa.String(30), nullable=True),
        sa.Column("engine_layout", sa.String(30), nullable=True),
        sa.Column("aspiration_type", sa.String(50), nullable=True),
        sa.Column("cylinder_layout", sa.String(30), nullable=True),
        sa.Column("body_type", sa.String(50), nullable=True),
        sa.Column("motor_total_power_hp", sa.Numeric(12, 3), nullable=True),
        sa.Column("system_power_hp", sa.Numeric(12, 3), nullable=True),
    )


def upgrade() -> None:
    """Добавить отсутствующие столбцы и индексы в старые базы."""
    connection = op.get_bind()
    table_names = set(inspect(connection).get_table_names())
    indexed_columns = (
        "clutch_type",
        "engine_layout",
        "aspiration_type",
        "cylinder_layout",
        "body_type",
    )

    for table_name in TABLES:
        if table_name not in table_names:
            continue
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns(table_name)
        }
        for column in _columns():
            if column.name not in existing_columns:
                op.add_column(table_name, column)

        existing_indexes = {
            index["name"] for index in inspect(connection).get_indexes(table_name)
        }
        for column_name in indexed_columns:
            index_name = f"ix_{table_name}_{column_name}"
            if index_name not in existing_indexes:
                op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    """Не удалять совместимые поля со схем, где они появились до миграции."""
