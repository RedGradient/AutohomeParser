"""Хранить только актуальный таможенный расчёт каждого сценария.

Revision ID: 0006_current_customs
Revises: 0005_name_trigram_indexes
"""

from sqlalchemy import inspect

from alembic import op

revision = "0006_current_customs"
down_revision = "0005_name_trigram_indexes"
branch_labels = None
depends_on = None

TABLE_NAME = "customs_calculations"
OLD_UNIQUE_COLUMNS = (
    "spec_id",
    "importer_type",
    "calculation_date",
    "rules_version",
    "price_source",
)
NEW_UNIQUE_NAME = "uq_customs_calculations_spec_importer"
NEW_UNIQUE_COLUMNS = ("spec_id", "importer_type")

STALE_CALCULATION_IDS = """
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY spec_id, importer_type
                ORDER BY calculation_date DESC, calculated_at DESC, id DESC
            ) AS scenario_position
        FROM customs_calculations
    ) AS ranked_calculations
    WHERE scenario_position > 1
"""


def _unique_constraint_name(columns: tuple[str, ...]) -> str | None:
    """Найти имя уникального ограничения по точному набору столбцов."""
    for constraint in inspect(op.get_bind()).get_unique_constraints(TABLE_NAME):
        if tuple(constraint["column_names"]) == columns:
            return constraint["name"]
    return None


def _replace_unique_constraint(
    old_columns: tuple[str, ...],
    new_name: str,
    new_columns: tuple[str, ...],
) -> None:
    """Заменить ограничение уникальности сценария расчёта."""
    old_name = _unique_constraint_name(old_columns)
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if old_name is not None:
            batch_op.drop_constraint(old_name, type_="unique")
        batch_op.create_unique_constraint(new_name, list(new_columns))


def upgrade() -> None:
    """Удалить историю и сделать сценарий комплектации единственным."""
    op.execute(
        "DELETE FROM customs_payment_results "
        f"WHERE calculation_id IN ({STALE_CALCULATION_IDS})"
    )
    op.execute(
        f"DELETE FROM customs_calculations WHERE id IN ({STALE_CALCULATION_IDS})"
    )
    _replace_unique_constraint(
        OLD_UNIQUE_COLUMNS,
        NEW_UNIQUE_NAME,
        NEW_UNIQUE_COLUMNS,
    )


def downgrade() -> None:
    """Вернуть прежнюю уникальность без восстановления удалённой истории."""
    _replace_unique_constraint(
        NEW_UNIQUE_COLUMNS,
        "uq_customs_calculations_spec_importer_date_rules_price",
        OLD_UNIQUE_COLUMNS,
    )
