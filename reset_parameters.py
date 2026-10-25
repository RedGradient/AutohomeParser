from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, delete, update

from autohome.models import (
    Modification,
    ParameterColor,
    ParameterColorSet,
    ParameterDefinition,
    ParameterGroup,
    ParameterSection,
    ParameterSubitem,
    Spec,
    SpecParameter,
    SpecPowertrain,
    SpecVehicleAttributes,
)

PARAMETER_MODELS = (
    ParameterColor,
    ParameterColorSet,
    ParameterSubitem,
    SpecParameter,
    ParameterDefinition,
    ParameterSection,
    ParameterGroup,
)


def parse_arguments() -> argparse.Namespace:
    """Разобрать адрес базы и обязательное подтверждение удаления."""
    parser = argparse.ArgumentParser(
        description="Очистить данные технических характеристик."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить безвозвратное удаление сохранённых характеристик.",
    )
    return parser.parse_args()


def main() -> int:
    """Очистить параметры, не затрагивая схему, каталог и медиа."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if not args.yes:
        raise SystemExit("Добавьте --yes для подтверждения удаления параметров")

    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(update(Spec).values(modification_id=None))
            connection.execute(delete(SpecPowertrain))
            connection.execute(delete(SpecVehicleAttributes))
            connection.execute(delete(Modification))
            for model in PARAMETER_MODELS:
                connection.execute(delete(model))
    finally:
        engine.dispose()

    print("Данные технических характеристик удалены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
