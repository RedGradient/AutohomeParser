from __future__ import annotations

import logging
import random
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scrapy.exceptions import DropItem
from sqlalchemy import bindparam, create_engine, event, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from autohome.items import (
    AttentionRankingItem,
    BrandItem,
    BrandManufacturerItem,
    BrandMonthlySaleItem,
    ConfigCrawlTaskItem,
    DiscountRankingItem,
    GalleryCrawlTaskItem,
    ManufacturerItem,
    MeasuredTestRankingItem,
    ModificationItem,
    NewEnergyRankingItem,
    ParameterColorItem,
    ParameterColorSetItem,
    ParameterDefinitionItem,
    ParameterGroupItem,
    ParameterSectionItem,
    ParameterSubitemItem,
    ResaleValueRankingItem,
    SeriesGalleryColorItem,
    SeriesItem,
    SeriesMonthlySaleItem,
    SeriesPhotoColorItem,
    SeriesPhotoItem,
    SmartTestRankingItem,
    SpecItem,
    SpecModificationItem,
    SpecParameterItem,
    SpecPowertrainItem,
    SpecVehicleAttributesItem,
    TechnologyRankingItem,
)
from autohome.models import (
    AttentionRanking,
    Brand,
    BrandManufacturer,
    BrandMonthlySale,
    ConfigCrawlTask,
    DiscountRanking,
    GalleryCrawlTask,
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
    ResaleValueRanking,
    Series,
    SeriesGalleryColor,
    SeriesMonthlySale,
    SeriesPhoto,
    SeriesPhotoColor,
    SmartTestRanking,
    Spec,
    SpecParameter,
    SpecPowertrain,
    SpecVehicleAttributes,
    TechnologyRanking,
)
from autohome.powertrain_schema import ensure_powertrain_schema
from autohome.translator import (
    translate_brand_name,
    translate_color_name,
    translate_equipment_name,
    translate_parameter_name,
    translate_parameter_value,
    translate_series_name,
    translate_spec_description,
    translate_spec_name,
    translate_taxonomy_name,
    translate_technology_name,
)
from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema

PRICE_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万元|万|元|юаней)?")
PRICE_RANGE_RE = re.compile(
    r"^\s*(?P<minimum>\d+(?:[.,]\d+)?)\s*(?P<minimum_unit>万元|万|元)?"
    r"\s*[-–—~至]\s*"
    r"(?P<maximum>\d+(?:[.,]\d+)?)\s*(?P<maximum_unit>万元|万|元)?\s*$"
)
PRICE_SINGLE_RE = re.compile(
    r"^\s*(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>万元|万|元)?\s*$"
)
MISSING_PRICE_VALUES = {"", "-", "--", "暂无", "暂无报价"}
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
    text = str(value).replace(",", "").strip()
    match = PRICE_RE.search(text)
    if not match:
        return None
    try:
        amount = Decimal(match.group("number"))
    except InvalidOperation:
        return None
    if match.group("unit") in {"万", "万元"} or "万" in text:
        amount *= Decimal(10000)
    return amount


def _full_yuan_amount(number: str, unit: str | None) -> Decimal:
    """Развернуть сокращённую сумму в полное количество юаней."""
    amount = Decimal(number.replace(",", "."))
    if unit in {"万", "万元"}:
        amount *= Decimal(10000)
    return amount


