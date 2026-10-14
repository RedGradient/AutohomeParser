from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_letter: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(100))
    logo: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)


class Spec(Base):
    __tablename__ = "specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    state: Mapped[int | None] = mapped_column(Integer, index=True)
    guide_price: Mapped[str | None] = mapped_column(String(100))
    dealer_price: Mapped[str | None] = mapped_column(String(100))
    discount: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    config_available: Mapped[bool | None] = mapped_column(Boolean)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)


class ParameterDefinition(Base):
    __tablename__ = "parameter_definitions"

    title_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_name: Mapped[str | None] = mapped_column(String(200))
    section_name: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    item_id: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)


class SpecParameter(Base):
    __tablename__ = "spec_parameters"
    __table_args__ = (UniqueConstraint("spec_id", "title_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id"), index=True)
    title_id: Mapped[int] = mapped_column(
        ForeignKey("parameter_definitions.title_id"), index=True
    )
    value: Mapped[str | None] = mapped_column(Text)
    option_price: Mapped[str | None] = mapped_column(String(100))
    subitems_json: Mapped[str | None] = mapped_column(Text)
    color_info_json: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
