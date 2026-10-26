from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import blake2b
from typing import Any

from sqlalchemy import (
    String,
    bindparam,
    cast,
    create_engine,
    delete,
    insert,
    select,
    update,
)

from autohome.models import (
    Modification,
    ParameterDefinition,
    ParameterSubitem,
    Spec,
    SpecParameter,
    SpecPowertrain,
)
from autohome.recycling_fee_power import select_recycling_fee_power
from autohome.translator import (
    translate_powertrain_code,
    translate_powertrain_field,
)

NORMALIZATION_VERSION = 5
EMPTY_VALUES = {None, "", "-", "Нет", "Неизвестно"}
NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

SEMANTIC_PATHS = {
    "energy_type": ("参数信息", "基本参数", "能源类型"),
    "engine_summary": ("参数信息", "基本参数", "发动机"),
    "maximum_power_kw": ("参数信息", "基本参数", "最大功率(kW)"),
    "transmission_summary": ("参数信息", "基本参数", "变速箱"),
    "engine_displacement_ml": ("参数信息", "发动机", "排量(mL)"),
    "engine_model": ("参数信息", "发动机", "发动机型号"),
    "engine_power_kw": ("参数信息", "发动机", "最大功率(kW)"),
    "engine_power_hp": ("参数信息", "发动机", "最大马力(Ps)"),
    "aspiration_type": ("参数信息", "发动机", "进气形式"),
    "cylinder_layout": ("参数信息", "发动机", "气缸排列形式"),
    "transmission_gears": ("参数信息", "变速箱", "挡位个数"),
    "transmission_type": ("参数信息", "变速箱", "变速箱类型"),
    "drive_type": ("参数信息", "底盘转向", "驱动方式"),
    "motor_total_power_kw": ("参数信息", "电动机", "电动机总功率(kW)"),
    "motor_total_power_hp": ("参数信息", "电动机", "电动机总马力(Ps)"),
    "motor_count": ("参数信息", "电动机", "驱动电机数"),
    "motor_layout": ("参数信息", "电动机", "电机布局"),
    "system_power_kw": ("参数信息", "电动机", "系统综合功率(kW)"),
    "system_power_hp": ("参数信息", "电动机", "系统综合马力(Ps)"),
    "battery_capacity_kwh": ("参数信息", "电池/充电", "电池能量(kWh)"),
    "battery_type": ("参数信息", "电池/充电", "电池类型"),
    "body_type": ("参数信息", "基本参数", "车身结构"),
}

DECIMAL_FIELDS = {
    "engine_power_kw",
    "engine_power_hp",
    "maximum_power_kw",
    "motor_total_power_kw",
    "motor_total_power_hp",
    "system_power_kw",
    "system_power_hp",
    "battery_capacity_kwh",
}
INTEGER_FIELDS = {"engine_displacement_ml", "transmission_gears"}
SUBITEM_FIELDS = {"drive_type", "battery_type"}
DERIVED_TEXT_FIELDS = {"clutch_type", "engine_layout"}
ELECTRIC_ENERGIES = {"BEV"}
PLUG_IN_ENERGIES = {"PHEV", "EREV", "SERIES_HEV"}


