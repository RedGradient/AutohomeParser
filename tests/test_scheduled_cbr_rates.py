from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from autohome.import_duty.scheduled_rates import synchronize_cbr_rates
from autohome.import_duty.types import ExchangeRate
from autohome.models import CbrExchangeRate


def rates(rate_date: date, cny: str, eur: str) -> dict[str, ExchangeRate]:
    """Создать тестовый набор курсов CNY и EUR."""
    return {
        "CNY": ExchangeRate("CNY", 10, Decimal(cny), rate_date),
        "EUR": ExchangeRate("EUR", 1, Decimal(eur), rate_date),
    }


class ScheduledCbrRatesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "rates.sqlite3"
        self.database_url = f"sqlite:///{database_path}"
        self.today = date(2026, 10, 22)
        self.yesterday = date(2026, 10, 21)
        self.calls: list[tuple[date, dict[str, ExchangeRate]]] = []

    def tearDown(self):
        self.temp_dir.cleanup()

    def recalculator(self, _database_url, calculation_date, current_rates):
        self.calls.append((calculation_date, current_rates))

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

    def test_unchanged_rates_do_not_start_second_recalculation(self):
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

        self.assertEqual(len(self.calls), 1)

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
                self.assertEqual(
                    session.scalars(select(CbrExchangeRate)).all(), []
                )
        finally:
            engine.dispose()
