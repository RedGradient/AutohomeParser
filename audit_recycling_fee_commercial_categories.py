from __future__ import annotations

import argparse
import os
import re
from collections import Counter

from sqlalchemy import create_engine, or_, select

from autohome.models import Series, Spec, SpecPowertrain, SpecVehicleAttributes

COMMERCIAL_CATEGORIES = frozenset({"M2", "M3", "N1", "N2", "N3"})
CHASSIS_NAME_RE = re.compile(r"(?:底盘|\bшасси\b)", re.IGNORECASE)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Проверить готовность M2/M3/N1/N2/N3 к расчёту утильсбора "
            "без записи в базу."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def vehicle_group(row) -> str:
    names = " ".join(value for value in (row.spec_name, row.series_name) if value)
    if CHASSIS_NAME_RE.search(names):
        return "CHASSIS_CANDIDATE"
    if row.is_special_purpose is True:
        return "SPECIAL_PURPOSE"
    if row.vehicle_purpose_type is not None:
        return "SPECIALIZED"
    if row.is_special_purpose is False:
        return "ORDINARY"
    return "UNKNOWN_PURPOSE"


def missing_inputs(row, group: str) -> tuple[str, ...]:
    missing = []
    if row.category is None:
        missing.append("vehicle_technical_category")
    for field in ("model_year", "gross_mass_kg", "energy_type"):
        if getattr(row, field) is None:
            missing.append(field)
    if row.is_special_purpose is None:
        missing.append("is_special_purpose")
    if group == "SPECIAL_PURPOSE" and row.vehicle_purpose_type is None:
        missing.append("vehicle_purpose_type")
    return tuple(missing)


def audit_commercial_categories(engine, limit: int | None = None):
    statement = (
        select(
            SpecVehicleAttributes.vehicle_technical_category.label("category"),
            SpecVehicleAttributes.gross_mass_kg,
            SpecVehicleAttributes.is_special_purpose,
            SpecVehicleAttributes.vehicle_purpose_type,
            SpecVehicleAttributes.inference_flags_json,
            Spec.year.label("model_year"),
            Spec.name.label("spec_name"),
            Series.name.label("series_name"),
            SpecPowertrain.energy_type,
        )
        .join(Spec, Spec.id == SpecVehicleAttributes.spec_id)
        .join(Series, Series.id == Spec.series_id)
        .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
        .where(
            or_(
                SpecVehicleAttributes.vehicle_technical_category.in_(
                    COMMERCIAL_CATEGORIES
                ),
                SpecVehicleAttributes.is_special_purpose.is_(True),
                SpecVehicleAttributes.vehicle_purpose_type.is_not(None),
            )
        )
        .order_by(SpecVehicleAttributes.spec_id)
    )
    if limit is not None:
        statement = statement.limit(limit)

    counters = {
        "category": Counter(),
        "vehicle_group": Counter(),
        "category_group": Counter(),
        "readiness": Counter(),
        "missing_field": Counter(),
        "purpose_type": Counter(),
        "energy_type": Counter(),
        "category_provenance": Counter(),
    }
    with engine.connect() as connection:
        rows = connection.execute(statement)
        for row in rows:
            group = vehicle_group(row)
            missing = missing_inputs(row, group)
            category = row.category or "NULL"
            counters["category"][category] += 1
            counters["vehicle_group"][group] += 1
            counters["category_group"][(category, group)] += 1
            counters["readiness"]["READY" if not missing else "MISSING_DATA"] += 1
            counters["missing_field"].update(missing)
            if row.vehicle_purpose_type:
                counters["purpose_type"][row.vehicle_purpose_type] += 1
            counters["energy_type"][row.energy_type or "NULL"] += 1
            inferred = "INFERRED_INPUTS_USED" in (row.inference_flags_json or [])
            counters["category_provenance"]["INFERRED" if inferred else "DIRECT"] += 1
    return counters


def print_counter(title: str, counter: Counter) -> None:
    print(title)
    if not counter:
        print("  нет")
        return
    for key, count in counter.most_common():
        if isinstance(key, tuple):
            key = ":".join(str(part) for part in key)
        print(f"  {key}: {count}")


def main() -> int:
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit должен быть положительным")

    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        counters = audit_commercial_categories(engine, args.limit)
    finally:
        engine.dispose()

    for key, title in (
        ("category", "Технические категории:"),
        ("vehicle_group", "Группы транспорта:"),
        ("category_group", "Категории по группам:"),
        ("readiness", "Готовность нормативных входных данных:"),
        ("missing_field", "Отсутствующие входные данные:"),
        ("purpose_type", "Типы назначения:"),
        ("energy_type", "Типы силовой установки:"),
        ("category_provenance", "Происхождение категории:"),
    ):
        print_counter(title, counters[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
