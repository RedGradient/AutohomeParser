from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
PRICE_TYPE = Numeric(16, 2)


class Base(DeclarativeBase):
    """Базовый класс моделей SQLAlchemy."""


class Brand(Base):
    """Марка автомобиля из дерева каталога."""

    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text)
    series_count: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Manufacturer(Base):
    """Производитель или завод, выпускающий серии автомобилей."""

    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    real_brand_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class BrandManufacturer(Base):
    """Связь марки с отображаемым внутри неё производителем."""

    __tablename__ = "brand_manufacturers"

    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(
        ForeignKey("manufacturers.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Series(Base):
    """Серия автомобилей внутри марки и производителя."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), index=True)
    manufacturer_id: Mapped[int | None] = mapped_column(
        ForeignKey("manufacturers.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_new_energy: Mapped[bool | None] = mapped_column(Boolean, index=True)
    spec_count: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Spec(Base):
    """Конкретная комплектация серии автомобиля."""

    __tablename__ = "specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    state: Mapped[int | None] = mapped_column(Integer, index=True)
    guide_price_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    dealer_price_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    discount_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    config_available: Mapped[bool | None] = mapped_column(Boolean, index=True)
    modification_id: Mapped[int | None] = mapped_column(
        ForeignKey("modifications.id"), index=True
    )
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ParameterGroup(Base):
    """Верхнеуровневая группа технических характеристик."""

    __tablename__ = "parameter_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ParameterSection(Base):
    """Раздел характеристик внутри группы."""

    __tablename__ = "parameter_sections"
    __table_args__ = (UniqueConstraint("group_id", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("parameter_groups.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ParameterDefinition(Base):
    """Справочное определение одного параметра Autohome."""

    __tablename__ = "parameter_definitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    semantic_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("parameter_sections.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    baike_id: Mapped[int | None] = mapped_column(Integer)
    baike_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class SpecParameter(Base):
    """Значение параметра для конкретной комплектации."""

    __tablename__ = "spec_parameters"
    __table_args__ = (
        PrimaryKeyConstraint("spec_id", "parameter_id"),
    )

    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), index=True)
    parameter_id: Mapped[int] = mapped_column(
        ForeignKey("parameter_definitions.id"), index=True
    )
    value: Mapped[str | None] = mapped_column(Text)
    option_price_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    video_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class ParameterSubitem(Base):
    """Вложенная характеристика с признаком штатного оснащения."""

    __tablename__ = "parameter_subitems"
    __table_args__ = (
        PrimaryKeyConstraint("spec_id", "parameter_id", "position"),
        ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["spec_parameters.spec_id", "spec_parameters.parameter_id"],
        ),
    )

    spec_id: Mapped[int] = mapped_column(Integer, index=True)
    parameter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[bool | None] = mapped_column(Boolean)
    option_price_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)


class ParameterColorSet(Base):
    """Набор цветов кузова или салона для параметра комплектации."""

    __tablename__ = "parameter_color_sets"
    __table_args__ = (
        PrimaryKeyConstraint("spec_id", "parameter_id"),
        ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["spec_parameters.spec_id", "spec_parameters.parameter_id"],
        ),
    )

    spec_id: Mapped[int] = mapped_column(Integer, index=True)
    parameter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    type: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class ParameterColor(Base):
    """Один доступный цвет кузова или салона."""

    __tablename__ = "parameter_colors"
    __table_args__ = (
        PrimaryKeyConstraint("spec_id", "parameter_id", "position"),
        ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["parameter_color_sets.spec_id", "parameter_color_sets.parameter_id"],
        ),
    )

    spec_id: Mapped[int] = mapped_column(Integer, index=True)
    parameter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    color_value: Mapped[str | None] = mapped_column(String(200))
    price_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    picture_count: Mapped[int | None] = mapped_column(Integer)
    gallery_url: Mapped[str | None] = mapped_column(Text)


class SpecPowertrain(Base):
    """Нормализованные признаки силовой установки комплектации."""

    __tablename__ = "spec_powertrains"

    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    model_year: Mapped[int | None] = mapped_column(Integer, index=True)
    energy_type: Mapped[str | None] = mapped_column(String(200), index=True)
    engine_summary: Mapped[str | None] = mapped_column(String(300))
    engine_displacement_ml: Mapped[int | None] = mapped_column(Integer)
    engine_model: Mapped[str | None] = mapped_column(String(300), index=True)
    engine_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    maximum_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    transmission_summary: Mapped[str | None] = mapped_column(String(300))
    transmission_type: Mapped[str | None] = mapped_column(String(300), index=True)
    transmission_gears: Mapped[int | None] = mapped_column(Integer)
    drive_type: Mapped[str | None] = mapped_column(String(300), index=True)
    motor_total_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_count: Mapped[int | None] = mapped_column(Integer)
    motor_layout: Mapped[str | None] = mapped_column(String(200))
    system_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_type: Mapped[str | None] = mapped_column(String(300))
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    missing_fields_json: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Modification(Base):
    """Одна нормализованная модификация внутри серии и модельного года."""

    __tablename__ = "modifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    modification_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    model_year: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    energy_type: Mapped[str | None] = mapped_column(String(200), index=True)
    engine_summary: Mapped[str | None] = mapped_column(String(300))
    engine_displacement_ml: Mapped[int | None] = mapped_column(Integer)
    engine_model: Mapped[str | None] = mapped_column(String(300), index=True)
    engine_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    maximum_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    transmission_summary: Mapped[str | None] = mapped_column(String(300))
    transmission_type: Mapped[str | None] = mapped_column(String(300), index=True)
    transmission_gears: Mapped[int | None] = mapped_column(Integer)
    drive_type: Mapped[str | None] = mapped_column(String(300), index=True)
    motor_total_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_count: Mapped[int | None] = mapped_column(Integer)
    motor_layout: Mapped[str | None] = mapped_column(String(200))
    system_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_type: Mapped[str | None] = mapped_column(String(300))
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    spec_count: Mapped[int] = mapped_column(Integer, nullable=False)
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SeriesMonthlySale(Base):
    """Месячная позиция серии в рейтинге продаж."""

    __tablename__ = "series_monthly_sales"
    __table_args__ = (PrimaryKeyConstraint("month", "series_id"),)

    month: Mapped[date] = mapped_column(Date)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand_id: Mapped[int | None] = mapped_column(Integer, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrandMonthlySale(Base):
    """Месячная позиция марки в рейтинге продаж."""

    __tablename__ = "brand_monthly_sales"
    __table_args__ = (PrimaryKeyConstraint("month", "brand_id"),)

    month: Mapped[date] = mapped_column(Date)
    brand_id: Mapped[int] = mapped_column(Integer, index=True)
    brand_name: Mapped[str] = mapped_column(String(300), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewEnergyRanking(Base):
    """Месячная позиция серии в рейтинге автомобилей новой энергии."""

    __tablename__ = "new_energy_rankings"
    __table_args__ = (
        PrimaryKeyConstraint("month", "subrank_type", "series_id"),
    )

    month: Mapped[date] = mapped_column(Date)
    subrank_type: Mapped[int] = mapped_column(Integer)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand_id: Mapped[int | None] = mapped_column(Integer, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    sales_count: Mapped[int | None] = mapped_column(Integer)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SmartTestRanking(Base):
    """Результат испытаний интеллектуальных систем 千里智测."""

    __tablename__ = "smart_test_rankings"
    __table_args__ = (
        PrimaryKeyConstraint("subrank_type", "subrank_code", "series_id"),
    )

    subrank_type: Mapped[int] = mapped_column(Integer)
    subrank_code: Mapped[int] = mapped_column(Integer)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    overall_grade: Mapped[str | None] = mapped_column(String(20))
    dimension_grades_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, nullable=False
    )
    tested_spec_name: Mapped[str | None] = mapped_column(String(1000))
    software_version: Mapped[str | None] = mapped_column(String(300))
    system_description: Mapped[str | None] = mapped_column(Text)
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AttentionRanking(Base):
    """Снимок рейтинга пользовательского внимания к сериям."""

    __tablename__ = "attention_rankings"
    __table_args__ = (
        PrimaryKeyConstraint("snapshot_date", "city_id", "subrank_type", "series_id"),
    )

    snapshot_date: Mapped[date] = mapped_column(Date)
    city_id: Mapped[int] = mapped_column(Integer)
    subrank_type: Mapped[int] = mapped_column(Integer)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    attention_index: Mapped[int | None] = mapped_column(Integer)
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResaleValueRanking(Base):
    """Снимок рейтинга трёхлетней остаточной стоимости серий."""

    __tablename__ = "resale_value_rankings"
    __table_args__ = (PrimaryKeyConstraint("snapshot_date", "series_id"),)

    snapshot_date: Mapped[date] = mapped_column(Date)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    resale_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DiscountRanking(Base):
    """Снимок максимальных дилерских скидок по сериям и комплектациям."""

    __tablename__ = "discount_rankings"
    __table_args__ = (
        PrimaryKeyConstraint("snapshot_date", "city_id", "series_id"),
    )

    snapshot_date: Mapped[date] = mapped_column(Date)
    city_id: Mapped[int] = mapped_column(Integer)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    spec_id: Mapped[int | None] = mapped_column(Integer, index=True)
    spec_name: Mapped[str | None] = mapped_column(String(1000))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_yuan: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TechnologyRanking(Base):
    """Снимок популярности автомобильной интеллектуальной технологии."""

    __tablename__ = "technology_rankings"
    __table_args__ = (PrimaryKeyConstraint("snapshot_date", "technology_id"),)

    snapshot_date: Mapped[date] = mapped_column(Date)
    technology_id: Mapped[int] = mapped_column(BigInteger)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    equipped_series_count: Mapped[int | None] = mapped_column(Integer)
    loudness_index: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MeasuredTestRanking(Base):
    """Инструментальный замер конкретной протестированной комплектации."""

    __tablename__ = "measured_test_rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subrank_type: Mapped[int] = mapped_column(Integer, index=True)
    subrank_code: Mapped[int] = mapped_column(Integer, index=True)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    tested_spec_name: Mapped[str | None] = mapped_column(String(1000))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(300))
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    metric_unit: Mapped[str | None] = mapped_column(String(50))
    secondary_metric_text: Mapped[str | None] = mapped_column(String(300))
    test_environment: Mapped[str | None] = mapped_column(String(500))
    price_text: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SeriesGalleryColor(Base):
    """Цвет кузова или салона в фотогалерее серии."""

    __tablename__ = "series_gallery_colors"
    __table_args__ = (PrimaryKeyConstraint("series_id", "color_type", "color_id"),)

    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    color_type: Mapped[str] = mapped_column(String(20))
    color_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    color_values: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    picture_count: Mapped[int | None] = mapped_column(Integer)
    gallery_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class SeriesPhoto(Base):
    """Фотография серии с прямой ссылкой на изображение."""

    __tablename__ = "series_photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    spec_id: Mapped[int | None] = mapped_column(Integer, index=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SeriesPhotoColor(Base):
    """Связь фотографии с цветом кузова или салона."""

    __tablename__ = "series_photo_colors"
    __table_args__ = (
        PrimaryKeyConstraint("photo_id", "series_id", "color_type", "color_id"),
        ForeignKeyConstraint(
            ["series_id", "color_type", "color_id"],
            [
                "series_gallery_colors.series_id",
                "series_gallery_colors.color_type",
                "series_gallery_colors.color_id",
            ],
        ),
    )

    photo_id: Mapped[int] = mapped_column(ForeignKey("series_photos.id"), index=True)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    color_type: Mapped[str] = mapped_column(String(20))
    color_id: Mapped[int] = mapped_column(Integer)