def parse_arguments() -> argparse.Namespace:
    """Разобрать адрес базы и размер пакета записи."""
    parser = argparse.ArgumentParser(
        description="Нормализовать силовые установки и построить модификации."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL базы данных; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


def semantic_key(path: tuple[str, str, str]) -> str:
    """Сериализовать исходный путь параметра так же, как паук."""
    return json.dumps(path, ensure_ascii=False, separators=(",", ":"))


def clean_text(value: Any) -> str | None:
    """Убрать служебные пустые значения и лишние пробелы."""
    if value in EMPTY_VALUES:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def parse_decimal(value: Any) -> Decimal | None:
    """Извлечь десятичное число из значения параметра."""
    normalized = clean_text(value)
    if normalized is None:
        return None
    match = NUMBER_RE.search(normalized.replace(" ", ""))
    if not match:
        return None
    try:
        return Decimal(match.group().replace(",", "."))
    except InvalidOperation:
        return None


def parse_integer(value: Any) -> int | None:
    """Извлечь целое число из значения параметра."""
    number = parse_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def parse_motor_count(value: Any) -> int | None:
    """Преобразовать текстовое количество электромоторов в число."""
    normalized = clean_text(value)
    mapping = {
        "Один электромотор": 1,
        "Два электромотора": 2,
        "三电机": 3,
        "四电机": 4,
    }
    if normalized in mapping:
        return mapping[normalized]
    return parse_integer(normalized)


def stable_id(value: str) -> int:
    """Построить положительный BIGINT из канонического ключа."""
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big") >> 1


def decimal_key(value: Decimal | None) -> str | None:
    """Преобразовать Decimal в стабильное строковое представление ключа."""
    if value is None:
        return None
    return format(value.normalize(), "f")


def load_parameter_ids(connection) -> dict[str, int]:
    """Найти идентификаторы требуемых семантических параметров."""
    wanted = {field: semantic_key(path) for field, path in SEMANTIC_PATHS.items()}
    rows = connection.execute(
        select(ParameterDefinition.id, ParameterDefinition.semantic_key).where(
            ParameterDefinition.semantic_key.in_(wanted.values())
        )
    )
    by_key = {key: parameter_id for parameter_id, key in rows}
    return {field: by_key[key] for field, key in wanted.items() if key in by_key}


def load_powertrains(connection, parameter_ids: dict[str, int]) -> dict[int, dict]:
    """Загрузить выбранные параметры и привести их к типизированному виду."""
    reverse_ids = {parameter_id: field for field, parameter_id in parameter_ids.items()}
    rows = connection.execute(
        select(
            Spec.id,
            Spec.series_id,
            Spec.year,
            SpecParameter.parameter_id,
            SpecParameter.value,
        )
        .join(SpecParameter, SpecParameter.spec_id == Spec.id)
        .where(SpecParameter.parameter_id.in_(reverse_ids))
    )
    result: dict[int, dict] = {}
    for spec_id, series_id, model_year, parameter_id, value in rows:
        row = result.setdefault(
            spec_id,
            {"spec_id": spec_id, "series_id": series_id, "model_year": model_year},
        )
        field = reverse_ids[parameter_id]
        if field in DECIMAL_FIELDS:
            row[field] = parse_decimal(value)
        elif field in INTEGER_FIELDS:
            row[field] = parse_integer(value)
        elif field == "motor_count":
            row[field] = parse_motor_count(value)
        elif field not in SUBITEM_FIELDS:
            row[field] = clean_text(translate_powertrain_field(field, value))
            if field == "transmission_type":
                row["clutch_type"] = translate_powertrain_code("clutch_type", value)

    for field in SUBITEM_FIELDS:
        parameter_id = parameter_ids.get(field)
        if parameter_id is None:
            continue
        subitems = connection.execute(
            select(ParameterSubitem.spec_id, ParameterSubitem.name).where(
                ParameterSubitem.parameter_id == parameter_id,
                cast(ParameterSubitem.value, String).in_(
                    ("true", "t", "1", "Штатно", "●")
                ),
            )
        )
        for spec_id, name in subitems:
            if spec_id in result:
                result[spec_id][field] = clean_text(
                    translate_powertrain_field(field, name)
                )
                if field == "drive_type":
                    result[spec_id]["engine_layout"] = translate_powertrain_code(
                        "engine_layout", name
                    )
    return result


def required_missing(row: dict) -> list[str]:
    """Вернуть критичные поля, без которых объединение небезопасно."""
    missing = []
    energy = row.get("energy_type")
    transmission = row.get("transmission_type") or row.get("transmission_summary")
    common = {
        "series_id": row.get("series_id"),
        "model_year": row.get("model_year"),
        "energy_type": energy,
        "transmission": transmission,
        "drive_type": row.get("drive_type"),
        "engine_layout": row.get("engine_layout"),
        "aspiration_type": row.get("aspiration_type"),
        "cylinder_layout": row.get("cylinder_layout"),
    }
    missing.extend(name for name, value in common.items() if value is None)

    if energy not in ELECTRIC_ENERGIES:
        engine_identity = row.get("engine_model") or row.get("engine_summary")
        engine_power = row.get("engine_power_kw") or row.get("maximum_power_kw")
        if engine_identity is None:
            missing.append("engine_identity")
        if engine_power is None:
            missing.append("engine_power_kw")

    if energy in ELECTRIC_ENERGIES | PLUG_IN_ENERGIES:
        motor_power = row.get("motor_total_power_kw") or row.get("maximum_power_kw")
        electric = {
            "motor_power_kw": motor_power,
            "motor_count": row.get("motor_count"),
            "battery_capacity_kwh": row.get("battery_capacity_kwh"),
            "battery_type": row.get("battery_type"),
        }
        missing.extend(name for name, value in electric.items() if value is None)
    return sorted(set(missing))


def modification_signature(row: dict, missing: list[str]) -> dict:
    """Построить условный технический ключ модификации."""
    energy = row.get("energy_type")
    signature = {
        "series_id": row.get("series_id"),
        "model_year": row.get("model_year"),
        "energy_type": energy,
        "maximum_power_kw": decimal_key(row.get("maximum_power_kw")),
        "transmission": row.get("transmission_type") or row.get("transmission_summary"),
        "clutch_type": row.get("clutch_type"),
        "transmission_gears": row.get("transmission_gears"),
        "drive_type": row.get("drive_type"),
    }
    if energy not in ELECTRIC_ENERGIES:
        signature["engine"] = {
            "displacement_ml": row.get("engine_displacement_ml"),
            "identity": row.get("engine_model") or row.get("engine_summary"),
            "power_kw": decimal_key(
                row.get("engine_power_kw") or row.get("maximum_power_kw")
            ),
            "power_hp": decimal_key(row.get("engine_power_hp")),
        }
    if energy in ELECTRIC_ENERGIES | PLUG_IN_ENERGIES:
        signature["electric"] = {
            "motor_power_kw": decimal_key(
                row.get("motor_total_power_kw") or row.get("maximum_power_kw")
            ),
            "motor_power_hp": decimal_key(row.get("motor_total_power_hp")),
            "motor_count": row.get("motor_count"),
            "motor_layout": row.get("motor_layout"),
            "system_power_kw": decimal_key(row.get("system_power_kw")),
            "system_power_hp": decimal_key(row.get("system_power_hp")),
            "battery_capacity_kwh": decimal_key(row.get("battery_capacity_kwh")),
            "battery_type": row.get("battery_type"),
        }
    signature["body_type"] = row.get("body_type")
    if missing:
        signature["incomplete_spec_id"] = row["spec_id"]
    return signature


def modification_name(row: dict) -> str:
    """Собрать краткое человекочитаемое название модификации."""
    parts = [str(row.get("model_year") or ""), row.get("energy_type")]
    engine = row.get("engine_summary") or row.get("engine_model")
    if engine:
        parts.append(engine)
    elif row.get("motor_total_power_kw") is not None:
        parts.append(f"{decimal_key(row['motor_total_power_kw'])} кВт")
    transmission = row.get("transmission_summary") or row.get("transmission_type")
    parts.extend((transmission, row.get("drive_type")))
    if row.get("battery_capacity_kwh") is not None:
        parts.append(f"{decimal_key(row['battery_capacity_kwh'])} кВт·ч")
    return " · ".join(part for part in parts if part)


def chunks(rows: list[dict], size: int):
    """Разбить список строк на пакеты заданного размера."""
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def rebuild(engine, batch_size: int) -> tuple[int, int, int]:
    """Пересчитать нормализованные силовые установки и модификации."""
    with engine.connect() as connection:
        parameter_ids = load_parameter_ids(connection)
        powertrains = load_powertrains(connection, parameter_ids)

    now = datetime.now(UTC)
    modifications: dict[int, dict] = {}
    spec_links: list[dict] = []
    powertrain_rows: list[dict] = []
    incomplete_count = 0

    normalized_fields = (*SEMANTIC_PATHS, *DERIVED_TEXT_FIELDS)
    for row in powertrains.values():
        for field in normalized_fields:
            row.setdefault(field, None)
        recycling_fee_power = select_recycling_fee_power(
            row.get("energy_type"),
            engine_power_kw=row.get("engine_power_kw"),
            engine_power_hp=row.get("engine_power_hp"),
            maximum_power_kw=row.get("maximum_power_kw"),
        )
        row.update(
            recycling_fee_powertrain_type=(recycling_fee_power.powertrain_type.value),
            recycling_fee_power_kw=recycling_fee_power.power_kw,
            recycling_fee_power_source=(
                recycling_fee_power.source.value
                if recycling_fee_power.source is not None
                else None
            ),
        )
        missing = required_missing(row)
        incomplete_count += bool(missing)
        row.update(
            is_complete=not missing,
            missing_fields_json=missing,
            normalization_version=NORMALIZATION_VERSION,
            normalized_at=now,
        )
        powertrain_rows.append(row)

        signature = modification_signature(row, missing)
        key = json.dumps(
            signature, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        modification_id = stable_id(key)
        existing = modifications.get(modification_id)
        if existing and existing["modification_key"] != key:
            raise RuntimeError("Обнаружена коллизия хеша модификации")
        if existing:
            existing["spec_count"] += 1
        else:
            modifications[modification_id] = {
                "id": modification_id,
                "modification_key": key,
                "series_id": row["series_id"],
                "model_year": row["model_year"],
                "name": modification_name(row),
                "energy_type": row["energy_type"],
                "engine_summary": row["engine_summary"],
                "engine_displacement_ml": row["engine_displacement_ml"],
                "engine_model": row["engine_model"],
                "engine_power_kw": row["engine_power_kw"],
                "engine_power_hp": row["engine_power_hp"],
                "maximum_power_kw": row["maximum_power_kw"],
                "transmission_summary": row["transmission_summary"],
                "transmission_type": row["transmission_type"],
                "clutch_type": row["clutch_type"],
                "transmission_gears": row["transmission_gears"],
                "drive_type": row["drive_type"],
                "engine_layout": row["engine_layout"],
                "aspiration_type": row["aspiration_type"],
                "cylinder_layout": row["cylinder_layout"],
                "body_type": row["body_type"],
                "motor_total_power_kw": row["motor_total_power_kw"],
                "motor_total_power_hp": row["motor_total_power_hp"],
                "motor_count": row["motor_count"],
                "motor_layout": row["motor_layout"],
                "system_power_kw": row["system_power_kw"],
                "system_power_hp": row["system_power_hp"],
                "battery_capacity_kwh": row["battery_capacity_kwh"],
                "battery_type": row["battery_type"],
                "is_complete": not missing,
                "spec_count": 1,
                "normalization_version": NORMALIZATION_VERSION,
                "generated_at": now,
            }
        spec_links.append(
            {"_spec_id": row["spec_id"], "modification_id": modification_id}
        )

    with engine.begin() as connection:
        connection.execute(update(Spec).values(modification_id=None))
        connection.execute(delete(SpecPowertrain))
        connection.execute(delete(Modification))
        for batch in chunks(list(modifications.values()), batch_size):
            connection.execute(insert(Modification), batch)
        for batch in chunks(powertrain_rows, batch_size):
            connection.execute(insert(SpecPowertrain), batch)
        statement = (
            update(Spec)
            .where(Spec.id == bindparam("_spec_id"))
            .values(modification_id=bindparam("modification_id"))
        )
        for batch in chunks(spec_links, batch_size):
            connection.execute(statement, batch)
    return len(powertrain_rows), len(modifications), incomplete_count


def main() -> int:
    """Выполнить полный пересчёт производных данных в готовой схеме."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.batch_size <= 0:
        raise SystemExit("batch-size должен быть положительным")
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        specs, modifications, incomplete = rebuild(engine, args.batch_size)
    finally:
        engine.dispose()
    print(
        f"Нормализовано комплектаций: {specs}; модификаций: {modifications}; "
        f"неполных: {incomplete}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
