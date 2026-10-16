from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
import random
import re
import time

from sqlalchemy import bindparam, create_engine, event, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from autohome.items import (
    AttentionRankingItem,
    BrandMonthlySaleItem,
    BrandItem,
    BrandManufacturerItem,
    DiscountRankingItem,
    ManufacturerItem,
    MeasuredTestRankingItem,
    NewEnergyRankingItem,
    ParameterColorItem,
    ParameterColorSetItem,
    ParameterDefinitionItem,
    ParameterGroupItem,
    ParameterSectionItem,
    ParameterSubitemItem,
    SeriesItem,
    SeriesGalleryColorItem,
    SeriesMonthlySaleItem,
    SeriesPhotoColorItem,
    SeriesPhotoItem,
    SmartTestRankingItem,
    SpecItem,
    ModificationItem,
    SpecModificationItem,
    SpecParameterItem,
    SpecPowertrainItem,
    ResaleValueRankingItem,
    TechnologyRankingItem,
)
from autohome.models import (
    AttentionRanking,
    Base,
    Brand,
    BrandMonthlySale,
    BrandManufacturer,
    DiscountRanking,
    Manufacturer,
    MeasuredTestRanking,
    Modification,
    NewEnergyRanking,
    ParameterColor,
    ParameterColorSet,
    ParameterDefinition,
    ParameterGroup,
    ParameterSection,
    ParameterSubitem,
    Series,
    SeriesGalleryColor,
    SeriesMonthlySale,
    SeriesPhoto,
    SeriesPhotoColor,
    SmartTestRanking,
    Spec,
    SpecPowertrain,
    SpecParameter,
    ResaleValueRanking,
    TechnologyRanking,
)
from autohome.translator import (
    translate_brand_name,
    translate_exact,
    translate_parameter_name,
    translate_series_name,
    translate_spec_name,
)


PRICE_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万元|万|元|юаней)?")
LOGGER = logging.getLogger(__name__)
RETRYABLE_SQLSTATES = {"40P01"}


def parse_equipment_value(value) -> bool | None:
    """Преобразовать обозначение оснащения Autohome в булево значение."""
    normalized = str(value or "").strip()
    if normalized in {"●", "Штатно"}:
        return True
    if normalized in {"○", "Опция", "-", "Нет"}:
        return False
    return None


