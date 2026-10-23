from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
            self.assertEqual(revision, "0003_sync_powertrain_columns")
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
