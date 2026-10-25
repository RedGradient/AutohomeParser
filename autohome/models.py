from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
    __table_args__ = (
        Index("ix_series_brand_name_id", "brand_id", "name", "id"),
        Index("ix_series_manufacturer_name_id", "manufacturer_id", "name", "id"),
    )

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
    __table_args__ = (
        Index("ix_specs_series_year_id", "series_id", "year", "id"),
        Index("ix_specs_modification_id_id", "modification_id", "id"),
    )

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
    __table_args__ = (PrimaryKeyConstraint("spec_id", "parameter_id"),)

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
    __table_args__ = (
        Index("ix_spec_powertrains_engine_displacement_ml", "engine_displacement_ml"),
        Index("ix_spec_powertrains_engine_power_hp", "engine_power_hp"),
    )

    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    model_year: Mapped[int | None] = mapped_column(Integer, index=True)
    energy_type: Mapped[str | None] = mapped_column(String(200), index=True)
    engine_summary: Mapped[str | None] = mapped_column(String(300))
    engine_displacement_ml: Mapped[int | None] = mapped_column(Integer)
    engine_model: Mapped[str | None] = mapped_column(String(300), index=True)
    engine_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    engine_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    maximum_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    transmission_summary: Mapped[str | None] = mapped_column(String(300))
    transmission_type: Mapped[str | None] = mapped_column(String(300), index=True)
    clutch_type: Mapped[str | None] = mapped_column(String(30), index=True)
    transmission_gears: Mapped[int | None] = mapped_column(Integer)
    drive_type: Mapped[str | None] = mapped_column(String(300), index=True)
    engine_layout: Mapped[str | None] = mapped_column(String(30), index=True)
    aspiration_type: Mapped[str | None] = mapped_column(String(50), index=True)
    cylinder_layout: Mapped[str | None] = mapped_column(String(30), index=True)
    body_type: Mapped[str | None] = mapped_column(String(50), index=True)
    motor_total_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_total_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_count: Mapped[int | None] = mapped_column(Integer)
    motor_layout: Mapped[str | None] = mapped_column(String(200))
    system_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    system_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    recycling_fee_powertrain_type: Mapped[str | None] = mapped_column(
        String(30), index=True
    )
    recycling_fee_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    recycling_fee_power_source: Mapped[str | None] = mapped_column(String(60))
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_type: Mapped[str | None] = mapped_column(String(300))
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    missing_fields_json: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SpecVehicleAttributes(Base):
    """Нормализованные кузовные и классификационные признаки комплектации."""

    __tablename__ = "spec_vehicle_attributes"
    __table_args__ = (
        Index("ix_spec_vehicle_attributes_seat_count_max", "seat_count_max"),
    )

    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    vehicle_class: Mapped[str | None] = mapped_column(String(100), index=True)
    vehicle_technical_category: Mapped[str | None] = mapped_column(
        String(10), index=True
    )
    body_type: Mapped[str | None] = mapped_column(String(50), index=True)
    body_construction: Mapped[str | None] = mapped_column(String(50), index=True)
    seat_count_min: Mapped[int | None] = mapped_column(Integer)
    seat_count_max: Mapped[int | None] = mapped_column(Integer)
    door_count: Mapped[int | None] = mapped_column(Integer)
    curb_mass_kg: Mapped[int | None] = mapped_column(Integer)
    curb_mass_kg_min: Mapped[int | None] = mapped_column(Integer)
    curb_mass_kg_max: Mapped[int | None] = mapped_column(Integer)
    gross_mass_kg: Mapped[int | None] = mapped_column(Integer, index=True)
    payload_kg_min: Mapped[int | None] = mapped_column(Integer)
    payload_kg_max: Mapped[int | None] = mapped_column(Integer)
    length_mm: Mapped[int | None] = mapped_column(Integer)
    width_mm: Mapped[int | None] = mapped_column(Integer)
    height_mm: Mapped[int | None] = mapped_column(Integer)
    wheelbase_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_length_min_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_length_max_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_width_min_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_width_max_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_height_min_mm: Mapped[int | None] = mapped_column(Integer)
    cargo_height_max_mm: Mapped[int | None] = mapped_column(Integer)
    ground_clearance_mm: Mapped[int | None] = mapped_column(Integer)
    ground_clearance_laden_mm: Mapped[int | None] = mapped_column(Integer)
    ground_clearance_unladen_mm: Mapped[int | None] = mapped_column(Integer)
    is_four_wheel_drive: Mapped[bool | None] = mapped_column(Boolean, index=True)
    has_permanent_rear_seats: Mapped[bool | None] = mapped_column(Boolean)
    has_rear_side_windows: Mapped[bool | None] = mapped_column(Boolean)
    has_rear_windowed_door: Mapped[bool | None] = mapped_column(Boolean)
    has_separate_cargo_compartment: Mapped[bool | None] = mapped_column(Boolean)
    is_special_purpose: Mapped[bool | None] = mapped_column(Boolean, index=True)
    vehicle_purpose_type: Mapped[str | None] = mapped_column(String(50), index=True)
    inference_details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    inference_flags_json: Mapped[list[str] | None] = mapped_column(JSON_TYPE)
    inference_rules_version: Mapped[str | None] = mapped_column(String(100))
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    missing_fields_json: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, nullable=False
    )
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
    engine_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    maximum_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    transmission_summary: Mapped[str | None] = mapped_column(String(300))
    transmission_type: Mapped[str | None] = mapped_column(String(300), index=True)
    clutch_type: Mapped[str | None] = mapped_column(String(30), index=True)
    transmission_gears: Mapped[int | None] = mapped_column(Integer)
    drive_type: Mapped[str | None] = mapped_column(String(300), index=True)
    engine_layout: Mapped[str | None] = mapped_column(String(30), index=True)
    aspiration_type: Mapped[str | None] = mapped_column(String(50), index=True)
    cylinder_layout: Mapped[str | None] = mapped_column(String(30), index=True)
    body_type: Mapped[str | None] = mapped_column(String(50), index=True)
    motor_total_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_total_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    motor_count: Mapped[int | None] = mapped_column(Integer)
    motor_layout: Mapped[str | None] = mapped_column(String(200))
    system_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    system_power_hp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    battery_type: Mapped[str | None] = mapped_column(String(300))
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    spec_count: Mapped[int] = mapped_column(Integer, nullable=False)
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CustomsCalculation(Base):
    """Один воспроизводимый сценарий расчёта таможенных платежей."""

    __tablename__ = "customs_calculations"
    __table_args__ = (
        UniqueConstraint(
            "spec_id",
            "importer_type",
            name="uq_customs_calculations_spec_importer",
        ),
        Index(
            "ix_customs_calculations_calculation_date_id",
            "calculation_date",
            "id",
        ),
        Index(
            "ix_customs_calculations_spec_date_id",
            "spec_id",
            "calculation_date",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), index=True)
    importer_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rules_version: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    price_source: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_price_cny: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    customs_value_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cny_rate_nominal: Mapped[int | None] = mapped_column(Integer)
    cny_rate_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cny_rate_date: Mapped[date | None] = mapped_column(Date)
    eur_rate_nominal: Mapped[int | None] = mapped_column(Integer)
    eur_rate_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    eur_rate_date: Mapped[date | None] = mapped_column(Date)
    model_year: Mapped[int | None] = mapped_column(Integer)
    assumed_production_date: Mapped[date | None] = mapped_column(Date)
    age_months: Mapped[int | None] = mapped_column(Integer)
    energy_type: Mapped[str | None] = mapped_column(String(50), index=True)
    body_type: Mapped[str | None] = mapped_column(String(50), index=True)
    engine_displacement_ml: Mapped[int | None] = mapped_column(Integer)
    tnved_code: Mapped[str | None] = mapped_column(String(20), index=True)
    classification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False
    )
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CbrExchangeRate(Base):
    """Последний применённый официальный курс валюты Банка России."""

    __tablename__ = "cbr_exchange_rates"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    nominal: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_rub: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CustomsPaymentResult(Base):
    """Результат одного вида платежа внутри таможенного расчёта."""

    __tablename__ = "customs_payment_results"
    __table_args__ = (PrimaryKeyConstraint("calculation_id", "payment_type"),)

    calculation_id: Mapped[int] = mapped_column(
        ForeignKey("customs_calculations.id"), index=True
    )
    payment_type: Mapped[str] = mapped_column(String(50), index=True)
    amount_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    rule_code: Mapped[str | None] = mapped_column(String(150))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


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
    __table_args__ = (PrimaryKeyConstraint("month", "subrank_type", "series_id"),)

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
    __table_args__ = (PrimaryKeyConstraint("snapshot_date", "city_id", "series_id"),)

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
    __table_args__ = (
        PrimaryKeyConstraint("series_id", "color_scope", "color_id"),
        Index(
            "ix_series_gallery_colors_series_scope_name",
            "series_id",
            "color_scope",
            "name",
        ),
    )

    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    color_scope: Mapped[str] = mapped_column(String(20))
    color_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    color_values: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    picture_count: Mapped[int | None] = mapped_column(Integer)
    gallery_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)


