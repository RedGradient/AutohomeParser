"""Команда пересчёта агрегированных метрик таможенных сценариев."""

from __future__ import annotations

import argparse
import os
import time

from sqlalchemy import create_engine

from autohome.customs_metrics import refresh_customs_metrics


def parse_arguments() -> argparse.Namespace:
    """Разобрать адрес PostgreSQL для пересчёта метрик."""
    parser = argparse.ArgumentParser(
        description="Рассчитать и сохранить актуальные таможенные метрики."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL; по умолчанию используется DATABASE_URL.",
    )
    return parser.parse_args()


def main() -> int:
    """Пересчитать снимок и вывести краткий результат."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")

    started_at = time.monotonic()
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        snapshot = refresh_customs_metrics(engine)
    finally:
        engine.dispose()

    elapsed = time.monotonic() - started_at
    print("Таможенные метрики обновлены.")
    print(f"  Комплектации: {snapshot.specs_count:,}")
    print(f"  Сценарии: {snapshot.customs_scenarios_count:,}")
    print(f"  Полные: {snapshot.complete_scenarios_count:,}")
    print(f"  Частичные: {snapshot.partial_scenarios_count:,}")
    print(f"  Недостаточно данных: {snapshot.missing_data_scenarios_count:,}")
    print(f"  Сформировано: {snapshot.generated_at.isoformat()}")
    print(f"  Время расчёта: {elapsed:.2f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
