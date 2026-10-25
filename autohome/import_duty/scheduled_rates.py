"""Ежедневная синхронизация курсов ЦБ и запуск массового перерасчёта."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from autohome.import_duty.currency import fetch_cbr_rates
from autohome.import_duty.types import ExchangeRate
from autohome.models import CbrExchangeRate

RateFetcher = Callable[[date], dict[str, ExchangeRate]]
Recalculator = Callable[[str, date, dict[str, ExchangeRate]], None]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def rates_differ(
    current: dict[str, ExchangeRate], previous: dict[str, ExchangeRate]
) -> bool:
    """Проверить изменение номинала или значения любого нужного курса."""
    return any(
        current[currency].nominal != previous[currency].nominal
        or current[currency].rate_rub != previous[currency].rate_rub
        for currency in ("CNY", "EUR")
    )


def run_customs_recalculation(
    database_url: str,
    calculation_date: date,
    rates: dict[str, ExchangeRate],
) -> None:
    """Запустить существующую утилиту расчёта с уже полученными курсами."""
    command = [
        sys.executable,
        str(PROJECT_ROOT / "calculate_customs_payments.py"),
        "--database-url",
        database_url,
        "--date",
        calculation_date.isoformat(),
        "--cny-rate-rub",
        str(rates["CNY"].rate_rub),
        "--cny-nominal",
        str(rates["CNY"].nominal),
        "--eur-rate-rub",
        str(rates["EUR"].rate_rub),
        "--eur-nominal",
        str(rates["EUR"].nominal),
    ]
    subprocess.run(command, check=True, env=os.environ.copy())


def synchronize_cbr_rates(
    database_url: str,
    calculation_date: date,
    *,
    fetcher: RateFetcher = fetch_cbr_rates,
    recalculator: Recalculator = run_customs_recalculation,
) -> dict[str, Any]:
    """Сравнить курсы со вчерашними, сохранить изменения и пересчитать платежи."""
    current = fetcher(calculation_date)
    previous = fetcher(calculation_date - timedelta(days=1))
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        CbrExchangeRate.__table__.create(engine, checkfirst=True)
        with Session(engine) as session:
            stored_rates = {
                item.currency: item
                for item in session.scalars(select(CbrExchangeRate)).all()
            }
            stored_is_stale = any(
                currency not in stored_rates
                or stored_rates[currency].nominal != current[currency].nominal
                or stored_rates[currency].rate_rub != current[currency].rate_rub
                for currency in ("CNY", "EUR")
            )
            changed = rates_differ(current, previous) or stored_is_stale
        if changed:
            recalculator(database_url, calculation_date, current)
            with Session(engine) as session:
                for currency in ("CNY", "EUR"):
                    rate = current[currency]
                    stored = session.get(CbrExchangeRate, currency)
                    if stored is None:
                        stored = CbrExchangeRate(currency=currency)
                        session.add(stored)
                    stored.nominal = rate.nominal
                    stored.rate_rub = rate.rate_rub
                    stored.rate_date = rate.rate_date
                    stored.fetched_at = datetime.now(UTC)
                session.commit()
    finally:
        engine.dispose()

    return {
        "changed": changed,
        "calculation_date": calculation_date.isoformat(),
        "current": {
            currency: {
                "nominal": current[currency].nominal,
                "rate_rub": str(current[currency].rate_rub),
                "rate_date": current[currency].rate_date.isoformat(),
            }
            for currency in ("CNY", "EUR")
        },
    }
