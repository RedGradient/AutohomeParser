from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import os
from typing import Any

from sqlalchemy import bindparam, create_engine, func, inspect, select, update

from autohome.models import (
    ParameterDefinition,
    Series,
    Spec,
    SpecParameter,
    SpecVehicleAttributes,
)
from autohome.vehicle_attribute_inference import (
    PARAMETER_INFERENCE_RULES,
    VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION,
    RawParameter,
    apply_vehicle_attribute_inference,
)
from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema


NORMALIZED_INPUT_FIELDS = (
    "body_type",
    "vehicle_class",
    "seat_count_min",
    "seat_count_max",
    "curb_mass_kg",
    "gross_mass_kg",
    "payload_kg_min",
    "payload_kg_max",
    "cargo_length_min_mm",
    "cargo_width_min_mm",
    "cargo_height_min_mm",
    "has_permanent_rear_seats",
    "has_rear_side_windows",
    "has_rear_windowed_door",
    "has_separate_cargo_compartment",
    "is_special_purpose",
    "warnings_json",
)
INFERENCE_STORAGE_FIELDS = (
    "gross_mass_kg",
    "has_permanent_rear_seats",
    "has_rear_side_windows",
    "has_rear_windowed_door",
    "has_separate_cargo_compartment",
    "is_special_purpose",
    "vehicle_purpose_type",
    "warnings_json",
    "inference_details_json",
    "inference_flags_json",
    "inference_rules_version",
)
OPTIONAL_EXISTING_FIELDS = (
    "vehicle_purpose_type",
    "inference_details_json",
    "inference_flags_json",
    "inference_rules_version",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Заполнить косвенно выводимые признаки транспорта."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--min-spec-id", type=int)
    parser.add_argument("--max-spec-id", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument(
        "--only-outdated",
        action="store_true",
        help="Обрабатывать только отсутствующую или старую версию вывода.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Записать результат; без флага выполняется только dry-run.",
    )
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
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


def _raw_name(raw_json: Any) -> str:
    if not isinstance(raw_json, dict):
        return ""
    return str(raw_json.get("name") or "")


def _parameter_name(raw_json: Any) -> str:
    if not isinstance(raw_json, dict):
        return ""
    return str(raw_json.get("itemname") or "")


def load_parameter_names(connection) -> dict[int, str]:
    candidate_names = {rule.raw_name for rule in PARAMETER_INFERENCE_RULES}
    return {
        row.id: raw_name
        for row in connection.execute(
            select(ParameterDefinition.id, ParameterDefinition.raw_json)
        )
        if (raw_name := _parameter_name(row.raw_json)) in candidate_names
    }


def select_batch(
    connection,
    *,
    after_id: int,
    batch_size: int,
    min_spec_id: int | None,
    max_spec_id: int | None,
    shard_index: int,
    shard_count: int,
    only_outdated: bool,
    existing_columns: set[str],
):
    columns = [
        SpecVehicleAttributes.spec_id,
        Spec.raw_json.label("spec_raw_json"),
        Series.raw_json.label("series_raw_json"),
        *(getattr(SpecVehicleAttributes, name) for name in NORMALIZED_INPUT_FIELDS),
        *(
            getattr(SpecVehicleAttributes, name)
            for name in OPTIONAL_EXISTING_FIELDS
            if name in existing_columns
        ),
    ]
    statement = (
        select(*columns)
        .join(Spec, Spec.id == SpecVehicleAttributes.spec_id)
        .outerjoin(Series, Series.id == Spec.series_id)
        .where(SpecVehicleAttributes.spec_id > after_id)
        .order_by(SpecVehicleAttributes.spec_id)
        .limit(batch_size)
    )
    if min_spec_id is not None:
        statement = statement.where(SpecVehicleAttributes.spec_id >= min_spec_id)
    if max_spec_id is not None:
        statement = statement.where(SpecVehicleAttributes.spec_id <= max_spec_id)
    if shard_count > 1:
        statement = statement.where(
            func.mod(SpecVehicleAttributes.spec_id, shard_count) == shard_index
        )
    if only_outdated and "inference_rules_version" in existing_columns:
        statement = statement.where(
            (
                SpecVehicleAttributes.inference_rules_version.is_(None)
                | (
                    SpecVehicleAttributes.inference_rules_version
                    != VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION
                )
            )
        )
    return list(connection.execute(statement).mappings())


def load_parameters(connection, spec_ids: list[int], parameter_names: dict[int, str]):
    by_spec: dict[int, list[RawParameter]] = defaultdict(list)
    if not parameter_names:
        return by_spec
    rows = connection.execute(
        select(
            SpecParameter.spec_id,
            SpecParameter.parameter_id,
            SpecParameter.raw_json,
        ).where(
            SpecParameter.spec_id.in_(spec_ids),
            SpecParameter.parameter_id.in_(parameter_names),
        )
    )
    for row in rows:
        by_spec[row.spec_id].append(
            RawParameter(
                name=parameter_names[row.parameter_id],
                raw_value=row.raw_json if isinstance(row.raw_json, dict) else {},
            )
        )
    return by_spec


def infer_batch(rows, parameters_by_spec) -> list[dict[str, Any]]:
    updates = []
    for source in rows:
        spec_id = source["spec_id"]
        values = {
            name: source.get(name)
            for name in (*NORMALIZED_INPUT_FIELDS, *OPTIONAL_EXISTING_FIELDS)
        }
        inferred = apply_vehicle_attribute_inference(
            values,
            parameters_by_spec.get(spec_id, ()),
            spec_name=_raw_name(source["spec_raw_json"]),
            series_name=_raw_name(source["series_raw_json"]),
        )
        updates.append(
            {
                "_spec_id": spec_id,
                **{name: inferred.get(name) for name in INFERENCE_STORAGE_FIELDS},
            }
        )
    return updates


def write_batch(connection, updates: list[dict[str, Any]]) -> None:
    if not updates:
        return
    connection.execute(
        update(SpecVehicleAttributes)
        .where(SpecVehicleAttributes.spec_id == bindparam("_spec_id"))
        .values(
            **{
                name: bindparam(name)
                for name in INFERENCE_STORAGE_FIELDS
            }
        ),
        updates,
    )


def _record_counts(counts: Counter, updates: list[dict[str, Any]]) -> None:
    for row in updates:
        value = row["is_special_purpose"]
        counts[f"is_special_purpose_{str(value).lower()}"] += 1
        details = row.get("inference_details_json") or {}
        decisions = details.get("decisions") or {}
        for field_name, decision in decisions.items():
            counts[f"outcome_{decision['outcome'].lower()}"] += 1
            if decision["outcome"] == "APPLIED":
                counts[f"field_{field_name}_applied"] += 1
        if row.get("vehicle_purpose_type"):
            counts[f"purpose_{row['vehicle_purpose_type']}"] += 1


def backfill(engine, args: argparse.Namespace) -> Counter:
    counts: Counter = Counter()
    existing_columns = {
        column["name"]
        for column in inspect(engine).get_columns("spec_vehicle_attributes")
    }
    with engine.connect() as connection:
        parameter_names = load_parameter_names(connection)

    after_id = (args.min_spec_id - 1) if args.min_spec_id is not None else -1
    remaining = args.limit
    while remaining is None or remaining > 0:
        size = args.batch_size if remaining is None else min(args.batch_size, remaining)
        with engine.connect() as connection:
            rows = select_batch(
                connection,
                after_id=after_id,
                batch_size=size,
                min_spec_id=args.min_spec_id,
                max_spec_id=args.max_spec_id,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
                only_outdated=args.only_outdated,
                existing_columns=existing_columns,
            )
            if not rows:
                break
            parameters = load_parameters(
                connection,
                [row["spec_id"] for row in rows],
                parameter_names,
            )
        updates = infer_batch(rows, parameters)
        if args.write:
            with engine.begin() as connection:
                write_batch(connection, updates)
        counts["selected"] += len(rows)
        _record_counts(counts, updates)
        after_id = rows[-1]["spec_id"]
        if remaining is not None:
            remaining -= len(rows)
    return counts


def main() -> int:
    args = parse_arguments()
    validate_arguments(args)
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        if args.write:
            ensure_vehicle_attribute_schema(engine)
        counts = backfill(engine, args)
    finally:
        engine.dispose()
    print(f"Режим: {'write' if args.write else 'dry-run'}")
    for name, count in counts.most_common():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
