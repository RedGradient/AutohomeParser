from __future__ import annotations

import unittest
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from tests.postgresql import PostgreSQLTestSchema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BTREE_INDEXES = {
    "series": {
        "ix_series_brand_name_id",
        "ix_series_manufacturer_name_id",
    },
    "specs": {
        "ix_specs_series_year_id",
        "ix_specs_modification_id_id",
    },
    "spec_powertrains": {
        "ix_spec_powertrains_engine_displacement_ml",
        "ix_spec_powertrains_engine_power_hp",
    },
    "spec_vehicle_attributes": {
        "ix_spec_vehicle_attributes_seat_count_max",
    },
    "series_photos": {
        "ix_series_photos_series_category_id",
        "ix_series_photos_series_spec_id",
    },
    "series_photo_colors": {"ix_series_photo_colors_lookup"},
    "series_gallery_colors": {
        "ix_series_gallery_colors_series_scope_name",
    },
    "customs_calculations": {
        "ix_customs_calculations_calculation_date_id",
        "ix_customs_calculations_spec_date_id",
    },
}
TRIGRAM_INDEXES = {
    "ix_brands_name_lower_trgm",
    "ix_manufacturers_name_lower_trgm",
    "ix_series_name_lower_trgm",
    "ix_specs_name_lower_trgm",
}


