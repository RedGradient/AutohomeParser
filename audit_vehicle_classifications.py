from __future__ import annotations

import argparse
import os
from collections import Counter

from sqlalchemy import create_engine, select

from autohome.import_duty import (
    CLASSIFICATION_RULES_VERSION,
    VehicleClassificationInput,
    classify_vehicle,
)
from autohome.models import SpecVehicleAttributes

INPUT_FIELDS = tuple(
    name
    for name in VehicleClassificationInput.__dataclass_fields__
    if hasattr(SpecVehicleAttributes, name)
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверить готовность каталога к классификации 8702–8704."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def audit_classifications(engine, limit: int | None = None) -> dict[str, Counter]:
    """Классифицировать строки без записи и собрать причины отказов."""
    columns = [getattr(SpecVehicleAttributes, name) for name in INPUT_FIELDS]
    statement = select(*columns).order_by(SpecVehicleAttributes.spec_id)
    if limit is not None:
        statement = statement.limit(limit)

    counters = {
        "status": Counter(),
        "heading": Counter(),
        "reason": Counter(),
        "missing_field": Counter(),
    }
    with engine.connect() as connection:
        rows = connection.execution_options(stream_results=True).execute(statement)
        for row in rows:
            result = classify_vehicle(
                VehicleClassificationInput.from_mapping(row._mapping)
            )
            counters["status"][result.status.value] += 1
            if result.tnved_heading:
                counters["heading"][result.tnved_heading] += 1
            reason = result.details.get("reason")
            if reason:
                counters["reason"][reason] += 1
            counters["missing_field"].update(result.missing_fields)
    return counters


def print_counter(title: str, counter: Counter) -> None:
    print(title)
    if not counter:
        print("  нет")
        return
    for key, count in counter.most_common():
        print(f"  {key}: {count}")


def main() -> int:
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit должен быть положительным")

    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        counters = audit_classifications(engine, args.limit)
    finally:
        engine.dispose()

    print(f"Версия правил: {CLASSIFICATION_RULES_VERSION}")
    for key, title in (
        ("status", "Статусы:"),
        ("heading", "Товарные позиции:"),
        ("reason", "Причины отказа:"),
        ("missing_field", "Отсутствующие поля:"),
    ):
        print_counter(title, counters[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
