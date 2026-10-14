from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from autohome.items import (
    BrandItem,
    ParameterDefinitionItem,
    SeriesItem,
    SpecItem,
    SpecParameterItem,
)
from autohome.models import Base, Brand, ParameterDefinition, Series, Spec, SpecParameter
from autohome.translator import (
    translate_exact,
    translate_parameter_name,
    translate_structure,
    translate_vehicle_name,
)


def json_text(value) -> str:
    """Сериализовать значение в компактную JSON-строку без ASCII-экранирования."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class SqlAlchemyPipeline:
    """Пакетно сохранять элементы Scrapy в базу через SQLAlchemy."""
    model_by_item = {
        BrandItem: Brand,
        SeriesItem: Series,
        SpecItem: Spec,
        ParameterDefinitionItem: ParameterDefinition,
        SpecParameterItem: SpecParameter,
    }

    def __init__(self, database_url: str, batch_size: int):
        """Инициализировать pipeline адресом базы и размером пакета."""
        self.database_url = database_url
        self.batch_size = batch_size
        self.buffers = defaultdict(list)
        self.buffered = 0

    @classmethod
    def from_crawler(cls, crawler):
        """Создать pipeline на основе настроек текущего crawler."""
        return cls(
            crawler.settings.get("DATABASE_URL"),
            crawler.settings.getint("DATABASE_BATCH_SIZE", 1000),
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
        """Сохранить накопленные элементы одной транзакцией."""
        if not self.buffered:
            return
        with Session(self.engine) as session, session.begin():
            # Родительские таблицы должны записываться раньше зависимых.
            for item_type in self.model_by_item:
                rows = self.buffers.get(item_type)
                if not rows:
                    continue
                model = self.model_by_item[item_type]
                rows = self._deduplicate_rows(model, rows)
                statement = self._insert(model).values(rows)
                primary_keys = {column.name for column in model.__table__.primary_key}
                update_columns = {
                    column.name: getattr(statement.excluded, column.name)
                    for column in model.__table__.columns
                    if column.name not in primary_keys
                }
                if model is SpecParameter:
                    statement = statement.on_conflict_do_update(
                        index_elements=["spec_id", "title_id"], set_=update_columns
                    )
                else:
                    statement = statement.on_conflict_do_update(
                        index_elements=list(primary_keys), set_=update_columns
                    )
                session.execute(statement)
        self.buffers.clear()
        self.buffered = 0

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
        """Оставить последнюю строку для каждого конфликтного ключа пакета."""
        if model is SpecParameter:
            key_columns = ("spec_id", "title_id")
        else:
            key_columns = tuple(column.name for column in model.__table__.primary_key)
        unique_rows = {
            tuple(row[column] for column in key_columns): row for row in rows
        }
        return list(unique_rows.values())

    @staticmethod
    def _serialize(item):
        """Преобразовать элемент Scrapy в строку для соответствующей таблицы."""
        data = dict(item)
        raw = data.pop("raw", data)
        data["raw_json"] = json_text(raw)
        if isinstance(item, (BrandItem, SeriesItem, SpecItem)):
            data["name"] = translate_vehicle_name(data.get("name"))
        if isinstance(item, SpecItem):
            for field in ("guide_price", "dealer_price", "discount", "description"):
                data[field] = translate_exact(data.get(field))
        if isinstance(item, ParameterDefinitionItem):
            data["name"] = translate_parameter_name(data.get("name"))
            data["group_name"] = translate_exact(data.get("group_name"))
            data["section_name"] = translate_exact(data.get("section_name"))
        if isinstance(item, SpecParameterItem):
            data["value"] = translate_exact(data.get("value"))
            data["option_price"] = translate_exact(data.get("option_price"))
            subitems = data.pop("subitems", None)
            color_info = data.pop("color_info", None)
            data["subitems_json"] = (
                json_text(translate_structure(subitems))
                if subitems is not None
                else None
            )
            data["color_info_json"] = (
                json_text(translate_structure(color_info))
                if color_info is not None
                else None
            )
        return data
