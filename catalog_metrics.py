from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select

from autohome.models import (
    Brand,
    Manufacturer,
    Modification,
    Series,
    SeriesPhoto,
    Spec,
    SpecParameter,
    SpecPowertrain,
)


DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://autohome:autohome@127.0.0.1:5432/autohome",
)

# Коды состояния из дерева Autohome. Состояние 30 встречается у актуальных
# серий со смешанным набором продающихся и снятых комплектаций. Код 0 в
# текущем каталоге преимущественно соответствует архивным и пустым сериям.
SERIES_STATUS_GROUPS = {
    "current": (20, 30),
    "discontinued": (0, 40),
    "upcoming": (10,),
}


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры запуска отчёта."""
    parser = argparse.ArgumentParser(
        description="Рассчитать основные метрики каталога Autohome."
    )
    parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="URL базы SQLAlchemy; по умолчанию используется DATABASE_URL.",
    )
    parser.add_argument(
        "--small-parameter-threshold",
        type=int,
        default=140,
        help=(
            "Конфигурации с ненулевым числом параметров ниже этого порога "
            "считаются подозрительными."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Формат результата.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Количество строк группировок в текстовом выводе; 0 — все.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Записать результат в файл вместо стандартного вывода.",
    )
    return parser.parse_args()


def _count(connection, model) -> int:
    """Посчитать все строки указанной таблицы."""
    return int(connection.scalar(select(func.count()).select_from(model)) or 0)


def collect_catalog_metrics(
    database_url: str,
    small_parameter_threshold: int = 140,
) -> dict[str, Any]:
    """Собрать метрики каталога, цен и полноты конфигураций."""
    if small_parameter_threshold <= 0:
        raise ValueError("Порог малого числа параметров должен быть положительным")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            totals = {
                "brands": _count(connection, Brand),
                "manufacturers": _count(connection, Manufacturer),
                "series": _count(connection, Series),
                "specs": _count(connection, Spec),
                "modifications": _count(connection, Modification),
            }
            totals["main_entities"] = sum(totals.values())

            series_by_brand = [
                {
                    "brand_id": brand_id,
                    "brand_name": brand_name,
                    "series_count": int(series_count),
                }
                for brand_id, brand_name, series_count in connection.execute(
                    select(Brand.id, Brand.name, func.count(Series.id))
                    .outerjoin(Series, Series.brand_id == Brand.id)
                    .group_by(Brand.id, Brand.name)
                    .order_by(func.count(Series.id).desc(), Brand.name)
                )
            ]

            spec_counts = (
                select(
                    Spec.series_id.label("series_id"),
                    func.count().label("spec_count"),
                )
                .group_by(Spec.series_id)
                .subquery()
            )
            modification_counts = (
                select(
                    Modification.series_id.label("series_id"),
                    func.count().label("modification_count"),
                )
                .group_by(Modification.series_id)
                .subquery()
            )
            grouped_statement = (
                select(
                    Brand.id.label("brand_id"),
                    Brand.name.label("brand_name"),
                    Series.id.label("series_id"),
                    Series.name.label("series_name"),
                    func.coalesce(spec_counts.c.spec_count, 0).label("spec_count"),
                    func.coalesce(
                        modification_counts.c.modification_count, 0
                    ).label("modification_count"),
                )
                .select_from(Series)
                .outerjoin(Brand, Brand.id == Series.brand_id)
                .outerjoin(spec_counts, spec_counts.c.series_id == Series.id)
                .outerjoin(
                    modification_counts,
                    modification_counts.c.series_id == Series.id,
                )
                .order_by(Brand.name, Series.name, Series.id)
            )
            by_brand_and_series = [dict(row) for row in connection.execute(
                grouped_statement
            ).mappings()]

            status_counts = {
                name: int(
                    connection.scalar(
                        select(func.count())
                        .select_from(Series)
                        .where(Series.state.in_(codes))
                    )
                    or 0
                )
                for name, codes in SERIES_STATUS_GROUPS.items()
            }
            status_counts["unknown"] = int(
                connection.scalar(
                    select(func.count())
                    .select_from(Series)
                    .where(Series.state.is_(None))
                )
                or 0
            )

            price_counts = dict(
                connection.execute(
                    select(
                        func.count()
                        .filter(Spec.guide_price_yuan.is_not(None))
                        .label("with_guide_price"),
                        func.count()
                        .filter(Spec.guide_price_yuan.is_(None))
                        .label("without_guide_price"),
                    )
                ).one()._mapping
            )
            price_counts = {
                "with_guide_price": int(price_counts["with_guide_price"]),
                "without_guide_price": int(price_counts["without_guide_price"]),
            }

            has_gallery_photo = (
                select(SeriesPhoto.id)
                .where(SeriesPhoto.spec_id == Spec.id)
                .exists()
            )
            has_photo = (
                Spec.image_url.is_not(None) & (func.length(Spec.image_url) > 0)
            ) | has_gallery_photo
            photo_counts_row = connection.execute(
                select(
                    func.count().filter(has_photo).label("with_photo"),
                    func.count().filter(~has_photo).label("without_photo"),
                )
            ).one()._mapping
            photo_counts = {
                "with_photo": int(photo_counts_row["with_photo"]),
                "without_photo": int(photo_counts_row["without_photo"]),
            }

            parameter_counts = (
                select(
                    SpecParameter.spec_id.label("spec_id"),
                    func.count().label("parameter_count"),
                )
                .group_by(SpecParameter.spec_id)
                .subquery()
            )
            complete_configuration_count = int(
                connection.scalar(
                    select(func.count())
                    .select_from(Spec)
                    .join(parameter_counts, parameter_counts.c.spec_id == Spec.id)
                    .join(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
                    .where(Spec.modification_id.is_not(None))
                )
                or 0
            )
            suspicious_rows = [
                {
                    "spec_id": spec_id,
                    "spec_name": spec_name,
                    "series_id": series_id,
                    "series_name": series_name,
                    "parameter_count": int(parameter_count),
                }
                for spec_id, spec_name, series_id, series_name, parameter_count
                in connection.execute(
                    select(
                        Spec.id,
                        Spec.name,
                        Series.id,
                        Series.name,
                        parameter_counts.c.parameter_count,
                    )
                    .join(parameter_counts, parameter_counts.c.spec_id == Spec.id)
                    .outerjoin(Series, Series.id == Spec.series_id)
                    .where(
                        parameter_counts.c.parameter_count > 0,
                        parameter_counts.c.parameter_count
                        < small_parameter_threshold,
                    )
                    .order_by(parameter_counts.c.parameter_count, Spec.id)
                )
            ]

            return {
                "catalog_size": totals,
                "series_by_brand": series_by_brand,
                "specs_and_modifications_by_brand_and_series": (
                    by_brand_and_series
                ),
                "series_status": {
                    **status_counts,
                    "state_codes": SERIES_STATUS_GROUPS,
                },
                "prices": price_counts,
                "photos": photo_counts,
                "configurations": {
                    "complete": complete_configuration_count,
                    "total_specs": totals["specs"],
                    "suspiciously_small": len(suspicious_rows),
                    "small_parameter_threshold": small_parameter_threshold,
                    "suspicious_specs": suspicious_rows,
                },
            }
    finally:
        engine.dispose()


def _limited(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Ограничить текстовое представление списка строк."""
    return rows if limit == 0 else rows[: max(0, limit)]


