from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autohome.models import Base, CustomsMetrics
from tests.postgresql import PostgreSQLTestSchema


def metrics_row(**overrides):
    """Создать допустимый снимок метрик для теста."""
    values = {
        "id": 1,
        "schema_version": 1,
        "brands_count": 10,
        "series_count": 20,
        "specs_count": 30,
        "modifications_count": 25,
        "customs_scenarios_count": 60,
        "complete_scenarios_count": 40,
        "partial_scenarios_count": 5,
        "missing_data_scenarios_count": 10,
        "manual_review_scenarios_count": 3,
        "unsupported_scenarios_count": 2,
        "specs_with_complete_scenario_count": 24,
        "missing_data_statistics_json": {"by_payment_type": {"RECYCLING_FEE": 10}},
    }
    values.update(overrides)
    return values


class CustomsMetricsModelTests(unittest.TestCase):
    """Проверить контракт единственного актуального снимка метрик."""

    def setUp(self):
        self.database = PostgreSQLTestSchema().create()
        self.engine = create_engine(self.database.database_url)
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.database.drop()

    def test_snapshot_round_trip(self):
        with self.engine.begin() as connection:
            connection.execute(CustomsMetrics.__table__.insert(), metrics_row())

        with Session(self.engine) as session:
            snapshot = session.get(CustomsMetrics, 1)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.id, 1)
        self.assertEqual(snapshot.complete_scenarios_count, 40)
        self.assertEqual(
            snapshot.missing_data_statistics_json["by_payment_type"],
            {"RECYCLING_FEE": 10},
        )
        self.assertIsNotNone(snapshot.generated_at)

    def test_snapshot_rejects_another_identifier(self):
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                CustomsMetrics.__table__.insert(),
                metrics_row(id=2),
            )

    def test_snapshot_rejects_negative_counts(self):
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                CustomsMetrics.__table__.insert(),
                metrics_row(specs_count=-1),
            )


if __name__ == "__main__":
    unittest.main()
