from __future__ import annotations

from collections import deque
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import blake2b
import json
import subprocess
from pathlib import Path
import re
from typing import Any, Iterable

import scrapy
from scrapy.http import TextResponse
from sqlalchemy import create_engine, select

from autohome.items import (
    AttentionRankingItem,
    BrandMonthlySaleItem,
    BrandManufacturerItem,
    BrandItem,
    ConfigCrawlTaskItem,
    DiscountRankingItem,
    GalleryCrawlTaskItem,
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
    ModificationItem,
    SpecItem,
    SpecModificationItem,
    SpecParameterItem,
    SpecPowertrainItem,
    SpecVehicleAttributesItem,
    ResaleValueRankingItem,
    TechnologyRankingItem,
)
from autohome.models import (
    ConfigCrawlTask,
    GalleryCrawlTask,
    Series,
    Spec,
    SpecParameter,
    SpecPowertrain,
)
from autohome.powertrain_normalizer import (
    PATH_TO_FIELD,
    SUBITEM_FIELDS,
    modification_row,
    normalize_powertrain,
)
from autohome.translator import translate_powertrain_code, translate_powertrain_field
from autohome.vehicle_attributes_normalizer import (
    PATH_TO_FIELD as VEHICLE_ATTRIBUTE_PATH_TO_FIELD,
    REQUIRED_SOURCE_FIELDS as REQUIRED_VEHICLE_ATTRIBUTE_SOURCE_FIELDS,
    normalize_vehicle_attributes,
)


def first(mapping: dict, *keys, default=None):
    """Вернуть первое непустое значение из перечисленных ключей."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def as_int(value):
    """Преобразовать значение в целое число либо вернуть None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value) -> bool:
    """Преобразовать строковое значение аргумента паука в bool."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def stable_id(*parts: object) -> int:
    """Построить устойчивый положительный BIGINT из строковых частей."""
    source = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(blake2b(source, digest_size=8).digest(), "big") >> 1


def decimal_from_text(value: object) -> Decimal | None:
    """Извлечь первое десятичное число из текстового значения."""
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return Decimal(match.group().replace(",", "."))
    except InvalidOperation:
        return None


def yuan_from_text(value: object) -> Decimal | None:
    """Преобразовать сумму с китайской единицей 万 в юани."""
    amount = decimal_from_text(value)
    if amount is None:
        return None
    if "万" in str(value):
        amount *= Decimal("10000")
    return amount


def has_vehicle_price(guide_price: object, dealer_price: object) -> bool:
    """Проверить наличие хотя бы одной положительной цены автомобиля."""
    return any(
        price is not None and price > 0
        for price in (yuan_from_text(guide_price), yuan_from_text(dealer_price))
    )


def text_after_colon(value: object) -> str | None:
    """Вернуть содержимое после китайского или обычного двоеточия."""
    text = str(value or "").strip()
    if not text:
        return None
    return re.split(r"[:：]", text, maxsplit=1)[-1].strip() or None


def walk_objects(value: Any) -> Iterable[dict]:
    """Рекурсивно обойти все словари во вложенной JSON-структуре."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


