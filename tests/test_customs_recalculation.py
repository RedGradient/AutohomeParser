from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from autohome.cli.calculate_customs_payments import (
    calculation_run_connection,
    process_batch,
)
from autohome.models import Base, CustomsCalculation, CustomsPaymentResult
from tests.postgresql import PostgreSQLTestSchema, seed_specs


def calculation_row() -> dict:
    """Сформировать минимальный актуальный таможенный расчёт для теста."""
    return {
        "id": 101,
        "spec_id": 1001,
        "importer_type": "LEGAL_ENTITY",
        "calculation_date": date(2026, 10, 25),
        "rules_version": "rules-v1",
        "price_source": "GUIDE_PRICE",
        "vehicle_price_cny": Decimal("100000.00"),
        "customs_value_rub": Decimal("1100000.00"),
        "cny_rate_nominal": 10,
        "cny_rate_rub": Decimal("110.000000"),
        "cny_rate_date": date(2026, 10, 24),
        "classification_status": "CLASSIFIED",
        "status": "CALCULATED",
        "input_snapshot_json": {"engine_power_kw": "110"},
        "warnings_json": [],
        "calculated_at": datetime(2026, 10, 25, 8, tzinfo=UTC),
    }


def payment_rows(calculation_id: int = 101) -> list[dict]:
    """Сформировать связанные результаты платежей для теста."""
    return [
        {
            "calculation_id": calculation_id,
            "payment_type": "EXCISE",
            "amount_rub": Decimal("9600.00"),
            "status": "CALCULATED",
            "rule_code": "EXCISE_2026",
            "details_json": {"rules_version": "excise-v1"},
        },
        {
            "calculation_id": calculation_id,
            "payment_type": "VAT",
            "amount_rub": Decimal("280412.00"),
            "status": "CALCULATED",
            "rule_code": "VAT_2026",
            "details_json": {"rules_version": "vat-v1"},
        },
    ]