class SeriesPhoto(Base):
    """Фотография серии с прямой ссылкой на изображение."""

    __tablename__ = "series_photos"
    __table_args__ = (
        Index("ix_series_photos_series_category_id", "series_id", "category_id", "id"),
        Index("ix_series_photos_series_spec_id", "series_id", "spec_id", "id"),
    )

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
        PrimaryKeyConstraint("photo_id", "series_id", "color_scope", "color_id"),
        ForeignKeyConstraint(
            ["series_id", "color_scope", "color_id"],
            [
                "series_gallery_colors.series_id",
                "series_gallery_colors.color_scope",
                "series_gallery_colors.color_id",
            ],
        ),
        Index(
            "ix_series_photo_colors_lookup",
            "series_id",
            "color_scope",
            "color_id",
            "photo_id",
        ),
    )

    photo_id: Mapped[int] = mapped_column(ForeignKey("series_photos.id"), index=True)
    series_id: Mapped[int] = mapped_column(Integer, index=True)
    color_scope: Mapped[str] = mapped_column(String(20))
    color_id: Mapped[int] = mapped_column(Integer)


class GalleryCrawlTask(Base):
    """Состояние загрузки одной страницы фотогалереи."""

    __tablename__ = "gallery_crawl_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    color_scope: Mapped[str | None] = mapped_column(String(20))
    color_id: Mapped[int | None] = mapped_column(Integer)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    photo_count: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConfigCrawlTask(Base):
    """Состояние загрузки полной конфигурации комплектации."""

    __tablename__ = "config_crawl_tasks"

    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parameter_count: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
