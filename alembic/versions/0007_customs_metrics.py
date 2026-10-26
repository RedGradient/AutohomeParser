"""Добавить актуальный снимок метрик таможенных расчётов.

Revision ID: 0007_customs_metrics
Revises: 0006_current_customs
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_customs_metrics"
down_revision = "0006_current_customs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать таблицу единственного актуального снимка метрик."""
    op.create_table(
        "customs_metrics",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("brands_count", sa.BigInteger(), nullable=False),
        sa.Column("series_count", sa.BigInteger(), nullable=False),
        sa.Column("specs_count", sa.BigInteger(), nullable=False),
        sa.Column("modifications_count", sa.BigInteger(), nullable=False),
        sa.Column("customs_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column("complete_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column("partial_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column("missing_data_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column("manual_review_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column("unsupported_scenarios_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "specs_with_complete_scenario_count",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "missing_data_statistics_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()),
                "postgresql",
            ),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_customs_metrics_singleton"),
        sa.CheckConstraint(
            "brands_count >= 0 AND series_count >= 0 "
            "AND specs_count >= 0 AND modifications_count >= 0 "
            "AND customs_scenarios_count >= 0 "
            "AND complete_scenarios_count >= 0 "
            "AND partial_scenarios_count >= 0 "
            "AND missing_data_scenarios_count >= 0 "
            "AND manual_review_scenarios_count >= 0 "
            "AND unsupported_scenarios_count >= 0 "
            "AND specs_with_complete_scenario_count >= 0",
            name="ck_customs_metrics_nonnegative_counts",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Удалить снимок таможенных метрик."""
    op.drop_table("customs_metrics")