class CustomsRecalculationTests(unittest.TestCase):
    def setUp(self):
        self.database = PostgreSQLTestSchema().create()
        self.engine = self.database.create_engine()
        Base.metadata.create_all(self.engine)
        seed_specs(self.engine, (1001, 2001))

    def tearDown(self):
        self.engine.dispose()
        self.database.drop()

    def test_stale_mode_skips_unchanged_calculation_on_another_date(self):
        calculation = calculation_row()
        payments = payment_rows()
        self.assertEqual(
            process_batch(
                self.engine,
                [calculation],
                payments,
                mode="stale",
                dry_run=False,
            ),
            1,
        )

        repeated = deepcopy(calculation)
        repeated["calculation_date"] += timedelta(days=1)
        repeated["calculated_at"] += timedelta(days=1)
        repeated["cny_rate_date"] += timedelta(days=1)
        self.assertEqual(
            process_batch(
                self.engine,
                [repeated],
                deepcopy(payments),
                mode="stale",
                dry_run=False,
            ),
            0,
        )

    def test_stale_mode_selects_changed_rate(self):
        calculation = calculation_row()
        payments = payment_rows()
        process_batch(
            self.engine,
            [calculation],
            payments,
            mode="full",
            dry_run=False,
        )
        changed = deepcopy(calculation)
        changed["cny_rate_rub"] = Decimal("111.000000")

        self.assertEqual(
            process_batch(
                self.engine,
                [changed],
                deepcopy(payments),
                mode="stale",
                dry_run=False,
            ),
            1,
        )
        with self.engine.connect() as connection:
            stored_rate = connection.scalar(select(CustomsCalculation.cny_rate_rub))
            count = connection.scalar(
                select(func.count()).select_from(CustomsCalculation)
            )
        self.assertEqual(stored_rate, Decimal("111.000000"))
        self.assertEqual(count, 1)

    def test_stale_mode_selects_changed_price_or_vehicle_data(self):
        calculation = calculation_row()
        payments = payment_rows()
        process_batch(
            self.engine,
            [calculation],
            payments,
            mode="full",
            dry_run=False,
        )

        for field, value in (
            ("vehicle_price_cny", Decimal("101000.00")),
            ("input_snapshot_json", {"engine_power_kw": "120"}),
        ):
            with self.subTest(field=field):
                process_batch(
                    self.engine,
                    [deepcopy(calculation)],
                    deepcopy(payments),
                    mode="full",
                    dry_run=False,
                )
                changed = deepcopy(calculation)
                changed[field] = value
                self.assertEqual(
                    process_batch(
                        self.engine,
                        [changed],
                        deepcopy(payments),
                        mode="stale",
                        dry_run=False,
                    ),
                    1,
                )
                with self.engine.connect() as connection:
                    stored_value = connection.scalar(
                        select(getattr(CustomsCalculation, field))
                    )
                self.assertEqual(stored_value, value)

    def test_stale_mode_selects_changed_payment_rule(self):
        calculation = calculation_row()
        payments = payment_rows()
        process_batch(
            self.engine,
            [calculation],
            payments,
            mode="full",
            dry_run=False,
        )
        changed_payments = deepcopy(payments)
        changed_payments[0]["details_json"]["rules_version"] = "excise-v2"

        self.assertEqual(
            process_batch(
                self.engine,
                [deepcopy(calculation)],
                changed_payments,
                mode="stale",
                dry_run=False,
            ),
            1,
        )
        with self.engine.connect() as connection:
            stored_details = connection.scalar(
                select(CustomsPaymentResult.details_json).where(
                    CustomsPaymentResult.payment_type == "EXCISE"
                )
            )
        self.assertEqual(stored_details["rules_version"], "excise-v2")

    def test_stale_mode_restores_missing_payment(self):
        calculation = calculation_row()
        payments = payment_rows()
        process_batch(
            self.engine,
            [calculation],
            payments,
            mode="full",
            dry_run=False,
        )
        with self.engine.begin() as connection:
            connection.execute(
                CustomsPaymentResult.__table__.delete().where(
                    CustomsPaymentResult.payment_type == "VAT"
                )
            )

        self.assertEqual(
            process_batch(
                self.engine,
                [deepcopy(calculation)],
                deepcopy(payments),
                mode="stale",
                dry_run=True,
            ),
            1,
        )

    def test_full_mode_rewrites_current_calculation(self):
        calculation = calculation_row()
        payments = payment_rows()
        process_batch(
            self.engine,
            [calculation],
            payments,
            mode="full",
            dry_run=False,
        )
        changed = deepcopy(calculation)
        changed["calculation_date"] += timedelta(days=1)

        self.assertEqual(
            process_batch(
                self.engine,
                [changed],
                deepcopy(payments),
                mode="full",
                dry_run=False,
            ),
            1,
        )
        with self.engine.connect() as connection:
            stored_date = connection.scalar(select(CustomsCalculation.calculation_date))
            count = connection.scalar(
                select(func.count()).select_from(CustomsCalculation)
            )
        self.assertEqual(stored_date, changed["calculation_date"])
        self.assertEqual(count, 1)

    def test_stale_mode_creates_both_scenarios_for_new_spec(self):
        individual = calculation_row()
        individual["id"] = 201
        individual["spec_id"] = 2001
        individual["importer_type"] = "INDIVIDUAL"
        legal_entity = deepcopy(individual)
        legal_entity["id"] = 202
        legal_entity["importer_type"] = "LEGAL_ENTITY"
        payments = payment_rows(201) + payment_rows(202)

        selected = process_batch(
            self.engine,
            [individual, legal_entity],
            payments,
            mode="stale",
            dry_run=False,
        )

        with self.engine.connect() as connection:
            importer_types = connection.scalars(
                select(CustomsCalculation.importer_type).order_by(
                    CustomsCalculation.importer_type
                )
            ).all()
        self.assertEqual(selected, 2)
        self.assertEqual(importer_types, ["INDIVIDUAL", "LEGAL_ENTITY"])

    def test_run_connection_acquires_advisory_lock(self):
        with calculation_run_connection(self.engine) as connection:
            self.assertEqual(connection.scalar(select(1)), 1)


if __name__ == "__main__":
    unittest.main()