def _plain_decimal(value: Decimal) -> str:
    """Представить Decimal без экспоненты и незначащих нулей."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def normalize_price_text(value) -> str | None:
    """Нормализовать одиночную цену или диапазон в полные суммы в юанях."""
    if value is None:
        return None
    text = str(value).strip().replace("￥", "").replace("¥", "")
    if text in MISSING_PRICE_VALUES:
        return None

    range_match = PRICE_RANGE_RE.fullmatch(text)
    if range_match:
        minimum_unit = range_match.group("minimum_unit")
        maximum_unit = range_match.group("maximum_unit")
        shared_unit = maximum_unit or minimum_unit
        minimum = _full_yuan_amount(
            range_match.group("minimum"), minimum_unit or shared_unit
        )
        maximum = _full_yuan_amount(
            range_match.group("maximum"), maximum_unit or shared_unit
        )
        return f"{_plain_decimal(minimum)}-{_plain_decimal(maximum)}"

    single_match = PRICE_SINGLE_RE.fullmatch(text)
    if single_match:
        amount = _full_yuan_amount(
            single_match.group("number"), single_match.group("unit")
        )
        return _plain_decimal(amount)

    return text


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
        SpecVehicleAttributesItem: SpecVehicleAttributes,
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
        GalleryCrawlTaskItem: GalleryCrawlTask,
        ConfigCrawlTaskItem: ConfigCrawlTask,
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
        ensure_vehicle_attribute_schema(self.engine)
        ensure_powertrain_schema(self.engine)

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
        if isinstance(item, SpecItem) and not any(
            row.get(field) is not None and row[field] > 0
            for field in ("guide_price_yuan", "dealer_price_yuan")
        ):
            spec_id = row.get("id")
            raise DropItem(
                f"Комплектация spec_id={spec_id} пропущена: отсутствуют цены"
            )
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
                latest_links = {row["spec_id"]: row for row in links}
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
                modification_ids = sorted({row["modification_id"] for row in link_rows})
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
        if "price_text" in data:
            data["price_text"] = normalize_price_text(data.get("price_text"))

        if isinstance(item, BrandItem):
            data["name"] = translate_brand_name(data.get("name"))
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, SeriesItem):
            data["name"] = translate_series_name(data.get("name"))
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, SpecItem):
            data["name"] = translate_spec_name(data.get("name"))
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, ManufacturerItem):
            data["name"] = translate_taxonomy_name(data.get("name"))

        if isinstance(item, SpecItem):
            for field in (
                "guide_price_yuan",
                "dealer_price_yuan",
                "discount_yuan",
            ):
                data[field] = parse_yuan(data.get(field))
            data["description"] = translate_spec_description(data.get("description"))
        elif isinstance(item, (ParameterGroupItem, ParameterSectionItem)):
            data["name"] = translate_taxonomy_name(data.get("name"))
        elif isinstance(item, ParameterDefinitionItem):
            data["name"] = translate_parameter_name(data.get("name"))
        elif isinstance(item, SpecParameterItem):
            data["value"] = translate_parameter_value(data.get("value"))
            data["option_price_yuan"] = parse_yuan(data.get("option_price_yuan"))
        elif isinstance(item, ParameterSubitemItem):
            data["name"] = translate_equipment_name(data.get("name"))
            data["value"] = parse_equipment_value(data.get("value"))
            data["option_price_yuan"] = parse_yuan(data.get("option_price_yuan"))
        elif isinstance(item, ParameterColorItem):
            data["name"] = translate_color_name(data.get("name"))
            data["price_yuan"] = parse_yuan(data.get("price_yuan"))
        elif isinstance(item, SeriesGalleryColorItem):
            data["name"] = translate_color_name(data.get("name"))
        elif isinstance(item, SeriesPhotoItem):
            data["title"] = translate_spec_name(data.get("title"))
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, (SeriesMonthlySaleItem, BrandMonthlySaleItem)):
            if isinstance(item, SeriesMonthlySaleItem):
                data["series_name"] = translate_series_name(data.get("series_name"))
            else:
                data["brand_name"] = translate_brand_name(data.get("brand_name"))
            data["fetched_at"] = datetime.now(UTC)
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
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, TechnologyRankingItem):
            data["name"] = translate_technology_name(data.get("name"))
            data["fetched_at"] = datetime.now(UTC)
        elif isinstance(item, (GalleryCrawlTaskItem, ConfigCrawlTaskItem)):
            data["updated_at"] = datetime.now(UTC)
        return data
