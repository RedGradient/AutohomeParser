from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import blake2b
import json
import re
from typing import Any


NORMALIZATION_VERSION = 1
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
    "transmission_gears": ("参数信息", "变速箱", "挡位个数"),
    "transmission_type": ("参数信息", "变速箱", "变速箱类型"),
    "drive_type": ("参数信息", "底盘转向", "驱动方式"),
    "motor_total_power_kw": ("参数信息", "电动机", "电动机总功率(kW)"),
    "motor_count": ("参数信息", "电动机", "驱动电机数"),
    "motor_layout": ("参数信息", "电动机", "电机布局"),
    "system_power_kw": ("参数信息", "电动机", "系统综合功率(kW)"),
    "battery_capacity_kwh": ("参数信息", "电池/充电", "电池能量(kWh)"),
    "battery_type": ("参数信息", "电池/充电", "电池类型"),
}
PATH_TO_FIELD = {path: field for field, path in SEMANTIC_PATHS.items()}
DECIMAL_FIELDS = {
    "engine_power_kw",
    "maximum_power_kw",
    "motor_total_power_kw",
    "system_power_kw",
    "battery_capacity_kwh",
}
INTEGER_FIELDS = {"engine_displacement_ml", "transmission_gears"}
SUBITEM_FIELDS = {"drive_type", "battery_type"}
ELECTRIC_ENERGIES = {"Электромобиль"}
PLUG_IN_ENERGIES = {"Подключаемый гибрид", "Гибрид с увеличенным запасом хода"}


def semantic_key(path: tuple[str, str, str]) -> str:
    """Сериализовать исходный путь параметра API."""
    return json.dumps(path, ensure_ascii=False, separators=(",", ":"))


def clean_text(value: Any) -> str | None:
    """Привести пустые и служебные текстовые значения к None."""
    if value in EMPTY_VALUES:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def parse_decimal(value: Any) -> Decimal | None:
    """Извлечь десятичное число из строкового значения."""
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
    """Извлечь целое число из строкового значения."""
    number = parse_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def parse_motor_count(value: Any) -> int | None:
    """Преобразовать число электромоторов в целое значение."""
    mapping = {
        "Один электромотор": 1,
        "Два электромотора": 2,
        "三电机": 3,
        "四电机": 4,
    }
    normalized = clean_text(value)
    return mapping.get(normalized, parse_integer(normalized))


def stable_id(value: str) -> int:
    """Построить положительный BIGINT из канонического ключа."""
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big") >> 1


def decimal_key(value: Decimal | None) -> str | None:
    """Преобразовать Decimal в стабильную строку для ключа."""
    return format(value.normalize(), "f") if value is not None else None


def normalize_powertrain(
    spec_id: int,
    series_id: int,
    model_year: int | None,
    values: dict[str, Any],
) -> dict:
    """Нормализовать выделенные признаки силовой установки комплектации."""
    row = {"spec_id": spec_id, "series_id": series_id, "model_year": model_year}
    for field in SEMANTIC_PATHS:
        value = values.get(field)
        if field in DECIMAL_FIELDS:
            row[field] = parse_decimal(value)
        elif field in INTEGER_FIELDS:
            row[field] = parse_integer(value)
        elif field == "motor_count":
            row[field] = parse_motor_count(value)
        else:
            row[field] = clean_text(value)
    missing = required_missing(row)
    row.update(
        is_complete=not missing,
        missing_fields_json=missing,
        normalization_version=NORMALIZATION_VERSION,
        normalized_at=datetime.now(timezone.utc),
    )
    return row


