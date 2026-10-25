"""Добавить B-tree индексы для фильтров и сортировки API.

Revision ID: 0004_api_filter_indexes
Revises: 0003_sync_powertrain_columns
"""

from sqlalchemy import inspect

from alembic import op

revision = "0004_api_filter_indexes"
down_revision = "0003_sync_powertrain_columns"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_series_brand_name_id", "series", ("brand_id", "name", "id")),
    (
        "ix_series_manufacturer_name_id",
        "series",
        ("manufacturer_id", "name", "id"),
    ),
    ("ix_specs_series_year_id", "specs", ("series_id", "year", "id")),
    (
        "ix_specs_modification_id_id",
        "specs",
        ("modification_id", "id"),
    ),
    (
        "ix_spec_powertrains_engine_displacement_ml",
        "spec_powertrains",
        ("engine_displacement_ml",),
    ),
    (
        "ix_spec_powertrains_engine_power_hp",
        "spec_powertrains",
        ("engine_power_hp",),
    ),
    (
        "ix_spec_vehicle_attributes_seat_count_max",
        "spec_vehicle_attributes",
        ("seat_count_max",),
    ),
    (
        "ix_series_photos_series_category_id",
        "series_photos",
        ("series_id", "category_id", "id"),
    ),
    (
        "ix_series_photos_series_spec_id",
        "series_photos",
        ("series_id", "spec_id", "id"),
    ),
    (
        "ix_series_photo_colors_lookup",
        "series_photo_colors",
        ("series_id", "color_scope", "color_id", "photo_id"),
    ),
    (
        "ix_series_gallery_colors_series_scope_name",
        "series_gallery_colors",
        ("series_id", "color_scope", "name"),
    ),
    (
        "ix_customs_calculations_calculation_date_id",
        "customs_calculations",
        ("calculation_date", "id"),
    ),
    (
        "ix_customs_calculations_spec_date_id",
        "customs_calculations",
        ("spec_id", "calculation_date", "id"),
    ),
)


def _index_names(table_name: str) -> set[str]:
    """Получить имена индексов существующей таблицы."""
    return {
        index["name"]
        for index in inspect(op.get_bind()).get_indexes(table_name)
        if index["name"]
    }


def _create_index(name: str, table_name: str, columns: tuple[str, ...]) -> None:
    """Создать индекс без длительной блокировки PostgreSQL."""
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                name,
                table_name,
                list(columns),
                postgresql_concurrently=True,
            )
        return
    op.create_index(name, table_name, list(columns))


def _drop_index(name: str, table_name: str) -> None:
    """Удалить индекс без длительной блокировки PostgreSQL."""
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(name, table_name=table_name, postgresql_concurrently=True)
        return
    op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    """Добавить отсутствующие индексы фильтров API."""
    table_names = set(inspect(op.get_bind()).get_table_names())
    for name, table_name, columns in INDEXES:
        if table_name in table_names and name not in _index_names(table_name):
            _create_index(name, table_name, columns)


def downgrade() -> None:
    """Удалить индексы фильтров API, если они существуют."""
    table_names = set(inspect(op.get_bind()).get_table_names())
    for name, table_name, _ in reversed(INDEXES):
        if table_name in table_names and name in _index_names(table_name):
            _drop_index(name, table_name)
