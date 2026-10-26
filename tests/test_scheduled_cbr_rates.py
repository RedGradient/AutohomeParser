from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from autohome.cli.calculate_customs_payments import process_batch
from autohome.import_duty.scheduled_rates import synchronize_cbr_rates
from autohome.import_duty.types import ExchangeRate
from autohome.models import Base, CbrExchangeRate, CustomsCalculation
from tests.postgresql import PostgreSQLTestSchema, seed_specs
from tests.test_customs_recalculation import calculation_row, payment_rows


def rates(rate_date: date, cny: str, eur: str) -> dict[str, ExchangeRate]:
    """Создать тестовый набор курсов CNY и EUR."""
    return {
        "CNY": ExchangeRate("CNY", 10, Decimal(cny), rate_date),
        "EUR": ExchangeRate("EUR", 1, Decimal(eur), rate_date),
    }


class ScheduledCbrRatesTests(unittest.TestCase):
    def setUp(self):
        self.database = PostgreSQLTestSchema().create()
        self.database_url = self.database.database_url
        engine = create_engine(self.database_url)
        try:
            Base.metadata.create_all(engine)
            seed_specs(engine, (1001, 2001, 3001))
        finally:
            engine.dispose()
        self.today = date(2026, 10, 22)
        self.yesterday = date(2026, 10, 21)
        self.calls: list[tuple[date, dict[str, ExchangeRate], str]] = []

    def tearDown(self):
        self.database.drop()

    def recalculator(self, _database_url, calculation_date, current_rates, mode):
        self.calls.append((calculation_date, current_rates, mode))

    def test_first_run_saves_rates_and_starts_recalculation(self):
        values = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "110.00", "91.00"),
        }

        result = synchronize_cbr_rates(
            self.database_url,
            self.today,
            fetcher=values.__getitem__,
            recalculator=self.recalculator,
        )

        self.assertTrue(result["changed"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][2], "full")
        engine = create_engine(self.database_url)
        try:
            with Session(engine) as session:
                stored = {
                    item.currency: item
                    for item in session.scalars(select(CbrExchangeRate)).all()
                }
            self.assertEqual(stored["CNY"].rate_rub, Decimal("110.000000"))
            self.assertEqual(stored["CNY"].rate_date, self.today)
        finally:
            engine.dispose()

    def test_unchanged_rates_start_stale_recalculation(self):
        values = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "110.00", "91.00"),
        }
        for _ in range(2):
            synchronize_cbr_rates(
                self.database_url,
                self.today,
                fetcher=values.__getitem__,
                recalculator=self.recalculator,
            )

        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][2], "full")
        self.assertEqual(self.calls[1][2], "stale")

    def test_unchanged_rates_calculate_new_spec_for_both_importers(self):
        values = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "110.00", "91.00"),
        }
        synchronize_cbr_rates(
            self.database_url,
            self.today,
            fetcher=values.__getitem__,
            recalculator=self.recalculator,
        )

        def calculate_new_spec(database_url, _date, _rates, mode):
            individual = calculation_row()
            individual["id"] = 301
            individual["spec_id"] = 3001
            individual["importer_type"] = "INDIVIDUAL"
            legal_entity = dict(individual)
            legal_entity["id"] = 302
            legal_entity["importer_type"] = "LEGAL_ENTITY"
            engine = create_engine(database_url)
            try:
                process_batch(
                    engine,
                    [individual, legal_entity],
                    payment_rows(301) + payment_rows(302),
                    mode=mode,
                    dry_run=False,
                )
            finally:
                engine.dispose()

        result = synchronize_cbr_rates(
            self.database_url,
            self.today,
            fetcher=values.__getitem__,
            recalculator=calculate_new_spec,
        )

        engine = create_engine(self.database_url)
        try:
            with engine.connect() as connection:
                count = connection.scalar(
                    select(func.count()).select_from(CustomsCalculation)
                )
        finally:
            engine.dispose()
        self.assertEqual(result["recalculation_mode"], "stale")
        self.assertEqual(count, 2)

    def test_changed_rate_is_saved_and_starts_recalculation(self):
        baseline = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "110.00", "91.00"),
        }
        synchronize_cbr_rates(
            self.database_url,
            self.today,
            fetcher=baseline.__getitem__,
            recalculator=self.recalculator,
        )
        changed = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "111.25", "91.00"),
        }

        result = synchronize_cbr_rates(
            self.database_url,
            self.today,
            fetcher=changed.__getitem__,
            recalculator=self.recalculator,
        )

        self.assertTrue(result["changed"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][2], "full")
        engine = create_engine(self.database_url)
        try:
            with Session(engine) as session:
                stored = session.get(CbrExchangeRate, "CNY")
                self.assertEqual(stored.rate_rub, Decimal("111.250000"))
        finally:
            engine.dispose()

    def test_failed_recalculation_does_not_mark_rate_as_applied(self):
        values = {
            self.yesterday: rates(self.yesterday, "110.00", "91.00"),
            self.today: rates(self.today, "111.25", "91.00"),
        }

        def failed_recalculation(*_args):
            raise RuntimeError("calculation failed")

        with self.assertRaisesRegex(RuntimeError, "calculation failed"):
            synchronize_cbr_rates(
                self.database_url,
                self.today,
                fetcher=values.__getitem__,
                recalculator=failed_recalculation,
            )

        engine = create_engine(self.database_url)
        try:
            with Session(engine) as session:
                self.assertEqual(session.scalars(select(CbrExchangeRate)).all(), [])
        finally:
            engine.dispose()
