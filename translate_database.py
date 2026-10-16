from __future__ import annotations

import argparse
import os
from typing import Any, Callable

from sqlalchemy import and_, bindparam, create_engine, select, tuple_, update

from autohome.models import (
    Brand,
    Manufacturer,
    ParameterColor,
    ParameterDefinition,
    ParameterGroup,
    ParameterSection,
    ParameterSubitem,
    Series,
    Spec,
    SpecParameter,
)
from autohome.translator import (
    translate_brand_name,
    translate_exact,
    translate_parameter_name,
    translate_series_name,
    translate_spec_name,
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


def update_table(
    engine,
    model,
    primary_keys: tuple[str, ...],
    fields: dict[str, Callable[[Any], Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Перевести таблицу пакетами и вернуть числа просмотренных и изменённых строк."""
    table = model.__table__
    key_columns = [table.c[name] for name in primary_keys]
    selected_columns = [*key_columns, *(table.c[name] for name in fields)]
    last_key = None
    scanned = 0
    changed = 0

    while True:
        query = select(*selected_columns).order_by(*key_columns).limit(batch_size)
        if last_key is not None:
            if len(key_columns) == 1:
                query = query.where(key_columns[0] > last_key[0])
            else:
                query = query.where(tuple_(*key_columns) > last_key)
        with engine.begin() as connection:
            rows = connection.execute(query).mappings().all()
            if not rows:
                break
            updates = []
            for row in rows:
                values = {name: transform(row[name]) for name, transform in fields.items()}
                if any(values[name] != row[name] for name in fields):
                    key_values = {
                        f"_pk_{name}": row[name] for name in primary_keys
                    }
                    updates.append({**key_values, **values})
            if updates:
                statement = (
                    update(table)
                    .where(
                        and_(
                            *(
                                table.c[name] == bindparam(f"_pk_{name}")
                                for name in primary_keys
                            )
                        )
                    )
                    .values({name: bindparam(name) for name in fields})
                )
                connection.execute(statement, updates)
            last_key = tuple(rows[-1][name] for name in primary_keys)
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
        (Brand, ("id",), {"name": translate_brand_name}),
        (Manufacturer, ("id",), {"name": translate_exact}),
        (Series, ("id",), {"name": translate_series_name}),
        (
            Spec,
            ("id",),
            {
                "name": translate_spec_name,
                "description": translate_exact,
            },
        ),
        (ParameterGroup, ("id",), {"name": translate_exact}),
        (ParameterSection, ("id",), {"name": translate_exact}),
        (
            ParameterDefinition,
            ("id",),
            {"name": translate_parameter_name},
        ),
        (
            SpecParameter,
            ("spec_id", "parameter_id"),
            {"value": translate_exact},
        ),
        (
            ParameterSubitem,
            ("spec_id", "parameter_id", "position"),
            {"name": translate_exact, "value": translate_exact},
        ),
        (
            ParameterColor,
            ("spec_id", "parameter_id", "position"),
            {"name": translate_exact},
        ),
    )
    try:
        for model, primary_keys, fields in jobs:
            update_table(engine, model, primary_keys, fields, args.batch_size)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