def required_missing(row: dict) -> list[str]:
    """Определить критичные пробелы в техническом ключе."""
    energy = row.get("energy_type")
    transmission = row.get("transmission_type") or row.get("transmission_summary")
    required = {
        "series_id": row.get("series_id"),
        "model_year": row.get("model_year"),
        "energy_type": energy,
        "transmission": transmission,
        "drive_type": row.get("drive_type"),
    }
    missing = [name for name, value in required.items() if value is None]
    if energy not in ELECTRIC_ENERGIES:
        if not (row.get("engine_model") or row.get("engine_summary")):
            missing.append("engine_identity")
        if not (row.get("engine_power_kw") or row.get("maximum_power_kw")):
            missing.append("engine_power_kw")
    if energy in ELECTRIC_ENERGIES | PLUG_IN_ENERGIES:
        electric = {
            "motor_power_kw": row.get("motor_total_power_kw")
            or row.get("maximum_power_kw"),
            "motor_count": row.get("motor_count"),
            "battery_capacity_kwh": row.get("battery_capacity_kwh"),
            "battery_type": row.get("battery_type"),
        }
        missing.extend(name for name, value in electric.items() if value is None)
    return sorted(set(missing))


def modification_signature(row: dict) -> dict:
    """Построить технический ключ модификации для нормализованной строки."""
    energy = row.get("energy_type")
    signature = {
        "series_id": row["series_id"],
        "model_year": row["model_year"],
        "energy_type": energy,
        "maximum_power_kw": decimal_key(row.get("maximum_power_kw")),
        "transmission": row.get("transmission_type")
        or row.get("transmission_summary"),
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
        }
    if energy in ELECTRIC_ENERGIES | PLUG_IN_ENERGIES:
        signature["electric"] = {
            "motor_power_kw": decimal_key(
                row.get("motor_total_power_kw") or row.get("maximum_power_kw")
            ),
            "motor_count": row.get("motor_count"),
            "motor_layout": row.get("motor_layout"),
            "system_power_kw": decimal_key(row.get("system_power_kw")),
            "battery_capacity_kwh": decimal_key(row.get("battery_capacity_kwh")),
            "battery_type": row.get("battery_type"),
        }
    if not row["is_complete"]:
        signature["incomplete_spec_id"] = row["spec_id"]
    return signature


def modification_row(row: dict) -> dict:
    """Построить строку модификации и её стабильный идентификатор."""
    key = json.dumps(
        modification_signature(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    modification_id = stable_id(key)
    engine = row.get("engine_summary") or row.get("engine_model")
    parts = [str(row.get("model_year") or ""), row.get("energy_type"), engine]
    if not engine and row.get("motor_total_power_kw") is not None:
        parts.append(f"{decimal_key(row['motor_total_power_kw'])} кВт")
    parts.extend(
        (
            row.get("transmission_summary") or row.get("transmission_type"),
            row.get("drive_type"),
        )
    )
    if row.get("battery_capacity_kwh") is not None:
        parts.append(f"{decimal_key(row['battery_capacity_kwh'])} кВт·ч")
    return {
        "id": modification_id,
        "modification_key": key,
        "series_id": row["series_id"],
        "model_year": row["model_year"],
        "name": " · ".join(part for part in parts if part),
        "energy_type": row["energy_type"],
        "engine_summary": row["engine_summary"],
        "engine_displacement_ml": row["engine_displacement_ml"],
        "engine_model": row["engine_model"],
        "engine_power_kw": row["engine_power_kw"],
        "maximum_power_kw": row["maximum_power_kw"],
        "transmission_summary": row["transmission_summary"],
        "transmission_type": row["transmission_type"],
        "transmission_gears": row["transmission_gears"],
        "drive_type": row["drive_type"],
        "motor_total_power_kw": row["motor_total_power_kw"],
        "motor_count": row["motor_count"],
        "motor_layout": row["motor_layout"],
        "system_power_kw": row["system_power_kw"],
        "battery_capacity_kwh": row["battery_capacity_kwh"],
        "battery_type": row["battery_type"],
        "is_complete": row["is_complete"],
        "spec_count": 0,
        "normalization_version": NORMALIZATION_VERSION,
        "generated_at": datetime.now(timezone.utc),
    }