class AlembicMigrationTests(unittest.TestCase):
    """Проверить создание и обновление схемы через Alembic."""

    def setUp(self):
        self.database = PostgreSQLTestSchema().create()
        self.database_url = self.database.database_url
        self.config = Config(str(PROJECT_ROOT / "alembic.ini"))
        self.config.set_main_option(
            "sqlalchemy.url", self.database_url.replace("%", "%%")
        )
        self.config.attributes["database_url"] = self.database_url

    def tearDown(self):
        self.database.drop()

    def test_upgrade_creates_current_schema(self):
        command.upgrade(self.config, "head")

        engine = create_engine(self.database_url)
        try:
            inspector = inspect(engine)
            self.assertIn("customs_metrics", inspector.get_table_names())
            metrics_columns = {
                column["name"] for column in inspector.get_columns("customs_metrics")
            }
            self.assertEqual(
                metrics_columns,
                {
                    "id",
                    "schema_version",
                    "generated_at",
                    "brands_count",
                    "series_count",
                    "specs_count",
                    "modifications_count",
                    "customs_scenarios_count",
                    "complete_scenarios_count",
                    "partial_scenarios_count",
                    "missing_data_scenarios_count",
                    "manual_review_scenarios_count",
                    "unsupported_scenarios_count",
                    "specs_with_complete_scenario_count",
                    "missing_data_statistics_json",
                },
            )
            for table_name in (
                "series_gallery_colors",
                "series_photo_colors",
                "gallery_crawl_tasks",
            ):
                columns = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                self.assertIn("color_scope", columns)
                self.assertNotIn("color_type", columns)
            with engine.connect() as connection:
                revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            self.assertEqual(revision, "0007_customs_metrics")
        finally:
            engine.dispose()

    def test_color_column_migration_is_reversible(self):
        command.upgrade(self.config, "head")
        command.downgrade(self.config, "0001_existing_schema")

        engine = create_engine(self.database_url)
        try:
            inspector = inspect(engine)
            columns = {
                column["name"]
                for column in inspector.get_columns("series_gallery_colors")
            }
            self.assertIn("color_type", columns)
            self.assertNotIn("color_scope", columns)
        finally:
            engine.dispose()

    def test_upgrade_creates_filter_indexes(self):
        command.upgrade(self.config, "head")

        engine = create_engine(self.database_url)
        try:
            inspector = inspect(engine)
            all_index_names = set()
            for table_name, expected_names in BTREE_INDEXES.items():
                actual_names = {
                    index["name"]
                    for index in inspector.get_indexes(table_name)
                    if index["name"]
                }
                self.assertTrue(expected_names <= actual_names)
                all_index_names.update(actual_names)
            for table_name in ("brands", "manufacturers", "series", "specs"):
                all_index_names.update(
                    index["name"]
                    for index in inspector.get_indexes(table_name)
                    if index["name"]
                )
            self.assertTrue(TRIGRAM_INDEXES <= all_index_names)
        finally:
            engine.dispose()

    def test_filter_indexes_are_removed_by_downgrade(self):
        command.upgrade(self.config, "head")
        command.downgrade(self.config, "0003_sync_powertrain_columns")

        engine = create_engine(self.database_url)
        try:
            inspector = inspect(engine)
            for table_name, removed_names in BTREE_INDEXES.items():
                remaining_names = {
                    index["name"]
                    for index in inspector.get_indexes(table_name)
                    if index["name"]
                }
                self.assertTrue(removed_names.isdisjoint(remaining_names))
        finally:
            engine.dispose()

    def test_upgrade_existing_database_preserves_data(self):
        command.upgrade(self.config, "0003_sync_powertrain_columns")
        engine = create_engine(self.database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO brands (id, name, raw_json) "
                        "VALUES (101, 'Existing brand', '{}')"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(self.config, "head")

        engine = create_engine(self.database_url)
        try:
            with engine.connect() as connection:
                name = connection.scalar(text("SELECT name FROM brands WHERE id = 101"))
            self.assertEqual(name, "Existing brand")
        finally:
            engine.dispose()

    def test_alembic_check_has_no_schema_differences(self):
        command.upgrade(self.config, "head")

        command.check(self.config)

    def test_customs_migration_keeps_only_latest_scenario(self):
        command.upgrade(self.config, "0005_name_trigram_indexes")
        engine = create_engine(self.database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO specs (id, name, raw_json) "
                        "VALUES (501, 'Test spec', '{}')"
                    )
                )
                for calculation_id, calculation_date in (
                    (1001, "2026-10-24"),
                    (1002, "2026-10-25"),
                ):
                    connection.execute(
                        text(
                            "INSERT INTO customs_calculations "
                            "(id, spec_id, importer_type, calculation_date, "
                            "rules_version, price_source, classification_status, "
                            "status, input_snapshot_json, warnings_json) VALUES "
                            "(:id, 501, 'INDIVIDUAL', :date, 'rules', 'GUIDE', "
                            "'CLASSIFIED', 'CALCULATED', '{}', '[]')"
                        ),
                        {"id": calculation_id, "date": calculation_date},
                    )
                    connection.execute(
                        text(
                            "INSERT INTO customs_payment_results "
                            "(calculation_id, payment_type, status, details_json) "
                            "VALUES (:id, 'IMPORT_DUTY', 'CALCULATED', '{}')"
                        ),
                        {"id": calculation_id},
                    )
        finally:
            engine.dispose()

        command.upgrade(self.config, "head")

        engine = create_engine(self.database_url)
        try:
            with engine.connect() as connection:
                calculation_ids = connection.scalars(
                    text("SELECT id FROM customs_calculations ORDER BY id")
                ).all()
                payment_ids = connection.scalars(
                    text(
                        "SELECT calculation_id FROM customs_payment_results "
                        "ORDER BY calculation_id"
                    )
                ).all()
            self.assertEqual(calculation_ids, [1002])
            self.assertEqual(payment_ids, [1002])

            with self.assertRaises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO customs_calculations "
                        "(id, spec_id, importer_type, calculation_date, "
                        "rules_version, price_source, classification_status, "
                        "status, input_snapshot_json, warnings_json) VALUES "
                        "(1003, 501, 'INDIVIDUAL', '2026-10-26', 'rules', "
                        "'GUIDE', 'CLASSIFIED', 'CALCULATED', '{}', '[]')"
                    )
                )
        finally:
            engine.dispose()
