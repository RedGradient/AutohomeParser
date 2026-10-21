from __future__ import annotations

import argparse
from collections import Counter
import json
import os

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from autohome.models import (
    ParameterDefinition,
    Spec,
    SpecParameter,
    SpecPowertrain,
    SpecVehicleAttributes,
)
from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema
from autohome.vehicle_attributes_normalizer import (
    NORMALIZATION_VERSION,
    REQUIRED_SOURCE_FIELDS,
    SEMANTIC_PATHS,
    extract_vehicle_attribute_value,
    normalize_vehicle_attributes,
)


MAX_UPSERT_ROWS = 500
INFERENCE_COMPATIBLE_FIELDS = frozenset(
    {
        "gross_mass_kg",
        "body_type",
        "seat_count_min",
        "seat_count_max",
        "has_permanent_rear_seats",
        "has_rear_side_windows",
        "has_rear_windowed_door",
        "has_separate_cargo_compartment",
        "is_special_purpose",
    }
)


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры пакетного пересчёта."""
    parser = argparse.ArgumentParser(
        description="Нормализовать кузовные и массовые характеристики."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--min-spec-id", type=int)
    parser.add_argument("--max-spec-id", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument(
        "--only-outdated",
        action="store_true",
        help="Обработать отсутствующие строки и старые версии нормализации.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Прочитать и нормализовать данные без записи.",
    )
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """Проверить ограничения параметров до обращения к базе."""
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.batch_size <= 0:
        raise SystemExit("batch-size должен быть положительным")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("limit должен быть положительным")
    if args.shard_count <= 0:
        raise SystemExit("shard-count должен быть положительным")
    if not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("shard-index должен находиться в диапазоне shard-count")
    if (
        args.min_spec_id is not None
        and args.max_spec_id is not None
        and args.min_spec_id > args.max_spec_id
    ):
        raise SystemExit("min-spec-id не может быть больше max-spec-id")


def semantic_key(path: tuple[str, str, str]) -> str:
    """Сериализовать путь параметра в том же формате, что и паук."""
    return json.dumps(path, ensure_ascii=False, separators=(",", ":"))


def load_parameter_ids(connection) -> dict[str, int]:
    """Найти идентификаторы используемых параметров по семантическим путям."""
    wanted = {field: semantic_key(path) for field, path in SEMANTIC_PATHS.items()}
    rows = connection.execute(
        select(ParameterDefinition.id, ParameterDefinition.semantic_key).where(
            ParameterDefinition.semantic_key.in_(wanted.values())
        )
    )
    by_key = {key: parameter_id for parameter_id, key in rows}
    result = {field: by_key[key] for field, key in wanted.items() if key in by_key}
    missing = REQUIRED_SOURCE_FIELDS - result.keys()
    if missing:
        raise RuntimeError(
            "В БД отсутствуют обязательные определения параметров: "
            + ", ".join(sorted(missing))
        )
    return result


def select_spec_batch(
    connection,
    *,
    after_id: int,
    batch_size: int,
    min_spec_id: int | None,
    max_spec_id: int | None,
    shard_index: int,
    shard_count: int,
    only_outdated: bool,
) -> list[tuple[int, int, str | None]]:
    """Выбрать следующую устойчиво упорядоченную партию комплектаций."""
    statement = (
        select(Spec.id, Spec.series_id, SpecPowertrain.drive_type)
        .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
        .where(Spec.id > after_id, Spec.series_id.is_not(None))
        .order_by(Spec.id)
        .limit(batch_size)
    )
    if min_spec_id is not None:
        statement = statement.where(Spec.id >= min_spec_id)
    if max_spec_id is not None:
        statement = statement.where(Spec.id <= max_spec_id)
    if shard_count > 1:
        statement = statement.where(func.mod(Spec.id, shard_count) == shard_index)
    if only_outdated:
        statement = statement.outerjoin(
            SpecVehicleAttributes,
            SpecVehicleAttributes.spec_id == Spec.id,
        ).where(
            or_(
                SpecVehicleAttributes.spec_id.is_(None),
                SpecVehicleAttributes.normalization_version
                < NORMALIZATION_VERSION,
            )
        )
    return [
        (spec_id, series_id, drive_type)
        for spec_id, series_id, drive_type in connection.execute(statement)
    ]


def build_normalized_rows(
    spec_rows: list[tuple[int, int, str | None]],
    parameter_rows,
    reverse_parameter_ids: dict[int, str],
) -> tuple[list[dict], int]:
    """Собрать значения партии и применить общий нормализатор."""
    values_by_spec: dict[int, dict] = {
        spec_id: {"drive_type": drive_type}
        for spec_id, _, drive_type in spec_rows
    }
    seen_by_spec: dict[int, set[str]] = {spec_id: set() for spec_id, _, _ in spec_rows}
    for spec_id, parameter_id, raw_value in parameter_rows:
        field = reverse_parameter_ids[parameter_id]
        values_by_spec[spec_id][field] = extract_vehicle_attribute_value(
            field,
            raw_value,
        )
        seen_by_spec[spec_id].add(field)

    rows = []
    skipped_partial = 0
    for spec_id, series_id, _ in spec_rows:
        if REQUIRED_SOURCE_FIELDS - seen_by_spec[spec_id]:
            skipped_partial += 1
            continue
        rows.append(
            normalize_vehicle_attributes(
                spec_id,
                series_id,
                values_by_spec[spec_id],
            )
        )
    return rows, skipped_partial


def upsert_rows(connection, rows: list[dict]) -> None:
    """Записать нормализованные строки совместимым с СУБД UPSERT."""
    if not rows:
        return
    for start in range(0, len(rows), MAX_UPSERT_ROWS):
        batch = rows[start : start + MAX_UPSERT_ROWS]
        if connection.dialect.name == "postgresql":
            statement = postgresql_insert(SpecVehicleAttributes).values(batch)
        elif connection.dialect.name == "sqlite":
            statement = sqlite_insert(SpecVehicleAttributes).values(batch)
        else:
            raise RuntimeError(
                f"СУБД {connection.dialect.name} не поддерживается"
            )
        primary_keys = {
            column.name for column in SpecVehicleAttributes.__table__.primary_key
        }
        update_columns = {
            name: (
                func.coalesce(
                    getattr(statement.excluded, name),
                    getattr(SpecVehicleAttributes.__table__.c, name),
                )
                if name in INFERENCE_COMPATIBLE_FIELDS
                else getattr(statement.excluded, name)
            )
            for name in batch[0]
            if name not in primary_keys
        }
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=list(primary_keys),
                set_=update_columns,
            )
        )


def backfill(engine, args: argparse.Namespace) -> Counter:
    """Пересчитать выбранные комплектации пакетами."""
    counts: Counter = Counter()
    with engine.connect() as connection:
        parameter_ids = load_parameter_ids(connection)
    reverse_ids = {
        parameter_id: field for field, parameter_id in parameter_ids.items()
    }

    after_id = (args.min_spec_id - 1) if args.min_spec_id is not None else -1
    remaining = args.limit
    while remaining is None or remaining > 0:
        current_batch_size = (
            args.batch_size
            if remaining is None
            else min(args.batch_size, remaining)
        )
        with engine.connect() as connection:
            spec_rows = select_spec_batch(
                connection,
                after_id=after_id,
                batch_size=current_batch_size,
                min_spec_id=args.min_spec_id,
                max_spec_id=args.max_spec_id,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
                only_outdated=args.only_outdated,
            )
            if not spec_rows:
                break
            spec_ids = [spec_id for spec_id, _, _ in spec_rows]
            parameter_rows = list(
                connection.execute(
                    select(
                        SpecParameter.spec_id,
                        SpecParameter.parameter_id,
                        SpecParameter.raw_json,
                    ).where(
                        SpecParameter.spec_id.in_(spec_ids),
                        SpecParameter.parameter_id.in_(reverse_ids),
                    )
                )
            )

        rows, skipped_partial = build_normalized_rows(
            spec_rows,
            parameter_rows,
            reverse_ids,
        )
        if not args.dry_run:
            with engine.begin() as connection:
                upsert_rows(connection, rows)

        counts["selected"] += len(spec_rows)
        counts["normalized"] += len(rows)
        counts["skipped_partial"] += skipped_partial
        counts["complete"] += sum(row["is_complete"] for row in rows)
        counts["incomplete"] += sum(not row["is_complete"] for row in rows)
        counts["with_warnings"] += sum(bool(row["warnings_json"]) for row in rows)
        after_id = spec_rows[-1][0]
        if remaining is not None:
            remaining -= len(spec_rows)
    return counts


def main() -> int:
    """Создать целевую таблицу и выполнить запрошенный backfill."""
    args = parse_arguments()
    validate_arguments(args)
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        if not args.dry_run:
            ensure_vehicle_attribute_schema(engine)
        counts = backfill(engine, args)
    finally:
        engine.dispose()
    mode = "dry-run" if args.dry_run else "write"
    print(
        f"Режим: {mode}; выбрано: {counts['selected']}; "
        f"нормализовано: {counts['normalized']}; "
        f"пропущено частичных: {counts['skipped_partial']}; "
        f"полных: {counts['complete']}; неполных: {counts['incomplete']}; "
        f"с предупреждениями: {counts['with_warnings']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