class CarsSpider(scrapy.Spider):
    """Собирать каталог, параметры, продажи и фотогалереи Autohome."""
    name = "cars"
    allowed_domains = [
        "www.autohome.com.cn",
        "car.app.autohome.com.cn",
        "car.autohome.com.cn",
    ]

    tree_url = "https://www.autohome.com.cn/web-main/car/web/price/treeMenu?extendseries=1"
    spec_list_url = (
        "https://car.app.autohome.com.cn/carMiddle/getSpecListBySeriesId"
        "?seriesId={series_id}&appId=pc&cityId={city_id}"
    )
    config_url = (
        "https://www.autohome.com.cn/web-main/car/param/getParamConf"
        "?mode=1&site=2&specid={spec_id}"
    )
    rank_url = "https://www.autohome.com.cn/web-main/car/rank/getList"
    sales_rank_page = "https://www.autohome.com.cn/rank/1"
    new_energy_rank_page = "https://www.autohome.com.cn/rank/9"
    static_rankings = (
        ("smart_test", {"typeid": "20", "subranktypeid": "1", "subrank": "1001"}),
        (
            "attention",
            {"typeid": "2", "subranktypeid": "2001", "levelid": "0", "price": "0-9000"},
        ),
        ("resale", {"typeid": "6", "levelid": "0", "price": "0-9000"}),
        ("discount", {"typeid": "3", "levelid": "0"}),
        ("technology", {"typeid": "16"}),
        (
            "measured",
            {
                "typeid": "8",
                "subranktypeid": "101",
                "subrank": "1011",
                "levelid": "0",
                "price": "0-9000",
            },
        ),
    )
    gallery_url = "https://car.autohome.com.cn/pic/series/{series_id}-{category_id}.html"
    gallery_category_names = {
        1: "Экстерьер",
        10: "Панель управления и руль",
        3: "Салон и сиденья",
        12: "Прочие детали",
        53: "Официальные изображения",
        51: "Тюнинг",
    }

    custom_settings = {
        "REFERER_ENABLED": True,
    }

    def __init__(
        self,
        city_id="110100",
        series_id=None,
        max_series="0",
        max_config_requests_per_series="0",
        resume_configs="0",
        max_resume_specs="0",
        worker_index="0",
        worker_count="1",
        bind_address=None,
        parse_sales="1",
        sales_months="6",
        parse_galleries="1",
        gallery_categories="1,10,3,12,53,51",
        catalog_path="data/tree_menu.json",
        catalog_preloaded="0",
        *args,
        **kwargs,
    ):
        """Инициализировать режим запуска и ограничения паука."""
        super().__init__(*args, **kwargs)
        self.city_id = city_id
        self.only_series_id = as_int(series_id)
        self.max_series = as_int(max_series) or 0
        self.max_config_requests_per_series = (
            as_int(max_config_requests_per_series) or 0
        )
        self.resume_configs = as_bool(resume_configs)
        self.max_resume_specs = as_int(max_resume_specs) or 0
        self.worker_index = as_int(worker_index) or 0
        self.worker_count = as_int(worker_count) or 1
        self.bind_address = bind_address or None
        self.parse_sales = as_bool(parse_sales)
        self.sales_months = max(0, as_int(sales_months) or 0)
        self.parse_galleries = as_bool(parse_galleries)
        self.gallery_categories = tuple(
            category
            for category in (
                as_int(part) for part in str(gallery_categories).split(",")
            )
            if category in self.gallery_category_names
        )
        self.catalog_path = Path(catalog_path)
        self.catalog_preloaded = as_bool(catalog_preloaded)
        if not 0 <= self.worker_index < self.worker_count:
            raise ValueError("worker_index должен находиться в диапазоне worker_count")
        self.processed_spec_ids: set[int] = set()
        self.pending_specs: dict[int, deque[int]] = {}
        self.spec_series: dict[int, int] = {}
        self.spec_years: dict[int, int | None] = {}
        self.config_request_counts: dict[int, int] = {}
        self.completed_config_spec_ids: set[int] = set()
        self.scheduled_config_spec_ids: set[int] = set()
        self.config_task_attempts: dict[int, int] = {}
        self.resume_specs_scheduled = 0
        self.completed_gallery_task_ids: set[int] = set()
        self.scheduled_gallery_task_ids: set[int] = set()
        self.gallery_task_attempts: dict[int, int] = {}
        self.pending_gallery_tasks: list[dict] = []

    async def start(self):
        """Запустить полный, точечный или возобновляемый обход."""
        if self.resume_configs:
            self.completed_config_spec_ids = self._load_completed_config_spec_ids()
            self._load_gallery_tasks()
            if self.parse_sales and self.worker_index == 0 and self.sales_months:
                for request in self._ranking_start_requests():
                    yield request
            # В режиме дозагрузки обязательно перечитываем каталог и списки
            # комплектаций. Это позволяет обнаружить серии и комплектации,
            # которых ещё не было в локальной БД на предыдущем запуске.
            response = self._download_tree(force_refresh=True)
            for output in self.parse_tree(response):
                yield output
            if self.parse_galleries:
                for request in self._resume_gallery_requests():
                    yield request
        elif self.only_series_id is not None:
            if not self._owns_series(self.only_series_id):
                self.logger.info(
                    "Серия %d назначена другому worker; текущий процесс завершён",
                    self.only_series_id,
                )
                return
            # Точечный запуск пропускает каталог, поэтому создаём родительскую
            # запись заранее. Последующий полный обход дополнит её данными.
            yield SeriesItem(
                id=self.only_series_id,
                brand_id=None,
                manufacturer_id=None,
                name=f"series-{self.only_series_id}",
                is_new_energy=None,
                spec_count=None,
                state=None,
                raw={"seriesid": self.only_series_id, "source": "spider_argument"},
            )
            yield self._spec_list_request(self.only_series_id)
            if self.parse_galleries:
                for category_id in self.gallery_categories:
                    for output in self._schedule_gallery_request(
                        self.only_series_id, category_id
                    ):
                        yield output
        else:
            if self.parse_sales and self.worker_index == 0 and self.sales_months:
                for request in self._ranking_start_requests():
                    yield request
            response = self._download_tree()
            for output in self.parse_tree(response):
                yield output

    def _ranking_start_requests(self):
        """Создать стартовые запросы всех поддерживаемых рейтингов."""
        common = {
            "headers": {"Referer": self.sales_rank_page},
            "meta": self._network_meta(),
            "dont_filter": True,
        }
        yield scrapy.Request(
            self.new_energy_rank_page,
            callback=self.parse_ranking_bootstrap,
            cb_kwargs={"kind": "monthly"},
            **common,
        )
        for kind, params in self.static_rankings:
            yield self._ranking_request(kind, dict(params), 1)

    def _load_completed_config_spec_ids(self) -> set[int]:
        """Найти комплектации с параметрами, силовой установкой и модификацией."""
        engine = create_engine(self.settings.get("DATABASE_URL"))
        has_parameters = (
            select(SpecParameter.spec_id)
            .where(SpecParameter.spec_id == Spec.id)
            .exists()
        )
        has_powertrain = (
            select(SpecPowertrain.spec_id)
            .where(SpecPowertrain.spec_id == Spec.id)
            .exists()
        )
        legacy_statement = (
            select(Spec.id)
            .where(
                has_parameters,
                has_powertrain,
                Spec.modification_id.is_not(None),
                Spec.series_id % self.worker_count == self.worker_index,
            )
        )
        task_statement = select(
            ConfigCrawlTask.spec_id,
            ConfigCrawlTask.status,
            ConfigCrawlTask.attempts,
        ).where(ConfigCrawlTask.series_id % self.worker_count == self.worker_index)
        completed: set[int] = set()
        try:
            with engine.connect() as connection:
                completed.update(connection.scalars(legacy_statement))
                for spec_id, status, attempts in connection.execute(task_statement):
                    self.config_task_attempts[spec_id] = attempts
                    if status in {"complete", "empty"}:
                        completed.add(spec_id)
        finally:
            engine.dispose()
        self.logger.info(
            "Режим дозагрузки нашёл %d полностью сохранённых конфигураций "
            "для текущего worker",
            len(completed),
        )
        return completed

    def _resume_gallery_requests(self):
        """Запланировать незавершённые страницы и новые корни галерей."""
        for task in self.pending_gallery_tasks:
            yield from self._schedule_gallery_request(
                task["series_id"],
                task["category_id"],
                task["page_url"],
                task["color_type"],
                task["color_id"],
                task_id=task["id"],
            )

        engine = create_engine(self.settings.get("DATABASE_URL"))
        statement = (
            select(Series.id)
            .where(Series.id % self.worker_count == self.worker_index)
            .order_by(Series.id)
        )
        series_ids: list[int] = []
        try:
            with engine.connect() as connection:
                for (series_id,) in connection.execute(statement):
                    if self.max_series and len(series_ids) >= self.max_series:
                        break
                    series_ids.append(series_id)
        finally:
            engine.dispose()

        self.logger.info(
            "Режим дозагрузки запланировал галереи %d серий",
            len(series_ids),
        )
        for series_id in series_ids:
            for category_id in self.gallery_categories:
                yield from self._schedule_gallery_request(series_id, category_id)

    def _load_gallery_tasks(self) -> None:
        """Загрузить завершённые и требующие повтора задачи галерей."""
        engine = create_engine(self.settings.get("DATABASE_URL"))
        statement = select(
            GalleryCrawlTask.id,
            GalleryCrawlTask.series_id,
            GalleryCrawlTask.category_id,
            GalleryCrawlTask.color_type,
            GalleryCrawlTask.color_id,
            GalleryCrawlTask.page_url,
            GalleryCrawlTask.status,
            GalleryCrawlTask.attempts,
        ).where(GalleryCrawlTask.series_id % self.worker_count == self.worker_index)
        try:
            with engine.connect() as connection:
                for row in connection.execute(statement).mappings():
                    task_id = row["id"]
                    self.gallery_task_attempts[task_id] = row["attempts"]
                    if row["status"] in {"complete", "empty"}:
                        self.completed_gallery_task_ids.add(task_id)
                    else:
                        self.pending_gallery_tasks.append(dict(row))
        finally:
            engine.dispose()
        self.logger.info(
            "Режим дозагрузки: завершённых страниц галерей %d, "
            "ожидают повтора %d",
            len(self.completed_gallery_task_ids),
            len(self.pending_gallery_tasks),
        )

    def _download_tree(self, force_refresh: bool = False):
        """Получить дерево каталога через curl либо прочитать его из кеша."""
        request = scrapy.Request(self.tree_url)
        cache_path = self.catalog_path
        if self.catalog_preloaded:
            if not cache_path.exists() or cache_path.stat().st_size <= 100_000:
                raise RuntimeError(
                    f"Мастер-процесс не подготовил каталог {cache_path}"
                )
            body = cache_path.read_bytes()
            self.logger.info("Используется каталог мастер-процесса из %s", cache_path)
            return TextResponse(
                url=self.tree_url,
                status=200,
                body=body,
                encoding="utf-8",
                request=request,
            )
        if (
            not force_refresh
            and cache_path.exists()
            and cache_path.stat().st_size > 100_000
        ):
            body = cache_path.read_bytes()
            self.logger.info("Using cached catalog from %s", cache_path)
        else:
            command = [
                "curl",
                "-fsS",
                "--compressed",
                "--connect-timeout",
                "15",
                "--max-time",
                "300",
                "--retry",
                "3",
                "--retry-all-errors",
                "-H",
                "Accept: application/json, text/plain, */*",
                "-H",
                "Referer: https://www.autohome.com.cn/price",
            ]
            if self.bind_address:
                command.extend(["--interface", self.bind_address])
            command.append(self.tree_url)
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=930,
            )
            body = completed.stdout
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(body)
            self.logger.info("Cached %d catalog bytes in %s", len(body), cache_path)
        return TextResponse(
            url=self.tree_url,
            status=200,
            body=body,
            encoding="utf-8",
            request=request,
        )

    def parse_tree(self, response):
        """Разобрать дерево брендов и серий и запланировать их комплектации."""
        payload = response.json()
        result = payload.get("result", payload)
        brand_ids: set[int] = set()
        series_ids: set[int] = set()
        scheduled_series = 0
        limit_reached = False

        # Текущая схема treeMenu иерархическая:
        # brand(id) -> fctitems[] -> seriesitems[](id). Для серии используется
        # общий ключ "id", а не "seriesid".
        for brand in walk_objects(result):
            factories = brand.get("fctitems")
            if not isinstance(factories, list):
                continue
            brand_id = as_int(first(brand, "brandid", "brandId", "id"))
            if brand_id is not None and brand_id not in brand_ids:
                brand_name = first(
                    brand, "brandname", "brandName", "name", default=f"brand-{brand_id}"
                )
                brand_ids.add(brand_id)
                yield BrandItem(
                    id=brand_id,
                    name=str(brand_name),
                    logo_url=first(brand, "logo", "logoUrl"),
                    series_count=as_int(brand.get("seriescount")),
                    raw=brand,
                )

            for factory_position, factory in enumerate(factories):
                if not isinstance(factory, dict):
                    continue
                manufacturer_id = as_int(factory.get("id"))
                if manufacturer_id is not None:
                    yield ManufacturerItem(
                        id=manufacturer_id,
                        name=str(factory.get("name") or manufacturer_id),
                        real_brand_id=as_int(factory.get("realbid")),
                        raw={
                            key: value
                            for key, value in factory.items()
                            if key != "seriesitems"
                        },
                    )
                    if brand_id is not None:
                        yield BrandManufacturerItem(
                            brand_id=brand_id,
                            manufacturer_id=manufacturer_id,
                            position=factory_position,
                        )
                series_items = factory.get("seriesitems") or []
                for series in series_items:
                    if not isinstance(series, dict):
                        continue
                    series_id = as_int(first(series, "seriesid", "seriesId", "id"))
                    if series_id is None or series_id in series_ids:
                        continue
                    series_ids.add(series_id)
                    series_name = first(
                        series,
                        "seriesname",
                        "seriesName",
                        "name",
                        default=f"series-{series_id}",
                    )
                    yield SeriesItem(
                        id=series_id,
                        brand_id=brand_id,
                        manufacturer_id=manufacturer_id,
                        name=str(series_name),
                        is_new_energy=(
                            bool(as_int(series.get("isnewenergy")))
                            if series.get("isnewenergy") is not None
                            else None
                        ),
                        spec_count=as_int(series.get("speccount")),
                        state=as_int(series.get("state")),
                        raw=series,
                    )

                    if self._owns_series(series_id) and self.parse_galleries:
                        for category_id in self.gallery_categories:
                            yield from self._schedule_gallery_request(
                                series_id, category_id
                            )

                    # Пустые серии сохраняем в БД, но не запрашиваем для них
                    # отсутствующие комплектации.
                    if as_int(series.get("speccount")) == 0:
                        continue
                    if not self._owns_series(series_id):
                        continue
                    yield self._spec_list_request(series_id)
                    scheduled_series += 1
                    if self.max_series and scheduled_series >= self.max_series:
                        limit_reached = True
                        break
                if limit_reached:
                    break
            if limit_reached:
                break

        self.logger.info(
            "Catalog produced %d unique series; scheduled %d spec-list requests",
            len(series_ids),
            scheduled_series,
        )

    def parse_ranking_bootstrap(self, response, kind: str):
        """Извлечь последний доступный месяц из серверных данных рейтинга."""
        raw = response.css("script#__NEXT_DATA__::text").get()
        if not raw:
            self.logger.error("На странице рейтинга %s нет __NEXT_DATA__", kind)
            return
        try:
            page_props = json.loads(raw)["props"]["pageProps"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            self.logger.error("Не удалось разобрать рейтинг %s: %s", kind, error)
            return
        latest = str((page_props.get("initialValues") or {}).get("date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}", latest):
            self.logger.error("Рейтинг %s не вернул доступный месяц", kind)
            return
        months = self._previous_months(latest, self.sales_months)
        self.logger.info(
            "Запланирован рейтинг %s за месяцы: %s",
            kind,
            ", ".join(months),
        )
        for month in months:
            yield self._ranking_request(
                "series_sales",
                {
                    "typeid": "1",
                    "subranktypeid": "1",
                    "date": month,
                    "levelid": "0",
                    "price": "0-9000",
                },
                1,
            )
            yield self._ranking_request(
                "brand_sales",
                {
                    "typeid": "1",
                    "subranktypeid": "3",
                    "entitytype": "1071",
                    "date": month,
                },
                1,
            )
            yield self._ranking_request(
                "new_energy",
                {
                    "typeid": "9",
                    "subranktypeid": "2305",
                    "date": month,
                    "levelid": "0",
                    "price": "0-9000",
                },
                1,
            )

    @staticmethod
    def _previous_months(latest: str, count: int) -> list[str]:
        """Построить последовательность месяцев назад от последнего доступного."""
        year, month = (int(part) for part in latest.split("-"))
        result = []
        for _ in range(count):
            result.append(f"{year:04d}-{month:02d}")
            month -= 1
            if month == 0:
                year -= 1
                month = 12
        return result

    def _ranking_request(self, kind: str, ranking_params: dict, page: int):
        """Создать запрос одной страницы выбранного рейтинга."""
        params = {
            "from": "28",
            "pm": "2",
            "pluginversion": "11.75.8",
            "model": "1",
            "channel": "0",
            "pageindex": str(page),
            "pagesize": "50",
            **ranking_params,
        }
        if kind in {"attention", "discount"}:
            params["cityid"] = self.city_id
        return scrapy.FormRequest(
            self.rank_url,
            method="GET",
            formdata=params,
            callback=self.parse_ranking,
            cb_kwargs={
                "kind": kind,
                "ranking_params": ranking_params,
                "page": page,
            },
            headers={"Referer": "https://www.autohome.com.cn/rank/1.html"},
            meta=self._network_meta(),
            priority=100,
            dont_filter=True,
        )

    def parse_ranking(self, response, kind: str, ranking_params: dict, page: int):
        """Сохранить одну страницу рейтинга и запросить следующую."""
        payload = response.json()
        result = payload.get("result") or {}
        rows = result.get("list") or []
        if page == 1:
            self.logger.info(
                "Рейтинг %s: получено %d строк на первой странице, страниц: %s",
                kind,
                len(rows),
                result.get("pagecount"),
            )
        if payload.get("message") != "SUCCESS":
            self.logger.warning(
                "API рейтинга %s вернул сообщение %r",
                kind,
                payload.get("message"),
            )
        for row in rows:
            item = self._ranking_item(kind, ranking_params, row)
            if item is not None:
                yield item

        if page < (as_int(result.get("pagecount")) or 0):
            yield self._ranking_request(kind, ranking_params, page + 1)

    def _ranking_item(self, kind: str, params: dict, row: dict):
        """Преобразовать строку API в элемент соответствующего рейтинга."""
        if kind == "brand_sales":
            # Универсальный API рейтингов в разных версиях ответа обозначает
            # бренд либо собственными полями, либо полями серии.
            entity_id = as_int(first(row, "brandid", "seriesid"))
        else:
            entity_id = as_int(row.get("seriesid"))
        rank = as_int(first(row, "rankNum", "rank")) or 0
        right = row.get("rightinfo") or {}
        primary_text = first(right, "righttextnewone", "righttextone")
        image_url = self._absolute_url(row.get("seriesimage"))
        entity_name = str(
            first(
                row,
                "brandname",
                "seriesname",
                default=entity_id or "",
            )
            if kind == "brand_sales"
            else first(row, "seriesname", default=entity_id or "")
        )
        month = params.get("date")

        if kind == "series_sales" and entity_id is not None and month:
            return SeriesMonthlySaleItem(
                month=date.fromisoformat(f"{month}-01"),
                series_id=entity_id,
                series_name=entity_name,
                brand_id=as_int(row.get("brandid")),
                rank=rank,
                sales_count=as_int(row.get("salecount")) or as_int(primary_text) or 0,
                rank_change=as_int(row.get("rankchange")),
                score=decimal_from_text(row.get("scorevalue")),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "brand_sales" and entity_id is not None and month:
            return BrandMonthlySaleItem(
                month=date.fromisoformat(f"{month}-01"),
                brand_id=entity_id,
                brand_name=entity_name,
                rank=rank,
                sales_count=as_int(row.get("salecount")) or as_int(primary_text) or 0,
                rank_change=as_int(row.get("rankchange")),
                image_url=image_url,
                raw=row,
            )
        if kind == "new_energy" and entity_id is not None and month:
            return NewEnergyRankingItem(
                month=date.fromisoformat(f"{month}-01"),
                subrank_type=as_int(params.get("subranktypeid")) or 0,
                series_id=entity_id,
                series_name=entity_name,
                brand_id=as_int(row.get("brandid")),
                rank=rank,
                sales_count=as_int(row.get("salecount")) or as_int(primary_text),
                rank_change=as_int(row.get("rankchange")),
                score=decimal_from_text(row.get("scorevalue")),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "smart_test" and entity_id is not None:
            overall = re.search(r"([A-D][+]?)", str(primary_text or ""))
            return SmartTestRankingItem(
                subrank_type=as_int(params.get("subranktypeid")) or 0,
                subrank_code=as_int(params.get("subrank")) or 0,
                series_id=entity_id,
                series_name=entity_name,
                overall_grade=overall.group(1) if overall else None,
                dimension_grades_json=row.get("rcmcenterlist") or [],
                tested_spec_name=text_after_colon(row.get("rcmdescone")),
                software_version=text_after_colon(row.get("rcmdesctwo")),
                system_description=text_after_colon(row.get("rcmdescthree")),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "attention" and entity_id is not None:
            return AttentionRankingItem(
                snapshot_date=date.today(),
                city_id=as_int(self.city_id) or 0,
                subrank_type=as_int(params.get("subranktypeid")) or 0,
                series_id=entity_id,
                series_name=entity_name,
                rank=rank,
                attention_index=as_int(primary_text),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "resale" and entity_id is not None:
            return ResaleValueRankingItem(
                snapshot_date=date.today(),
                series_id=entity_id,
                series_name=entity_name,
                rank=rank,
                resale_rate_percent=decimal_from_text(primary_text),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "discount" and entity_id is not None:
            spec_match = re.search(r"specid=(\d+)", str(row.get("rcmlinkurl") or ""))
            percent = decimal_from_text(right.get("righttexttwo"))
            return DiscountRankingItem(
                snapshot_date=date.today(),
                city_id=as_int(self.city_id) or 0,
                series_id=entity_id,
                series_name=entity_name,
                spec_id=int(spec_match.group(1)) if spec_match else None,
                spec_name=row.get("rcmdesc"),
                rank=rank,
                discount_yuan=yuan_from_text(primary_text),
                discount_percent=percent,
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        if kind == "technology":
            technology = row.get("technologyinfo") or {}
            technology_id = as_int(technology.get("technologyid"))
            if technology_id is None:
                return None
            return TechnologyRankingItem(
                snapshot_date=date.today(),
                technology_id=technology_id,
                rank=rank,
                name=str(technology.get("title") or technology_id),
                equipped_series_count=(
                    int(decimal_from_text(technology.get("subtitle")))
                    if decimal_from_text(technology.get("subtitle")) is not None
                    else None
                ),
                loudness_index=as_int(primary_text),
                raw=row,
            )
        if kind == "measured" and entity_id is not None:
            tested_spec_name = row.get("rcmdesc") or text_after_colon(
                row.get("rcmdescone")
            )
            metric_text = str(primary_text or "")
            unit_match = re.search(r"(%|km|kWh/100km|L/100km|s|m)$", metric_text)
            subrank_type = as_int(params.get("subranktypeid")) or 0
            subrank_code = as_int(params.get("subrank")) or 0
            return MeasuredTestRankingItem(
                id=stable_id(
                    "measured-ranking",
                    subrank_type,
                    subrank_code,
                    entity_id,
                    tested_spec_name,
                ),
                subrank_type=subrank_type,
                subrank_code=subrank_code,
                series_id=entity_id,
                series_name=entity_name,
                tested_spec_name=tested_spec_name,
                rank=rank,
                metric_name=right.get("righttexttwo"),
                metric_value=decimal_from_text(metric_text),
                metric_unit=unit_match.group(1) if unit_match else None,
                secondary_metric_text=right.get("righttextthree"),
                test_environment=text_after_colon(row.get("rcmdesctwo")),
                price_text=row.get("priceinfo"),
                image_url=image_url,
                raw=row,
            )
        return None

    def _gallery_request(
        self,
        series_id: int,
        category_id: int,
        url: str,
        color_type: str | None = None,
        color_id: int | None = None,
        task_id: int | None = None,
        attempts: int = 1,
    ):
        """Создать запрос страницы галереи с контекстом категории и цвета."""
        return scrapy.Request(
            url,
            callback=self.parse_gallery,
            errback=self.gallery_error,
            cb_kwargs={
                "series_id": series_id,
                "category_id": category_id,
                "color_type": color_type,
                "color_id": color_id,
                "task_id": task_id,
                "attempts": attempts,
            },
            headers={"Referer": f"https://www.autohome.com.cn/{series_id}/"},
            meta=self._network_meta(),
        )

    def _schedule_gallery_request(
        self,
        series_id: int,
        category_id: int,
        url: str | None = None,
        color_type: str | None = None,
        color_id: int | None = None,
        task_id: int | None = None,
    ):
        """Зарегистрировать ожидающую задачу и затем отправить её запрос."""
        page_url = (url or self.gallery_url.format(
            series_id=series_id,
            category_id=category_id,
        )).split("#", 1)[0]
        if task_id is None:
            task_id = stable_id(
                "gallery-page",
                series_id,
                category_id,
                color_type,
                color_id,
                page_url,
            )
        if task_id in self.completed_gallery_task_ids:
            return
        if task_id in self.scheduled_gallery_task_ids:
            return
        self.scheduled_gallery_task_ids.add(task_id)
        attempts = self.gallery_task_attempts.get(task_id, 0) + 1
        self.gallery_task_attempts[task_id] = attempts
        yield self._gallery_task_item(
            task_id,
            series_id,
            category_id,
            color_type,
            color_id,
            page_url,
            "pending",
            attempts,
        )
        yield self._gallery_request(
            series_id,
            category_id,
            page_url,
            color_type,
            color_id,
            task_id,
            attempts,
        )

    @staticmethod
    def _gallery_task_item(
        task_id: int,
        series_id: int,
        category_id: int,
        color_type: str | None,
        color_id: int | None,
        page_url: str,
        status: str,
        attempts: int,
        photo_count: int | None = None,
        last_error: str | None = None,
    ) -> GalleryCrawlTaskItem:
        """Создать строку состояния страницы фотогалереи."""
        return GalleryCrawlTaskItem(
            id=task_id,
            series_id=series_id,
            category_id=category_id,
            color_type=color_type,
            color_id=color_id,
            page_url=page_url,
            status=status,
            photo_count=photo_count,
            attempts=attempts,
            last_error=last_error,
        )

    def parse_gallery(
        self,
        response,
        series_id: int,
        category_id: int,
        color_type: str | None,
        color_id: int | None,
        task_id: int,
        attempts: int,
    ):
        """Сохранить фото, цвета и пагинацию одной галереи серии."""
        photo_count = 0
        for block in response.css(".search-pic"):
            label = "".join(block.css(".search-pic-left::text").getall()).strip()
            block_color_type = "interior" if "内饰" in label else "exterior"
            for link in block.css("a.color-cont[href]"):
                href = link.attrib.get("href", "")
                match = re.search(r"series-\d+-(i?)(\d+)-(\d+)-1\.html", href)
                if not match:
                    continue
                discovered_type = "interior" if match.group(1) else block_color_type
                discovered_id = as_int(match.group(2))
                discovered_category = as_int(match.group(3)) or category_id
                if discovered_id is None:
                    continue
                text = " ".join(link.xpath("string()").get().split())
                count_match = re.search(r"\((\d+)张\)", text)
                name = re.sub(r"\s*\(\d+张\)\s*$", "", text).strip()
                colors = re.findall(
                    r"background-color\s*:\s*(#[0-9A-Fa-f]{6})",
                    " ".join(link.css("em::attr(style)").getall()),
                )
                gallery_url = response.urljoin(href.split("#", 1)[0])
                yield SeriesGalleryColorItem(
                    series_id=series_id,
                    color_type=discovered_type,
                    color_id=discovered_id,
                    name=name,
                    color_values=colors,
                    picture_count=as_int(count_match.group(1)) if count_match else None,
                    gallery_url=gallery_url,
                    raw={"href": href, "label": label, "colors": colors},
                )
                yield from self._schedule_gallery_request(
                    series_id,
                    discovered_category,
                    gallery_url,
                    discovered_type,
                    discovered_id,
                )

        for node in response.css(".carpic-list03 li"):
            href = node.css("a[href*='/imgs-']::attr(href)").get()
            if not href:
                continue
            photo_match = re.search(r"/(\d+)\.html", href)
            spec_match = re.search(r"imgs-\d+-(\d+)-", href)
            photo_id = as_int(photo_match.group(1)) if photo_match else None
            if photo_id is None:
                continue
            photo_count += 1
            thumbnail = node.css("img::attr(data-webp)").get() or node.css(
                "img::attr(src)"
            ).get()
            thumbnail = self._absolute_url(thumbnail)
            image_url = re.sub(
                r"/\d+x\d+_\d+_q\d+_c\d+_", "/", thumbnail or ""
            )
            title = node.css("img::attr(title)").get() or node.css(
                "img::attr(alt)"
            ).get()
            page_url = response.urljoin(href.split("#", 1)[0])
            yield SeriesPhotoItem(
                id=photo_id,
                series_id=series_id,
                spec_id=as_int(spec_match.group(1)) if spec_match else None,
                category_id=category_id,
                category_name=self.gallery_category_names.get(
                    category_id, str(category_id)
                ),
                title=title,
                image_url=image_url,
                thumbnail_url=thumbnail,
                page_url=page_url,
                raw={"href": href, "thumbnail_url": thumbnail},
            )
            if color_type is not None and color_id is not None:
                yield SeriesPhotoColorItem(
                    photo_id=photo_id,
                    series_id=series_id,
                    color_type=color_type,
                    color_id=color_id,
                )

        next_href = response.css(".page a.page-item-next::attr(href)").get()
        if next_href and not next_href.startswith("javascript:"):
            yield from self._schedule_gallery_request(
                series_id,
                category_id,
                response.urljoin(next_href),
                color_type,
                color_id,
            )
        self.completed_gallery_task_ids.add(task_id)
        yield self._gallery_task_item(
            task_id,
            series_id,
            category_id,
            color_type,
            color_id,
            response.url.split("#", 1)[0],
            "complete" if photo_count else "empty",
            attempts,
            photo_count=photo_count,
        )

    def gallery_error(self, failure):
        """Сохранить неудачную страницу галереи для следующей дозагрузки."""
        context = failure.request.cb_kwargs
        self.logger.error(
            "Страница галереи %s не загружена: %s",
            failure.request.url,
            failure.getErrorMessage(),
        )
        yield self._gallery_task_item(
            context["task_id"],
            context["series_id"],
            context["category_id"],
            context["color_type"],
            context["color_id"],
            failure.request.url.split("#", 1)[0],
            "failed",
            context["attempts"],
            last_error=failure.getErrorMessage(),
        )

    @staticmethod
    def _absolute_url(url: str | None) -> str | None:
        """Добавить схему к протокол-независимому URL."""
        if not url:
            return None
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("http://"):
            return f"https://{url.removeprefix('http://')}"
        return url

    def _spec_list_request(self, series_id: int):
        """Создать запрос списка комплектаций выбранной серии."""
        return scrapy.Request(
            self.spec_list_url.format(series_id=series_id, city_id=self.city_id),
            callback=self.parse_spec_list,
            cb_kwargs={"series_id": series_id},
            headers={"Referer": f"https://www.autohome.com.cn/{series_id}/"},
            meta=self._network_meta(),
        )

    def parse_spec_list(self, response, series_id: int):
        """Сохранить комплектации серии и запустить загрузку их параметров."""
        payload = response.json()
        specs: dict[int, dict] = {}
        for obj in walk_objects(payload.get("result", payload)):
            spec_id = as_int(first(obj, "specid", "specId"))
            if spec_id is None:
                continue
            # Пропускаем обёртки, которые только ссылаются на комплектацию.
            if not any(k in obj for k in ("name", "specname", "specName", "price", "year")):
                continue
            current = specs.get(spec_id)
            if current is None or (
                not self._spec_has_price(current) and self._spec_has_price(obj)
            ):
                specs[spec_id] = obj

        skipped_spec_ids = {
            spec_id for spec_id, obj in specs.items() if not self._spec_has_price(obj)
        }
        if skipped_spec_ids:
            self.logger.info(
                "Серия %d: пропущено комплектаций без цены: %d",
                series_id,
                len(skipped_spec_ids),
            )
            specs = {
                spec_id: obj
                for spec_id, obj in specs.items()
                if spec_id not in skipped_spec_ids
            }

        for spec_id, obj in specs.items():
            self.spec_series[spec_id] = series_id
            self.spec_years[spec_id] = as_int(obj.get("year"))
            yield self._spec_item(obj, series_id)

        configurable = []
        for spec_id, obj in specs.items():
            if str(first(obj, "paramIsShow", "paramisshow", default="1")) == "0":
                continue
            if self.resume_configs and spec_id in self.completed_config_spec_ids:
                continue
            if spec_id in self.scheduled_config_spec_ids:
                continue
            if (
                self.resume_configs
                and self.max_resume_specs
                and self.resume_specs_scheduled >= self.max_resume_specs
            ):
                continue
            configurable.append(spec_id)
            if self.resume_configs:
                self.resume_specs_scheduled += 1
        self.pending_specs[series_id] = deque(configurable)
        yield from self._next_config_outputs(series_id)

    def _next_config_outputs(self, series_id: int):
        """Зарегистрировать и создать следующий запрос конфигурации серии."""
        pending = self.pending_specs.get(series_id)
        if (
            self.max_config_requests_per_series
            and self.config_request_counts.get(series_id, 0)
            >= self.max_config_requests_per_series
        ):
            self.pending_specs.pop(series_id, None)
            return
        while pending:
            spec_id = pending.popleft()
            if (
                spec_id in self.processed_spec_ids
                or spec_id in self.scheduled_config_spec_ids
            ):
                continue
            self.scheduled_config_spec_ids.add(spec_id)
            self.config_request_counts[series_id] = (
                self.config_request_counts.get(series_id, 0) + 1
            )
            attempts = self.config_task_attempts.get(spec_id, 0) + 1
            self.config_task_attempts[spec_id] = attempts
            yield self._config_task_item(
                spec_id,
                series_id,
                "pending",
                attempts,
            )
            yield scrapy.Request(
                self.config_url.format(spec_id=spec_id),
                callback=self.parse_config,
                errback=self.config_error,
                cb_kwargs={
                    "series_id": series_id,
                    "requested_spec_id": spec_id,
                    "attempts": attempts,
                },
                headers={
                    "Referer": f"https://www.autohome.com.cn/config/spec/{spec_id}.html"
                },
                meta=self._network_meta(),
            )
            return
        self.pending_specs.pop(series_id, None)

    @staticmethod
    def _config_task_item(
        spec_id: int,
        series_id: int,
        status: str,
        attempts: int,
        parameter_count: int | None = None,
        last_error: str | None = None,
    ) -> ConfigCrawlTaskItem:
        """Создать строку состояния полной конфигурации."""
        return ConfigCrawlTaskItem(
            spec_id=spec_id,
            series_id=series_id,
            status=status,
            parameter_count=parameter_count,
            attempts=attempts,
            last_error=last_error,
        )

    def parse_config(
        self,
        response,
        series_id: int,
        requested_spec_id: int,
        attempts: int,
    ):
        """Разобрать определения и значения параметров комплектаций."""
        payload = response.json()
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError(
                f"API конфигурации spec_id={requested_spec_id} не вернул result"
            )
        datalist = result.get("datalist")
        if not isinstance(datalist, list):
            raise ValueError(
                f"API конфигурации spec_id={requested_spec_id} не вернул datalist"
            )

        group_positions: dict[str, int] = {}
        section_positions: dict[str, int] = {}
        local_parameter_ids: dict[int, int] = {}
        local_powertrain_fields: dict[int, str] = {}
        local_vehicle_attribute_fields: dict[int, str] = {}
        for position, group in enumerate(result.get("titlelist") or []):
            group_name = str(group.get("groupname") or "")
            section_name = str(group.get("itemtype") or "")
            group_id = stable_id("parameter-group", group_name)
            section_id = stable_id("parameter-section", group_name, section_name)
            group_position = group_positions.setdefault(group_name, len(group_positions))
            section_position = section_positions.get(group_name, 0)
            section_positions[group_name] = section_position + 1
            yield ParameterGroupItem(
                id=group_id,
                name=group_name,
                position=group_position,
            )
            yield ParameterSectionItem(
                id=section_id,
                group_id=group_id,
                name=section_name,
                position=section_position,
            )
            for definition in group.get("items") or []:
                title_id = as_int(definition.get("titleid"))
                if title_id is None:
                    continue
                parameter_name = str(definition.get("itemname") or title_id)
                semantic_key = json.dumps(
                    [group_name, section_name, parameter_name],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                parameter_id = stable_id(
                    "parameter-definition",
                    group_name,
                    section_name,
                    parameter_name,
                )
                previous_id = local_parameter_ids.get(title_id)
                if previous_id is not None and previous_id != parameter_id:
                    self.logger.warning(
                        "В одном ответе title_id=%d соответствует нескольким "
                        "параметрам; используется последнее определение",
                        title_id,
                    )
                local_parameter_ids[title_id] = parameter_id
                powertrain_field = PATH_TO_FIELD.get(
                    (group_name, section_name, parameter_name)
                )
                if powertrain_field is not None:
                    local_powertrain_fields[title_id] = powertrain_field
                vehicle_attribute_field = VEHICLE_ATTRIBUTE_PATH_TO_FIELD.get(
                    (group_name, section_name, parameter_name)
                )
                if vehicle_attribute_field is not None:
                    local_vehicle_attribute_fields[title_id] = (
                        vehicle_attribute_field
                    )
                yield ParameterDefinitionItem(
                    id=parameter_id,
                    semantic_key=semantic_key,
                    item_id=as_int(definition.get("itemid")),
                    section_id=section_id,
                    name=parameter_name,
                    baike_id=as_int(definition.get("baikeid")),
                    baike_url=definition.get("baikeurl"),
                    raw=definition,
                )

        returned_ids: set[int] = set()
        returned_parameter_counts: dict[int, int] = {}
        for spec_data in datalist:
            spec_id = as_int(spec_data.get("specid"))
            if spec_id is None:
                continue
            returned_ids.add(spec_id)
            parameters = spec_data.get("paramconflist") or []
            returned_parameter_counts[spec_id] = len(parameters)
            returned_series_id = self.spec_series.get(spec_id, series_id)
            if spec_id not in self.spec_years:
                self.spec_years[spec_id] = as_int(spec_data.get("year"))
            # Эндпоинт списка содержит более полные данные о годе, цене дилера
            # и изображении. Здесь создаём запись только при её отсутствии.
            if spec_id not in self.spec_series and not self.resume_configs:
                if not self._spec_has_price(spec_data):
                    self.logger.info(
                        "Пропущена комплектация spec_id=%d без цены из ответа конфигурации",
                        spec_id,
                    )
                    continue
                yield self._spec_item(spec_data, returned_series_id)

            powertrain_values: dict[str, object] = {}
            vehicle_attribute_values: dict[str, object] = {}
            seen_vehicle_attribute_fields: set[str] = set()
            for parameter in parameters:
                title_id = as_int(parameter.get("titleid"))
                if title_id is None:
                    continue
                parameter_id = local_parameter_ids.get(title_id)
                if parameter_id is None:
                    self.logger.warning(
                        "Для spec_id=%d не найдено локальное определение title_id=%d",
                        spec_id,
                        title_id,
                    )
                    continue
                powertrain_field = local_powertrain_fields.get(title_id)
                vehicle_attribute_field = local_vehicle_attribute_fields.get(title_id)
                if vehicle_attribute_field is not None:
                    vehicle_attribute_values[vehicle_attribute_field] = parameter.get(
                        "itemname"
                    )
                    seen_vehicle_attribute_fields.add(vehicle_attribute_field)
                if powertrain_field not in SUBITEM_FIELDS:
                    if powertrain_field is not None:
                        raw_value = parameter.get("itemname")
                        powertrain_values[powertrain_field] = translate_powertrain_field(
                            powertrain_field,
                            raw_value,
                        )
                        if powertrain_field == "transmission_type":
                            powertrain_values["clutch_type"] = (
                                translate_powertrain_code("clutch_type", raw_value)
                            )
                yield SpecParameterItem(
                    spec_id=spec_id,
                    parameter_id=parameter_id,
                    value=parameter.get("itemname"),
                    option_price_yuan=parameter.get("priceinfo"),
                    video_url=parameter.get("videourl"),
                    raw=parameter,
                )
                for position, subitem in enumerate(parameter.get("sublist") or []):
                    if not isinstance(subitem, dict):
                        continue
                    yield ParameterSubitemItem(
                        spec_id=spec_id,
                        parameter_id=parameter_id,
                        position=position,
                        name=str(subitem.get("name") or ""),
                        value=subitem.get("value"),
                        option_price_yuan=subitem.get("priceinfo"),
                    )
                    if (
                        powertrain_field in SUBITEM_FIELDS
                        and str(subitem.get("value") or "").strip() == "●"
                    ):
                        raw_value = subitem.get("name")
                        powertrain_values[powertrain_field] = translate_powertrain_field(
                            powertrain_field,
                            raw_value,
                        )
                        if powertrain_field == "drive_type":
                            powertrain_values["engine_layout"] = (
                                translate_powertrain_code("engine_layout", raw_value)
                            )

                color_info = parameter.get("colorinfo")
                if isinstance(color_info, dict):
                    color_type = as_int(color_info.get("type"))
                    if color_type is not None:
                        yield ParameterColorSetItem(
                            spec_id=spec_id,
                            parameter_id=parameter_id,
                            type=color_type,
                        )
                        for position, color in enumerate(color_info.get("list") or []):
                            if not isinstance(color, dict):
                                continue
                            yield ParameterColorItem(
                                spec_id=spec_id,
                                parameter_id=parameter_id,
                                position=position,
                                name=str(color.get("name") or ""),
                                color_value=color.get("value"),
                                price_yuan=color.get("price"),
                                picture_count=as_int(color.get("picnum")),
                                gallery_url=color.get("linkurl"),
                            )

            powertrain = normalize_powertrain(
                spec_id,
                returned_series_id,
                self.spec_years.get(spec_id),
                powertrain_values,
            )
            modification = modification_row(powertrain)
            yield ModificationItem(**modification)
            yield SpecPowertrainItem(**powertrain)
            missing_attribute_sources = (
                REQUIRED_VEHICLE_ATTRIBUTE_SOURCE_FIELDS
                - seen_vehicle_attribute_fields
            )
            if missing_attribute_sources:
                self.logger.warning(
                    "Нормализация характеристик spec_id=%d пропущена: "
                    "частичный ответ без полей %s",
                    spec_id,
                    ", ".join(sorted(missing_attribute_sources)),
                )
            else:
                vehicle_attribute_values["drive_type"] = powertrain_values.get(
                    "drive_type"
                )
                vehicle_attributes = normalize_vehicle_attributes(
                    spec_id,
                    returned_series_id,
                    vehicle_attribute_values,
                )
                yield SpecVehicleAttributesItem(**vehicle_attributes)
            yield SpecModificationItem(
                spec_id=spec_id,
                modification_id=modification["id"],
            )

        parameter_count = returned_parameter_counts.get(requested_spec_id, 0)
        status = "complete" if parameter_count else "empty"
        self.completed_config_spec_ids.add(requested_spec_id)
        yield self._config_task_item(
            requested_spec_id,
            series_id,
            status,
            attempts,
            parameter_count=parameter_count,
        )
        # Пустой успешный ответ считается завершённым и больше не создаёт
        # бесконечную очередь повторов при каждом запуске дозагрузки.
        returned_ids.add(requested_spec_id)
        self.processed_spec_ids.update(returned_ids)
        yield from self._next_config_outputs(series_id)

    def config_error(self, failure):
        """Записать ошибку конфигурации и продолжить обработку серии."""
        request = failure.request
        series_id = request.cb_kwargs["series_id"]
        requested_spec_id = request.cb_kwargs["requested_spec_id"]
        attempts = request.cb_kwargs["attempts"]
        self.logger.error(
            "Configuration request failed for spec %d: %s",
            requested_spec_id,
            failure.getErrorMessage(),
        )
        yield self._config_task_item(
            requested_spec_id,
            series_id,
            "failed",
            attempts,
            last_error=failure.getErrorMessage(),
        )
        # Продолжаем серию после исчерпания стандартных повторов Scrapy.
        self.processed_spec_ids.add(requested_spec_id)
        yield from self._next_config_outputs(series_id)

    @staticmethod
    def _spec_has_price(obj: dict) -> bool:
        """Проверить цены комплектации во входном объекте API."""
        return has_vehicle_price(
            first(obj, "minprice", "price"),
            first(obj, "dealerprice", "dealerPrice"),
        )

    @staticmethod
    def _spec_item(obj: dict, series_id: int):
        """Преобразовать объект API в элемент комплектации."""
        spec_id = as_int(first(obj, "specid", "specId"))
        return SpecItem(
            id=spec_id,
            series_id=series_id,
            name=str(first(obj, "specname", "specName", "name", default=f"spec-{spec_id}")),
            year=as_int(obj.get("year")),
            state=as_int(first(obj, "specstatus", "state")),
            guide_price_yuan=first(obj, "minprice", "price"),
            dealer_price_yuan=first(obj, "dealerprice", "dealerPrice"),
            discount_yuan=first(obj, "downPrice", "downprice"),
            description=obj.get("description"),
            image_url=first(obj, "imgUrl", "imgurl"),
            config_available=(
                str(first(obj, "paramIsShow", "paramisshow")) != "0"
                if first(obj, "paramIsShow", "paramisshow") is not None
                else None
            ),
            raw=obj,
        )

    def _owns_series(self, series_id: int) -> bool:
        """Проверить, назначена ли серия текущему worker-процессу."""
        return series_id % self.worker_count == self.worker_index

    def _network_meta(self) -> dict:
        """Вернуть параметры Scrapy для привязки запроса к локальному IP."""
        return {"bindaddress": self.bind_address} if self.bind_address else {}