def format_text(metrics: dict[str, Any], limit: int = 20) -> str:
    """Сформировать компактный человекочитаемый отчёт."""
    size = metrics["catalog_size"]
    statuses = metrics["series_status"]
    prices = metrics["prices"]
    photos = metrics["photos"]
    configs = metrics["configurations"]
    lines = [
        "Размер каталога",
        f"  Бренды: {size['brands']:,}",
        f"  Производители: {size['manufacturers']:,}",
        f"  Серии: {size['series']:,}",
        f"  Комплектации: {size['specs']:,}",
        f"  Модификации: {size['modifications']:,}",
        f"  Всего основных сущностей: {size['main_entities']:,}",
        "",
        "Состояние серий",
        f"  Актуальные: {statuses['current']:,}",
        f"  Снятые с производства: {statuses['discontinued']:,}",
        f"  Ожидаемые: {statuses['upcoming']:,}",
        f"  Без состояния: {statuses['unknown']:,}",
        "",
        "Цены комплектаций",
        f"  С рекомендованной ценой: {prices['with_guide_price']:,}",
        f"  Без рекомендованной цены: {prices['without_guide_price']:,}",
        "",
        "Фотографии комплектаций",
        f"  С фотографией: {photos['with_photo']:,}",
        f"  Без фотографии: {photos['without_photo']:,}",
        "",
        "Полнота конфигураций",
        f"  Полные конфигурации: {configs['complete']:,}",
        (
            "  Подозрительно мало параметров "
            f"(< {configs['small_parameter_threshold']}): "
            f"{configs['suspiciously_small']:,}"
        ),
        "",
        "Серии по брендам",
    ]
    for row in _limited(metrics["series_by_brand"], limit):
        lines.append(f"  {row['brand_name']}: {row['series_count']:,}")

    lines.extend(("", "Комплектации и модификации по сериям"))
    grouped = metrics["specs_and_modifications_by_brand_and_series"]
    grouped = sorted(
        grouped,
        key=lambda row: (row["spec_count"], row["modification_count"]),
        reverse=True,
    )
    for row in _limited(grouped, limit):
        lines.append(
            f"  {row['brand_name'] or 'Без бренда'} / {row['series_name']}: "
            f"комплектаций {row['spec_count']:,}, "
            f"модификаций {row['modification_count']:,}"
        )
    if limit and len(grouped) > limit:
        lines.append(
            f"  … ещё {len(grouped) - limit:,} строк; "
            "используйте --limit 0 или --format json"
        )
    return "\n".join(lines)


def main() -> int:
    """Рассчитать и вывести метрики каталога."""
    args = parse_arguments()
    metrics = collect_catalog_metrics(
        args.database_url,
        args.small_parameter_threshold,
    )
    if args.format == "json":
        rendered = json.dumps(metrics, ensure_ascii=False, indent=2, default=str)
    else:
        rendered = format_text(metrics, args.limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
