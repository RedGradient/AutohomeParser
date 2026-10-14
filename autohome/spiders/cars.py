from __future__ import annotations

from collections import deque
import subprocess
from pathlib import Path
from typing import Any, Iterable

import scrapy
from scrapy.http import TextResponse
from sqlalchemy import create_engine, select

from autohome.items import (
    BrandItem,
    ParameterDefinitionItem,
    SeriesItem,
    SpecItem,
    SpecParameterItem,
)
from autohome.models import Spec, SpecParameter


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
    """Собирать каталог, комплектации и технические параметры Autohome."""
    name = "cars"
    allowed_domains = [
        "www.autohome.com.cn",
        "car.app.autohome.com.cn",
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
        if not 0 <= self.worker_index < self.worker_count:
            raise ValueError("worker_index должен находиться в диапазоне worker_count")
        self.processed_spec_ids: set[int] = set()
        self.pending_specs: dict[int, deque[int]] = {}
        self.spec_series: dict[int, int] = {}
        self.config_request_counts: dict[int, int] = {}

    async def start(self):
        """Запустить полный, точечный или возобновляемый обход."""
        if self.resume_configs:
            for request in self._resume_config_requests():
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
                name=f"series-{self.only_series_id}",
                raw={"seriesid": self.only_series_id, "source": "spider_argument"},
            )
            yield self._spec_list_request(self.only_series_id)
        else:
            response = self._download_tree()
            for output in self.parse_tree(response):
                yield output

    def _resume_config_requests(self):
        """Создать запросы параметров для незавершённых комплектаций из БД."""
        engine = create_engine(self.settings.get("DATABASE_URL"))
        has_parameters = (
            select(SpecParameter.id)
            .where(SpecParameter.spec_id == Spec.id)
            .exists()
        )
        statement = (
            select(Spec.id, Spec.series_id)
            .where(
                Spec.config_available.is_not(False),
                ~has_parameters,
                Spec.series_id % self.worker_count == self.worker_index,
            )
            .order_by(Spec.series_id, Spec.id)
        )

        queued = 0
        try:
            with engine.connect() as connection:
                for spec_id, series_id in connection.execute(statement):
                    if series_id is None:
                        continue
                    if self.max_resume_specs and queued >= self.max_resume_specs:
                        break
                    self.spec_series[spec_id] = series_id
                    self.pending_specs.setdefault(series_id, deque()).append(spec_id)
                    queued += 1
        finally:
            engine.dispose()

        self.logger.info(
            "Resume mode found %d specs without saved configuration parameters "
            "in %d series",
            queued,
            len(self.pending_specs),
        )
        for series_id in list(self.pending_specs):
            request = self._next_config_request(series_id)
            if request:
                yield request

    def _download_tree(self):
        """Получить дерево каталога через curl либо прочитать его из кеша."""
        request = scrapy.Request(self.tree_url)
        cache_path = Path("data/tree_menu.json")
        if cache_path.exists() and cache_path.stat().st_size > 100_000:
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
                    first_letter=first(brand, "firstletter", "firstLetter"),
                    country=brand.get("country"),
                    logo=first(brand, "logo", "logoUrl"),
                    raw=brand,
                )

            for factory in factories:
                if not isinstance(factory, dict):
                    continue
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
                        name=str(series_name),
                        raw={**series, "factory": factory.get("name")},
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
            specs.setdefault(spec_id, obj)

        for spec_id, obj in specs.items():
            self.spec_series[spec_id] = series_id
            yield self._spec_item(obj, series_id)

        configurable = [
            spec_id
            for spec_id, obj in specs.items()
            if str(first(obj, "paramIsShow", "paramisshow", default="1")) != "0"
        ]
        self.pending_specs[series_id] = deque(configurable)
        request = self._next_config_request(series_id)
        if request:
            yield request

    def _next_config_request(self, series_id: int):
        """Создать следующий запрос полной конфигурации для серии."""
        pending = self.pending_specs.get(series_id)
        if (
            self.max_config_requests_per_series
            and self.config_request_counts.get(series_id, 0)
            >= self.max_config_requests_per_series
        ):
            self.pending_specs.pop(series_id, None)
            return None
        while pending:
            spec_id = pending.popleft()
            if spec_id in self.processed_spec_ids:
                continue
            self.config_request_counts[series_id] = (
                self.config_request_counts.get(series_id, 0) + 1
            )
            return scrapy.Request(
                self.config_url.format(spec_id=spec_id),
                callback=self.parse_config,
                errback=self.config_error,
                cb_kwargs={"series_id": series_id, "requested_spec_id": spec_id},
                headers={
                    "Referer": f"https://www.autohome.com.cn/config/spec/{spec_id}.html"
                },
                meta=self._network_meta(),
            )
        self.pending_specs.pop(series_id, None)
        return None

    def parse_config(self, response, series_id: int, requested_spec_id: int):
        """Разобрать определения и значения параметров комплектаций."""
        payload = response.json()
        result = payload.get("result") or {}

        for group in result.get("titlelist") or []:
            for definition in group.get("items") or []:
                title_id = as_int(definition.get("titleid"))
                if title_id is None:
                    continue
                yield ParameterDefinitionItem(
                    title_id=title_id,
                    group_name=group.get("groupname"),
                    section_name=group.get("itemtype"),
                    name=str(definition.get("itemname") or title_id),
                    item_id=as_int(definition.get("itemid")),
                    raw=definition,
                )

        returned_ids: set[int] = set()
        for spec_data in result.get("datalist") or []:
            spec_id = as_int(spec_data.get("specid"))
            if spec_id is None:
                continue
            returned_ids.add(spec_id)
            returned_series_id = self.spec_series.get(spec_id, series_id)
            # Эндпоинт списка содержит более полные данные о годе, цене дилера
            # и изображении. Здесь создаём запись только при её отсутствии.
            if spec_id not in self.spec_series and not self.resume_configs:
                yield self._spec_item(spec_data, returned_series_id)

            for parameter in spec_data.get("paramconflist") or []:
                title_id = as_int(parameter.get("titleid"))
                if title_id is None:
                    continue
                yield SpecParameterItem(
                    spec_id=spec_id,
                    title_id=title_id,
                    value=parameter.get("itemname"),
                    option_price=parameter.get("priceinfo"),
                    subitems=parameter.get("sublist"),
                    color_info=parameter.get("colorinfo"),
                    raw=parameter,
                )

        # Считаем запрошенный ID обработанным даже при пустом ответе, иначе
        # некорректная серия может создать бесконечный цикл.
        returned_ids.add(requested_spec_id)
        self.processed_spec_ids.update(returned_ids)
        request = self._next_config_request(series_id)
        if request:
            yield request

    def config_error(self, failure):
        """Записать ошибку конфигурации и продолжить обработку серии."""
        request = failure.request
        series_id = request.cb_kwargs["series_id"]
        requested_spec_id = request.cb_kwargs["requested_spec_id"]
        self.logger.error(
            "Configuration request failed for spec %d: %s",
            requested_spec_id,
            failure.getErrorMessage(),
        )
        # Продолжаем серию после исчерпания стандартных повторов Scrapy.
        self.processed_spec_ids.add(requested_spec_id)
        next_request = self._next_config_request(series_id)
        if next_request:
            yield next_request

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
            guide_price=first(obj, "minprice", "price"),
            dealer_price=first(obj, "dealerprice", "dealerPrice"),
            discount=first(obj, "downPrice", "downprice"),
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
