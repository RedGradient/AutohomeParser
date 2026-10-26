from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect

from autohome.database_migrations import DatabaseSchemaError, upgrade_database
from autohome.pipelines import SqlAlchemyPipeline
from tests.postgresql import PostgreSQLTestSchema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SCHEMA_MUTATIONS = (
    "create_all(",
    "ALTER TABLE",
    ".__table__.create(",
    ".__table__.drop(",
)


class SchemaLifecycleTests(unittest.TestCase):
    """Проверить, что рабочий код использует только готовую схему Alembic."""

    def test_pipeline_rejects_unversioned_database_without_creating_tables(self):
        database = PostgreSQLTestSchema().create()
        try:
            database_url = database.database_url
            pipeline = SqlAlchemyPipeline(database_url, 100, 0, 0)

            with self.assertRaisesRegex(DatabaseSchemaError, "alembic upgrade head"):
                pipeline.open_spider()

            engine = create_engine(database_url)
            try:
                self.assertEqual(inspect(engine).get_table_names(), [])
            finally:
                engine.dispose()
        finally:
            database.drop()

    def test_pipeline_accepts_database_at_head(self):
        database = PostgreSQLTestSchema().create()
        try:
            database_url = database.database_url
            upgrade_database(database_url)
            pipeline = SqlAlchemyPipeline(database_url, 100, 0, 0)

            pipeline.open_spider()
            pipeline.close_spider()
        finally:
            database.drop()

    def test_runtime_code_contains_no_direct_schema_mutations(self):
        excluded_directories = {".git", ".venv", "alembic", "tests"}
        violations: list[str] = []
        for path in PROJECT_ROOT.rglob("*.py"):
            if any(part in excluded_directories for part in path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_SCHEMA_MUTATIONS:
                if marker in source:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {marker}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