def parse_yuan(value) -> Decimal | None:
    """Преобразовать цену Autohome в числовое значение в юанях."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    match = PRICE_RE.search(str(value).replace(",", "").strip())
    if not match:
        return None
    try:
        amount = Decimal(match.group("number"))
    except InvalidOperation:
        return None
    if match.group("unit") in {"万", "万元"}:
        amount *= Decimal("10000")
    return amount


class SqlAlchemyPipeline:
    """Пакетно сохранять нормализованные элементы Scrapy через SQLAlchemy."""

    model_by_item = {
        BrandItem: Brand,
        ManufacturerItem: Manufacturer,
        BrandManufacturerItem: BrandManufacturer,
        SeriesItem: Series,
        SpecItem: Spec,
        ParameterGroupItem: ParameterGroup,
        ParameterSectionItem: ParameterSection,
        ParameterDefinitionItem: ParameterDefinition,
        ModificationItem: Modification,
        SpecPowertrainItem: SpecPowertrain,
        SpecParameterItem: SpecParameter,
        ParameterSubitemItem: ParameterSubitem,
        ParameterColorSetItem: ParameterColorSet,
        ParameterColorItem: ParameterColor,
        SeriesMonthlySaleItem: SeriesMonthlySale,
        BrandMonthlySaleItem: BrandMonthlySale,
        NewEnergyRankingItem: NewEnergyRanking,
        SmartTestRankingItem: SmartTestRanking,
        AttentionRankingItem: AttentionRanking,
        ResaleValueRankingItem: ResaleValueRanking,
        DiscountRankingItem: DiscountRanking,
        TechnologyRankingItem: TechnologyRanking,
        MeasuredTestRankingItem: MeasuredTestRanking,
        SeriesGalleryColorItem: SeriesGalleryColor,
        SeriesPhotoItem: SeriesPhoto,
        SeriesPhotoColorItem: SeriesPhotoColor,
    }

    reference_models = frozenset(
        {ParameterGroup, ParameterSection, ParameterDefinition}
    )

    def __init__(
        self,
        database_url: str,
        batch_size: int,
        deadlock_retries: int,
        deadlock_retry_delay: float,
    ):
        """Инициализировать pipeline адресом базы и размером пакета."""
        self.database_url = database_url
        self.batch_size = batch_size
        self.deadlock_retries = deadlock_retries
        self.deadlock_retry_delay = deadlock_retry_delay
        self.buffers = defaultdict(list)
        self.buffered = 0

    @classmethod
    def from_crawler(cls, crawler):
        """Создать pipeline на основе настроек текущего crawler."""
        return cls(
            crawler.settings.get("DATABASE_URL"),
            crawler.settings.getint("DATABASE_BATCH_SIZE", 1000),
            crawler.settings.getint("DATABASE_DEADLOCK_RETRIES", 6),
            crawler.settings.getfloat("DATABASE_DEADLOCK_RETRY_DELAY", 0.1),
        )

    def open_spider(self):
        """Подключиться к базе и создать отсутствующие таблицы."""
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(self.database_url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", self._configure_sqlite)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _configure_sqlite(dbapi_connection, _):
        """Настроить SQLite для пакетной записи и параллельного чтения."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def process_item(self, item):
        """Добавить элемент в буфер и записать заполненный пакет."""
        row = self._serialize(item)
        self.buffers[type(item)].append(row)
        self.buffered += 1
        if self.buffered >= self.batch_size:
            self.flush()
        return item

    def close_spider(self):
        """Записать остаток буфера и освободить подключение к базе."""
        self.flush()
        self.engine.dispose()

    def flush(self):
        """Сохранить пакет, повторяя транзакцию после взаимной блокировки."""
        if not self.buffered:
            return

        for attempt in range(self.deadlock_retries + 1):
            try:
                self._flush_once()
                break
            except DBAPIError as error:
                sqlstate = getattr(error.orig, "sqlstate", None)
                if (
                    sqlstate not in RETRYABLE_SQLSTATES
                    or attempt >= self.deadlock_retries
                ):
                    raise
                delay = min(
                    self.deadlock_retry_delay * (2**attempt),
                    2.0,
                )
                delay += random.uniform(0, self.deadlock_retry_delay)
                LOGGER.warning(
                    "PostgreSQL отклонил пакет из-за deadlock; "
                    "повтор %d/%d через %.2f с",
                    attempt + 1,
                    self.deadlock_retries,
                    delay,
                )
                time.sleep(delay)

        self.buffers.clear()
        self.buffered = 0

    def _flush_once(self):
        """Выполнить одну попытку пакетной транзакции."""
        with Session(self.engine) as session, session.begin():
            for item_type, model in self.model_by_item.items():
                rows = self.buffers.get(item_type)
                if not rows:
                    continue
                rows = self._deduplicate_rows(model, rows)
                statement = self._insert(model).values(rows)
                primary_keys = tuple(
                    column.name for column in model.__table__.primary_key
                )
                update_columns = {
                    name: getattr(statement.excluded, name)
                    for name in rows[0]
                    if name not in primary_keys
                }
                if model in self.reference_models:
                    statement = statement.on_conflict_do_nothing(
                        index_elements=primary_keys
                    )
                elif update_columns:
                    statement = statement.on_conflict_do_update(
                        index_elements=primary_keys, set_=update_columns
                    )
                else:
                    statement = statement.on_conflict_do_nothing(
                        index_elements=primary_keys
                    )
                session.execute(statement)

            links = self.buffers.get(SpecModificationItem)
            if links:
                latest_links = {
                    row["spec_id"]: row for row in links
                }
                link_rows = [latest_links[key] for key in sorted(latest_links)]
                session.execute(
                    update(Spec.__table__)
                    .where(Spec.__table__.c.id == bindparam("_spec_id"))
                    .values(modification_id=bindparam("modification_id")),
                    [
                        {
                            "_spec_id": row["spec_id"],
                            "modification_id": row["modification_id"],
                        }
                        for row in link_rows
                    ],
                )
                modification_ids = sorted(
                    {row["modification_id"] for row in link_rows}
                )
                spec_count = (
                    select(func.count())
                    .where(Spec.modification_id == Modification.id)
                    .scalar_subquery()
                )
                session.execute(
                    update(Modification)
                    .where(Modification.id.in_(modification_ids))
                    .values(spec_count=spec_count)
                )

    def _insert(self, model):
        """Создать совместимый с текущей СУБД оператор INSERT с UPSERT."""
        if self.engine.dialect.name == "postgresql":
            return postgresql_insert(model)
        if self.engine.dialect.name == "sqlite":
            return sqlite_insert(model)
        raise RuntimeError(
            f"СУБД {self.engine.dialect.name} не поддерживается pipeline"
        )

    @staticmethod
    def _deduplicate_rows(model, rows: list[dict]) -> list[dict]:
        """Оставить последнюю строку для каждого первичного ключа пакета."""
        key_columns = tuple(column.name for column in model.__table__.primary_key)
        unique_rows = {
            tuple(row[column] for column in key_columns): row for row in rows
        }
        return [unique_rows[key] for key in sorted(unique_rows)]

    @staticmethod
    def _serialize(item):
        """Преобразовать Scrapy Item в типизированную строку базы."""
        data = dict(item)
        if "raw" in data:
            data["raw_json"] = data.pop("raw")

        if isinstance(item, BrandItem):
            data["name"] = translate_brand_name(data.get("name"))
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(item, SeriesItem):
            data["name"] = translate_series_name(data.get("name"))
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(item, SpecItem):
            data["name"] = translate_spec_name(data.get("name"))
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(item, ManufacturerItem):
            data["name"] = translate_exact(data.get("name"))

        if isinstance(item, SpecItem):
            for field in (
                "guide_price_yuan",
                "dealer_price_yuan",
                "discount_yuan",
            ):
                data[field] = parse_yuan(data.get(field))
            data["description"] = translate_exact(data.get("description"))
        elif isinstance(item, (ParameterGroupItem, ParameterSectionItem)):
            data["name"] = translate_exact(data.get("name"))
        elif isinstance(item, ParameterDefinitionItem):
            data["name"] = translate_parameter_name(data.get("name"))
        elif isinstance(item, SpecParameterItem):
            data["value"] = translate_exact(data.get("value"))
            data["option_price_yuan"] = parse_yuan(data.get("option_price_yuan"))
        elif isinstance(item, ParameterSubitemItem):
            data["name"] = translate_exact(data.get("name"))
            data["value"] = parse_equipment_value(data.get("value"))
            data["option_price_yuan"] = parse_yuan(data.get("option_price_yuan"))
        elif isinstance(item, ParameterColorItem):
            data["name"] = translate_exact(data.get("name"))
            data["price_yuan"] = parse_yuan(data.get("price_yuan"))
        elif isinstance(item, SeriesGalleryColorItem):
            data["name"] = translate_exact(data.get("name"))
        elif isinstance(item, SeriesPhotoItem):
            data["title"] = translate_series_name(data.get("title"))
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(item, (SeriesMonthlySaleItem, BrandMonthlySaleItem)):
            if isinstance(item, SeriesMonthlySaleItem):
                data["series_name"] = translate_series_name(data.get("series_name"))
            else:
                data["brand_name"] = translate_brand_name(data.get("brand_name"))
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(
            item,
            (
                NewEnergyRankingItem,
                SmartTestRankingItem,
                AttentionRankingItem,
                ResaleValueRankingItem,
                DiscountRankingItem,
                MeasuredTestRankingItem,
            ),
        ):
            data["series_name"] = translate_series_name(data.get("series_name"))
            if "spec_name" in data:
                data["spec_name"] = translate_spec_name(data.get("spec_name"))
            if "tested_spec_name" in data:
                data["tested_spec_name"] = translate_spec_name(
                    data.get("tested_spec_name")
                )
            data["fetched_at"] = datetime.now(timezone.utc)
        elif isinstance(item, TechnologyRankingItem):
            data["name"] = translate_exact(data.get("name"))
            data["fetched_at"] = datetime.now(timezone.utc)
        return data
