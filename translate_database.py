from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable

from sqlalchemy import bindparam, create_engine, select, update

from autohome.models import Brand, ParameterDefinition, Series, Spec, SpecParameter
from autohome.translator import (
    translate_exact,
    translate_parameter_name,
    translate_structure,
    translate_vehicle_name,
)


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры постобработки существующей базы."""
    parser = argparse.ArgumentParser(
        description="Перевод существующих нормализованных полей базы на русский."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


def translated_json(value: str | None) -> str | None:
    """Перевести значения JSON-строки, сохранив её компактный формат."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value
    translated = translate_structure(parsed)
    return json.dumps(translated, ensure_ascii=False, separators=(",", ":"))


def update_table(
    engine,
    model,
    primary_key: str,
    fields: dict[str, Callable[[Any], Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Перевести таблицу пакетами и вернуть числа просмотренных и изменённых строк."""
    table = model.__table__
    key_column = table.c[primary_key]
    selected_columns = [key_column, *(table.c[name] for name in fields)]
    last_key = None
    scanned = 0
    changed = 0

    while True:
        query = select(*selected_columns).order_by(key_column).limit(batch_size)
        if last_key is not None:
            query = query.where(key_column > last_key)
        with engine.begin() as connection:
            rows = connection.execute(query).mappings().all()
            if not rows:
                break
            updates = []
            for row in rows:
                values = {name: transform(row[name]) for name, transform in fields.items()}
                if any(values[name] != row[name] for name in fields):
                    updates.append({"_row_key": row[primary_key], **values})
            if updates:
                statement = (
                    update(table)
                    .where(key_column == bindparam("_row_key"))
                    .values({name: bindparam(name) for name in fields})
                )
                connection.execute(statement, updates)
            last_key = rows[-1][primary_key]
            scanned += len(rows)
            changed += len(updates)
            print(
                f"{table.name}: просмотрено {scanned}, изменено {changed}",
                flush=True,
            )
    return scanned, changed


def main() -> int:
    """Перевести нормализованные поля всех поддерживаемых таблиц."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.batch_size <= 0:
        raise SystemExit("batch-size должен быть положительным")

    engine = create_engine(args.database_url, pool_pre_ping=True)
    jobs = (
        (Brand, "id", {"name": translate_vehicle_name}),
        (Series, "id", {"name": translate_vehicle_name}),
        (
            Spec,
            "id",
            {
                "name": translate_vehicle_name,
                "guide_price": translate_exact,
                "dealer_price": translate_exact,
                "discount": translate_exact,
                "description": translate_exact,
            },
        ),
        (
            ParameterDefinition,
            "title_id",
            {
                "name": translate_parameter_name,
                "group_name": translate_exact,
                "section_name": translate_exact,
            },
        ),
        (
            SpecParameter,
            "id",
            {
                "value": translate_exact,
                "option_price": translate_exact,
                "subitems_json": translated_json,
                "color_info_json": translated_json,
            },
        ),
    )
    try:
        for model, primary_key, fields in jobs:
            update_table(engine, model, primary_key, fields, args.batch_size)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
