from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

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
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "migrations.sqlite3"
        self.database_url = f"sqlite:///{database_path}"
        self.config = Config(str(PROJECT_ROOT / "alembic.ini"))
        self.config.set_main_option("sqlalchemy.url", self.database_url)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upgrade_creates_current_schema(self):
        command.upgrade(self.config, "head")

        engine = create_engine(self.database_url)
        try:
            inspector = inspect(engine)
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
            self.assertEqual(revision, "0005_name_trigram_indexes")
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

    def test_upgrade_creates_filter_indexes_without_postgresql_indexes(self):
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
            self.assertTrue(TRIGRAM_INDEXES.isdisjoint(all_index_names))
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
