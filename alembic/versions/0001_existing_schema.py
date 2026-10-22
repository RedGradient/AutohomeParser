"""Зафиксировать существующую схему как отправную точку.

Revision ID: 0001_existing_schema
Revises: None
"""

from alembic import op

from autohome.models import Base


revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать актуальные таблицы только в пустой базе."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Не удалять существующую пользовательскую базу при откате baseline."""
    pass
