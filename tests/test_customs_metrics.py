from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autohome.customs_metrics import refresh_customs_metrics
from autohome.models import (
    Base,
    Brand,
    CustomsCalculation,
    CustomsMetrics,
    CustomsPaymentResult,
    Modification,
)
from tests.postgresql import PostgreSQLTestSchema, seed_specs

PAYMENT_TYPES = (
    "IMPORT_DUTY",
    "CUSTOMS_FEE",
    "RECYCLING_FEE",
    "EXCISE",
    "VAT",
)


def calculation(calculation_id: int, spec_id: int, importer_type: str) -> dict:
    """Создать минимальный актуальный таможенный сценарий."""
    return {
        "id": calculation_id,
        "spec_id": spec_id,
        "importer_type": importer_type,
        "calculation_date": date(2026, 10, 27),
        "rules_version": "rules-v1",
        "price_source": "GUIDE_PRICE",
        "classification_status": "CLASSIFIED",
        "status": "CALCULATED",
        "input_snapshot_json": {},
        "warnings_json": [],
    }


def payments(
    calculation_id: int,
    overrides: dict[str, tuple[str, Decimal | None, dict]] | None = None,
    *,
    payment_types: tuple[str, ...] = PAYMENT_TYPES,
) -> list[dict]:
    """Создать набор компонентов сценария с точечными переопределениями."""
    overrides = overrides or {}
    rows = []
    for payment_type in payment_types:
        status, amount, details = overrides.get(
            payment_type,
            ("CALCULATED", Decimal("100.00"), {}),
        )
        rows.append(
            {
                "calculation_id": calculation_id,
                "payment_type": payment_type,
                "amount_rub": amount,
                "status": status,
                "details_json": details,
            }
        )
    return rows


class CustomsMetricsTests(unittest.TestCase):
    """Проверить агрегацию и перезапись актуального снимка."""

    def setUp(self):
        self.database = PostgreSQLTestSchema().create()
        self.engine = self.database.create_engine()
        Base.metadata.create_all(self.engine)
        seed_specs(self.engine, (1001, 1002, 1003))
        with self.engine.begin() as connection:
            connection.execute(
                Brand.__table__.insert(),
                {"id": 1, "name": "Brand", "raw_json": {}},
            )
            connection.execute(
                Modification.__table__.insert(),
                {
                    "id": 1,
                    "modification_key": "modification-1",
                    "series_id": 10,
                    "name": "Modification",
                    "is_complete": True,
                    "spec_count": 1,
                    "normalization_version": 1,
                },
            )
            connection.execute(
                CustomsCalculation.__table__.insert(),
                [
                    calculation(101, 1001, "LEGAL_ENTITY"),
                    calculation(102, 1001, "INDIVIDUAL"),
                    calculation(201, 1002, "LEGAL_ENTITY"),
                    calculation(202, 1002, "INDIVIDUAL"),
                    calculation(301, 1003, "LEGAL_ENTITY"),
                ],
            )
            connection.execute(
                CustomsPaymentResult.__table__.insert(),
                [
                    *payments(
                        101,
                        {"EXCISE": ("NOT_APPLICABLE", None, {})},
                    ),
                    *payments(
                        102,
                        {
                            "RECYCLING_FEE": (
                                "MISSING_DATA",
                                None,
                                {
                                    "reason": "POWER_REQUIRED",
                                    "missing_fields": ["electric_30_min_power_kw"],
                                },
                            ),
                            "VAT": (
                                "MISSING_DATA",
                                None,
                                {
                                    "missing_fields": ["customs_value_rub"],
                                    "invalid_fields": ["customs_value_rub"],
                                },
                            ),
                        },
                    ),
                    *payments(
                        201,
                        {"IMPORT_DUTY": ("MANUAL_REVIEW", None, {})},
                    ),
                    *payments(
                        202,
                        {"RECYCLING_FEE": ("UNSUPPORTED", None, {})},
                    ),
                    *payments(
                        301,
                        payment_types=PAYMENT_TYPES[:-1],
                    ),
                ],
            )

    def tearDown(self):
        self.engine.dispose()
        self.database.drop()

    def test_refresh_classifies_scenarios_and_collects_missing_data(self):
        snapshot = refresh_customs_metrics(self.engine)

        self.assertEqual(snapshot.brands_count, 1)
        self.assertEqual(snapshot.series_count, 1)
        self.assertEqual(snapshot.specs_count, 3)
        self.assertEqual(snapshot.modifications_count, 1)
        self.assertEqual(snapshot.customs_scenarios_count, 5)
        self.assertEqual(snapshot.complete_scenarios_count, 1)
        self.assertEqual(snapshot.partial_scenarios_count, 1)
        self.assertEqual(snapshot.missing_data_scenarios_count, 1)
        self.assertEqual(snapshot.manual_review_scenarios_count, 1)
        self.assertEqual(snapshot.unsupported_scenarios_count, 1)
        self.assertEqual(snapshot.specs_with_complete_scenario_count, 1)

        statistics = snapshot.missing_data_statistics_json
        self.assertEqual(statistics["affected_scenarios_count"], 1)
        self.assertEqual(statistics["affected_specs_count"], 1)
        self.assertEqual(statistics["by_importer_type"], {"INDIVIDUAL": 1})
        self.assertEqual(
            statistics["by_payment_type"],
            {"RECYCLING_FEE": 1, "VAT": 1},
        )
        self.assertEqual(statistics["by_reason"], {"POWER_REQUIRED": 1})
        self.assertEqual(
            statistics["by_missing_field"],
            {"customs_value_rub": 1, "electric_30_min_power_kw": 1},
        )
        self.assertEqual(
            statistics["by_invalid_field"],
            {"customs_value_rub": 1},
        )

    def test_refresh_replaces_singleton_snapshot(self):
        first = refresh_customs_metrics(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                Brand.__table__.insert(),
                {"id": 2, "name": "Second brand", "raw_json": {}},
            )

        second = refresh_customs_metrics(self.engine)

        self.assertEqual(first.brands_count, 1)
        self.assertEqual(second.brands_count, 2)
        with Session(self.engine) as session:
            stored = session.get(CustomsMetrics, 1)
            row_count = session.scalar(select(func.count()).select_from(CustomsMetrics))
        self.assertEqual(row_count, 1)
        self.assertEqual(stored.brands_count, 2)
        self.assertGreaterEqual(stored.generated_at, first.generated_at)


if __name__ == "__main__":
    unittest.main()
