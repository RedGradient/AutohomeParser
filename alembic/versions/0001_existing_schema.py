"""Зафиксировать исходную схему явными операциями Alembic.

Revision ID: 0001_existing_schema
Revises: None
"""

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать исходную схему независимо от текущих ORM-моделей."""
    op.create_table(
        "attention_rankings",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("subrank_type", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("attention_index", sa.Integer(), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_date", "city_id", "subrank_type", "series_id"
        ),
    )
    op.create_index(
        op.f("ix_attention_rankings_series_id"),
        "attention_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "brand_monthly_sales",
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("brand_name", sa.String(length=300), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("sales_count", sa.Integer(), nullable=False),
        sa.Column("rank_change", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("month", "brand_id"),
    )
    op.create_index(
        op.f("ix_brand_monthly_sales_brand_id"),
        "brand_monthly_sales",
        ["brand_id"],
        unique=False,
    )
    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("series_count", sa.Integer(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "cbr_exchange_rates",
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("nominal", sa.Integer(), nullable=False),
        sa.Column("rate_rub", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("currency"),
    )
    op.create_index(
        op.f("ix_cbr_exchange_rates_rate_date"),
        "cbr_exchange_rates",
        ["rate_date"],
        unique=False,
    )
    op.create_table(
        "discount_rankings",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("spec_id", sa.Integer(), nullable=True),
        sa.Column("spec_name", sa.String(length=1000), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("discount_yuan", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("discount_percent", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("snapshot_date", "city_id", "series_id"),
    )
    op.create_index(
        op.f("ix_discount_rankings_series_id"),
        "discount_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discount_rankings_spec_id"),
        "discount_rankings",
        ["spec_id"],
        unique=False,
    )
    op.create_table(
        "manufacturers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("real_brand_id", sa.Integer(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_manufacturers_real_brand_id"),
        "manufacturers",
        ["real_brand_id"],
        unique=False,
    )
    op.create_table(
        "measured_test_rankings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("subrank_type", sa.Integer(), nullable=False),
        sa.Column("subrank_code", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("tested_spec_name", sa.String(length=1000), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=300), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("metric_unit", sa.String(length=50), nullable=True),
        sa.Column("secondary_metric_text", sa.String(length=300), nullable=True),
        sa.Column("test_environment", sa.String(length=500), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_measured_test_rankings_series_id"),
        "measured_test_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_measured_test_rankings_subrank_code"),
        "measured_test_rankings",
        ["subrank_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_measured_test_rankings_subrank_type"),
        "measured_test_rankings",
        ["subrank_type"],
        unique=False,
    )
    op.create_table(
        "new_energy_rankings",
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("subrank_type", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("sales_count", sa.Integer(), nullable=True),
        sa.Column("rank_change", sa.Integer(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("month", "subrank_type", "series_id"),
    )
    op.create_index(
        op.f("ix_new_energy_rankings_brand_id"),
        "new_energy_rankings",
        ["brand_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_new_energy_rankings_series_id"),
        "new_energy_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "parameter_groups",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "resale_value_rankings",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "resale_rate_percent", sa.Numeric(precision=8, scale=3), nullable=True
        ),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("snapshot_date", "series_id"),
    )
    op.create_index(
        op.f("ix_resale_value_rankings_series_id"),
        "resale_value_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "series_monthly_sales",
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("sales_count", sa.Integer(), nullable=False),
        sa.Column("rank_change", sa.Integer(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("month", "series_id"),
    )
    op.create_index(
        op.f("ix_series_monthly_sales_brand_id"),
        "series_monthly_sales",
        ["brand_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_series_monthly_sales_series_id"),
        "series_monthly_sales",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "smart_test_rankings",
        sa.Column("subrank_type", sa.Integer(), nullable=False),
        sa.Column("subrank_code", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.String(length=300), nullable=False),
        sa.Column("overall_grade", sa.String(length=20), nullable=True),
        sa.Column(
            "dimension_grades_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("tested_spec_name", sa.String(length=1000), nullable=True),
        sa.Column("software_version", sa.String(length=300), nullable=True),
        sa.Column("system_description", sa.Text(), nullable=True),
        sa.Column("price_text", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("subrank_type", "subrank_code", "series_id"),
    )
    op.create_index(
        op.f("ix_smart_test_rankings_series_id"),
        "smart_test_rankings",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "technology_rankings",
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("technology_id", sa.BigInteger(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("equipped_series_count", sa.Integer(), nullable=True),
        sa.Column("loudness_index", sa.Integer(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("snapshot_date", "technology_id"),
    )
    op.create_table(
        "brand_manufacturers",
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("manufacturer_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manufacturer_id"],
            ["manufacturers.id"],
        ),
        sa.PrimaryKeyConstraint("brand_id", "manufacturer_id"),
    )
    op.create_table(
        "parameter_sections",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["parameter_groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "name"),
    )
    op.create_index(
        op.f("ix_parameter_sections_group_id"),
        "parameter_sections",
        ["group_id"],
        unique=False,
    )
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("manufacturer_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("is_new_energy", sa.Boolean(), nullable=True),
        sa.Column("spec_count", sa.Integer(), nullable=True),
        sa.Column("state", sa.Integer(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manufacturer_id"],
            ["manufacturers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_series_brand_id"), "series", ["brand_id"], unique=False)
    op.create_index(
        op.f("ix_series_is_new_energy"), "series", ["is_new_energy"], unique=False
    )
    op.create_index(
        op.f("ix_series_manufacturer_id"), "series", ["manufacturer_id"], unique=False
    )
    op.create_index(op.f("ix_series_state"), "series", ["state"], unique=False)
    op.create_table(
        "gallery_crawl_tasks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("color_scope", sa.String(length=20), nullable=True),
        sa.Column("color_id", sa.Integer(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("photo_count", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gallery_crawl_tasks_category_id"),
        "gallery_crawl_tasks",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gallery_crawl_tasks_series_id"),
        "gallery_crawl_tasks",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gallery_crawl_tasks_status"),
        "gallery_crawl_tasks",
        ["status"],
        unique=False,
    )
    op.create_table(
        "modifications",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("modification_key", sa.Text(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("model_year", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=1000), nullable=False),
        sa.Column("energy_type", sa.String(length=200), nullable=True),
        sa.Column("engine_summary", sa.String(length=300), nullable=True),
        sa.Column("engine_displacement_ml", sa.Integer(), nullable=True),
        sa.Column("engine_model", sa.String(length=300), nullable=True),
        sa.Column("engine_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("engine_power_hp", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("maximum_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("transmission_summary", sa.String(length=300), nullable=True),
        sa.Column("transmission_type", sa.String(length=300), nullable=True),
        sa.Column("clutch_type", sa.String(length=30), nullable=True),
        sa.Column("transmission_gears", sa.Integer(), nullable=True),
        sa.Column("drive_type", sa.String(length=300), nullable=True),
        sa.Column("engine_layout", sa.String(length=30), nullable=True),
        sa.Column("aspiration_type", sa.String(length=50), nullable=True),
        sa.Column("cylinder_layout", sa.String(length=30), nullable=True),
        sa.Column("body_type", sa.String(length=50), nullable=True),
        sa.Column(
            "motor_total_power_kw", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column(
            "motor_total_power_hp", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column("motor_count", sa.Integer(), nullable=True),
        sa.Column("motor_layout", sa.String(length=200), nullable=True),
        sa.Column("system_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("system_power_hp", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column(
            "battery_capacity_kwh", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column("battery_type", sa.String(length=300), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("spec_count", sa.Integer(), nullable=False),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("modification_key"),
    )
    op.create_index(
        op.f("ix_modifications_aspiration_type"),
        "modifications",
        ["aspiration_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_body_type"), "modifications", ["body_type"], unique=False
    )
    op.create_index(
        op.f("ix_modifications_clutch_type"),
        "modifications",
        ["clutch_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_cylinder_layout"),
        "modifications",
        ["cylinder_layout"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_drive_type"),
        "modifications",
        ["drive_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_energy_type"),
        "modifications",
        ["energy_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_engine_layout"),
        "modifications",
        ["engine_layout"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_engine_model"),
        "modifications",
        ["engine_model"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_is_complete"),
        "modifications",
        ["is_complete"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_model_year"),
        "modifications",
        ["model_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_modifications_series_id"), "modifications", ["series_id"], unique=False
    )
    op.create_index(
        op.f("ix_modifications_transmission_type"),
        "modifications",
        ["transmission_type"],
        unique=False,
    )
    op.create_table(
        "parameter_definitions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("semantic_key", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("baike_id", sa.Integer(), nullable=True),
        sa.Column("baike_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["parameter_sections.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("semantic_key"),
    )
    op.create_index(
        op.f("ix_parameter_definitions_item_id"),
        "parameter_definitions",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parameter_definitions_section_id"),
        "parameter_definitions",
        ["section_id"],
        unique=False,
    )
    op.create_table(
        "series_gallery_colors",
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("color_scope", sa.String(length=20), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "color_values",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("picture_count", sa.Integer(), nullable=True),
        sa.Column("gallery_url", sa.Text(), nullable=False),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("series_id", "color_scope", "color_id"),
    )
    op.create_index(
        op.f("ix_series_gallery_colors_series_id"),
        "series_gallery_colors",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "series_photos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("spec_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("category_name", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_series_photos_category_id"),
        "series_photos",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_series_photos_series_id"), "series_photos", ["series_id"], unique=False
    )
    op.create_index(
        op.f("ix_series_photos_spec_id"), "series_photos", ["spec_id"], unique=False
    )
    op.create_table(
        "series_photo_colors",
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("color_scope", sa.String(length=20), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["series_photos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["series_id", "color_scope", "color_id"],
            [
                "series_gallery_colors.series_id",
                "series_gallery_colors.color_scope",
                "series_gallery_colors.color_id",
            ],
        ),
        sa.PrimaryKeyConstraint("photo_id", "series_id", "color_scope", "color_id"),
    )
    op.create_index(
        op.f("ix_series_photo_colors_photo_id"),
        "series_photo_colors",
        ["photo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_series_photo_colors_series_id"),
        "series_photo_colors",
        ["series_id"],
        unique=False,
    )
    op.create_table(
        "specs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("state", sa.Integer(), nullable=True),
        sa.Column("guide_price_yuan", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column(
            "dealer_price_yuan", sa.Numeric(precision=16, scale=2), nullable=True
        ),
        sa.Column("discount_yuan", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("config_available", sa.Boolean(), nullable=True),
        sa.Column("modification_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["modification_id"],
            ["modifications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_specs_config_available"), "specs", ["config_available"], unique=False
    )
    op.create_index(
        op.f("ix_specs_modification_id"), "specs", ["modification_id"], unique=False
    )
    op.create_index(op.f("ix_specs_series_id"), "specs", ["series_id"], unique=False)
    op.create_index(op.f("ix_specs_state"), "specs", ["state"], unique=False)
    op.create_index(op.f("ix_specs_year"), "specs", ["year"], unique=False)
    op.create_table(
        "config_crawl_tasks",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("parameter_count", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["specs.id"],
        ),
        sa.PrimaryKeyConstraint("spec_id"),
    )
    op.create_index(
        op.f("ix_config_crawl_tasks_series_id"),
        "config_crawl_tasks",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_config_crawl_tasks_status"),
        "config_crawl_tasks",
        ["status"],
        unique=False,
    )
    op.create_table(
        "customs_calculations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("importer_type", sa.String(length=30), nullable=False),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("rules_version", sa.String(length=100), nullable=False),
        sa.Column("price_source", sa.String(length=30), nullable=False),
        sa.Column(
            "vehicle_price_cny", sa.Numeric(precision=16, scale=2), nullable=True
        ),
        sa.Column(
            "customs_value_rub", sa.Numeric(precision=18, scale=2), nullable=True
        ),
        sa.Column("cny_rate_nominal", sa.Integer(), nullable=True),
        sa.Column("cny_rate_rub", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("cny_rate_date", sa.Date(), nullable=True),
        sa.Column("eur_rate_nominal", sa.Integer(), nullable=True),
        sa.Column("eur_rate_rub", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("eur_rate_date", sa.Date(), nullable=True),
        sa.Column("model_year", sa.Integer(), nullable=True),
        sa.Column("assumed_production_date", sa.Date(), nullable=True),
        sa.Column("age_months", sa.Integer(), nullable=True),
        sa.Column("energy_type", sa.String(length=50), nullable=True),
        sa.Column("body_type", sa.String(length=50), nullable=True),
        sa.Column("engine_displacement_ml", sa.Integer(), nullable=True),
        sa.Column("tnved_code", sa.String(length=20), nullable=True),
        sa.Column("classification_status", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "input_snapshot_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "warnings_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["specs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "spec_id",
            "importer_type",
            "calculation_date",
            "rules_version",
            "price_source",
        ),
    )
    op.create_index(
        op.f("ix_customs_calculations_body_type"),
        "customs_calculations",
        ["body_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_calculation_date"),
        "customs_calculations",
        ["calculation_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_classification_status"),
        "customs_calculations",
        ["classification_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_energy_type"),
        "customs_calculations",
        ["energy_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_importer_type"),
        "customs_calculations",
        ["importer_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_rules_version"),
        "customs_calculations",
        ["rules_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_spec_id"),
        "customs_calculations",
        ["spec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_status"),
        "customs_calculations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_calculations_tnved_code"),
        "customs_calculations",
        ["tnved_code"],
        unique=False,
    )
    op.create_table(
        "spec_parameters",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.BigInteger(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "option_price_yuan", sa.Numeric(precision=16, scale=2), nullable=True
        ),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parameter_id"],
            ["parameter_definitions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["specs.id"],
        ),
        sa.PrimaryKeyConstraint("spec_id", "parameter_id"),
    )
    op.create_index(
        op.f("ix_spec_parameters_parameter_id"),
        "spec_parameters",
        ["parameter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_parameters_spec_id"), "spec_parameters", ["spec_id"], unique=False
    )
    op.create_table(
        "spec_powertrains",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("model_year", sa.Integer(), nullable=True),
        sa.Column("energy_type", sa.String(length=200), nullable=True),
        sa.Column("engine_summary", sa.String(length=300), nullable=True),
        sa.Column("engine_displacement_ml", sa.Integer(), nullable=True),
        sa.Column("engine_model", sa.String(length=300), nullable=True),
        sa.Column("engine_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("engine_power_hp", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("maximum_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("transmission_summary", sa.String(length=300), nullable=True),
        sa.Column("transmission_type", sa.String(length=300), nullable=True),
        sa.Column("clutch_type", sa.String(length=30), nullable=True),
        sa.Column("transmission_gears", sa.Integer(), nullable=True),
        sa.Column("drive_type", sa.String(length=300), nullable=True),
        sa.Column("engine_layout", sa.String(length=30), nullable=True),
        sa.Column("aspiration_type", sa.String(length=50), nullable=True),
        sa.Column("cylinder_layout", sa.String(length=30), nullable=True),
        sa.Column("body_type", sa.String(length=50), nullable=True),
        sa.Column(
            "motor_total_power_kw", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column(
            "motor_total_power_hp", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column("motor_count", sa.Integer(), nullable=True),
        sa.Column("motor_layout", sa.String(length=200), nullable=True),
        sa.Column("system_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("system_power_hp", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("recycling_fee_powertrain_type", sa.String(length=30), nullable=True),
        sa.Column(
            "recycling_fee_power_kw", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column("recycling_fee_power_source", sa.String(length=60), nullable=True),
        sa.Column(
            "battery_capacity_kwh", sa.Numeric(precision=12, scale=3), nullable=True
        ),
        sa.Column("battery_type", sa.String(length=300), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column(
            "missing_fields_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["specs.id"],
        ),
        sa.PrimaryKeyConstraint("spec_id"),
    )
    op.create_index(
        op.f("ix_spec_powertrains_aspiration_type"),
        "spec_powertrains",
        ["aspiration_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_body_type"),
        "spec_powertrains",
        ["body_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_clutch_type"),
        "spec_powertrains",
        ["clutch_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_cylinder_layout"),
        "spec_powertrains",
        ["cylinder_layout"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_drive_type"),
        "spec_powertrains",
        ["drive_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_energy_type"),
        "spec_powertrains",
        ["energy_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_engine_layout"),
        "spec_powertrains",
        ["engine_layout"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_engine_model"),
        "spec_powertrains",
        ["engine_model"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_is_complete"),
        "spec_powertrains",
        ["is_complete"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_model_year"),
        "spec_powertrains",
        ["model_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_recycling_fee_powertrain_type"),
        "spec_powertrains",
        ["recycling_fee_powertrain_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_series_id"),
        "spec_powertrains",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_powertrains_transmission_type"),
        "spec_powertrains",
        ["transmission_type"],
        unique=False,
    )
    op.create_table(
        "spec_vehicle_attributes",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_class", sa.String(length=100), nullable=True),
        sa.Column("vehicle_technical_category", sa.String(length=10), nullable=True),
        sa.Column("body_type", sa.String(length=50), nullable=True),
        sa.Column("body_construction", sa.String(length=50), nullable=True),
        sa.Column("seat_count_min", sa.Integer(), nullable=True),
        sa.Column("seat_count_max", sa.Integer(), nullable=True),
        sa.Column("door_count", sa.Integer(), nullable=True),
        sa.Column("curb_mass_kg", sa.Integer(), nullable=True),
        sa.Column("curb_mass_kg_min", sa.Integer(), nullable=True),
        sa.Column("curb_mass_kg_max", sa.Integer(), nullable=True),
        sa.Column("gross_mass_kg", sa.Integer(), nullable=True),
        sa.Column("payload_kg_min", sa.Integer(), nullable=True),
        sa.Column("payload_kg_max", sa.Integer(), nullable=True),
        sa.Column("length_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("wheelbase_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_length_min_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_length_max_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_width_min_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_width_max_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_height_min_mm", sa.Integer(), nullable=True),
        sa.Column("cargo_height_max_mm", sa.Integer(), nullable=True),
        sa.Column("ground_clearance_mm", sa.Integer(), nullable=True),
        sa.Column("ground_clearance_laden_mm", sa.Integer(), nullable=True),
        sa.Column("ground_clearance_unladen_mm", sa.Integer(), nullable=True),
        sa.Column("is_four_wheel_drive", sa.Boolean(), nullable=True),
        sa.Column("has_permanent_rear_seats", sa.Boolean(), nullable=True),
        sa.Column("has_rear_side_windows", sa.Boolean(), nullable=True),
        sa.Column("has_rear_windowed_door", sa.Boolean(), nullable=True),
        sa.Column("has_separate_cargo_compartment", sa.Boolean(), nullable=True),
        sa.Column("is_special_purpose", sa.Boolean(), nullable=True),
        sa.Column("vehicle_purpose_type", sa.String(length=50), nullable=True),
        sa.Column(
            "inference_details_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "inference_flags_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("inference_rules_version", sa.String(length=100), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column(
            "missing_fields_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "warnings_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["specs.id"],
        ),
        sa.PrimaryKeyConstraint("spec_id"),
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_body_construction"),
        "spec_vehicle_attributes",
        ["body_construction"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_body_type"),
        "spec_vehicle_attributes",
        ["body_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_gross_mass_kg"),
        "spec_vehicle_attributes",
        ["gross_mass_kg"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_is_complete"),
        "spec_vehicle_attributes",
        ["is_complete"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_is_four_wheel_drive"),
        "spec_vehicle_attributes",
        ["is_four_wheel_drive"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_is_special_purpose"),
        "spec_vehicle_attributes",
        ["is_special_purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_series_id"),
        "spec_vehicle_attributes",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_vehicle_class"),
        "spec_vehicle_attributes",
        ["vehicle_class"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_vehicle_purpose_type"),
        "spec_vehicle_attributes",
        ["vehicle_purpose_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_vehicle_attributes_vehicle_technical_category"),
        "spec_vehicle_attributes",
        ["vehicle_technical_category"],
        unique=False,
    )
    op.create_table(
        "customs_payment_results",
        sa.Column("calculation_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_type", sa.String(length=50), nullable=False),
        sa.Column("amount_rub", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("rule_code", sa.String(length=150), nullable=True),
        sa.Column(
            "details_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["calculation_id"],
            ["customs_calculations.id"],
        ),
        sa.PrimaryKeyConstraint("calculation_id", "payment_type"),
    )
    op.create_index(
        op.f("ix_customs_payment_results_calculation_id"),
        "customs_payment_results",
        ["calculation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_payment_results_payment_type"),
        "customs_payment_results",
        ["payment_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customs_payment_results_status"),
        "customs_payment_results",
        ["status"],
        unique=False,
    )
    op.create_table(
        "parameter_color_sets",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["spec_parameters.spec_id", "spec_parameters.parameter_id"],
        ),
        sa.PrimaryKeyConstraint("spec_id", "parameter_id"),
    )
    op.create_index(
        op.f("ix_parameter_color_sets_parameter_id"),
        "parameter_color_sets",
        ["parameter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parameter_color_sets_spec_id"),
        "parameter_color_sets",
        ["spec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parameter_color_sets_type"),
        "parameter_color_sets",
        ["type"],
        unique=False,
    )
    op.create_table(
        "parameter_subitems",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.Boolean(), nullable=True),
        sa.Column(
            "option_price_yuan", sa.Numeric(precision=16, scale=2), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["spec_parameters.spec_id", "spec_parameters.parameter_id"],
        ),
        sa.PrimaryKeyConstraint("spec_id", "parameter_id", "position"),
    )
    op.create_index(
        op.f("ix_parameter_subitems_parameter_id"),
        "parameter_subitems",
        ["parameter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parameter_subitems_spec_id"),
        "parameter_subitems",
        ["spec_id"],
        unique=False,
    )
    op.create_table(
        "parameter_colors",
        sa.Column("spec_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("color_value", sa.String(length=200), nullable=True),
        sa.Column("price_yuan", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("picture_count", sa.Integer(), nullable=True),
        sa.Column("gallery_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["spec_id", "parameter_id"],
            ["parameter_color_sets.spec_id", "parameter_color_sets.parameter_id"],
        ),
        sa.PrimaryKeyConstraint("spec_id", "parameter_id", "position"),
    )
    op.create_index(
        op.f("ix_parameter_colors_parameter_id"),
        "parameter_colors",
        ["parameter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parameter_colors_spec_id"),
        "parameter_colors",
        ["spec_id"],
        unique=False,
    )


def downgrade() -> None:
    """Удалить все объекты исходной схемы в обратном порядке."""
    op.drop_index(op.f("ix_parameter_colors_spec_id"), table_name="parameter_colors")
    op.drop_index(
        op.f("ix_parameter_colors_parameter_id"), table_name="parameter_colors"
    )
    op.drop_table("parameter_colors")
    op.drop_index(
        op.f("ix_parameter_subitems_spec_id"), table_name="parameter_subitems"
    )
    op.drop_index(
        op.f("ix_parameter_subitems_parameter_id"), table_name="parameter_subitems"
    )
    op.drop_table("parameter_subitems")
    op.drop_index(
        op.f("ix_parameter_color_sets_type"), table_name="parameter_color_sets"
    )
    op.drop_index(
        op.f("ix_parameter_color_sets_spec_id"), table_name="parameter_color_sets"
    )
    op.drop_index(
        op.f("ix_parameter_color_sets_parameter_id"), table_name="parameter_color_sets"
    )
    op.drop_table("parameter_color_sets")
    op.drop_index(
        op.f("ix_customs_payment_results_status"), table_name="customs_payment_results"
    )
    op.drop_index(
        op.f("ix_customs_payment_results_payment_type"),
        table_name="customs_payment_results",
    )
    op.drop_index(
        op.f("ix_customs_payment_results_calculation_id"),
        table_name="customs_payment_results",
    )
    op.drop_table("customs_payment_results")
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_vehicle_technical_category"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_vehicle_purpose_type"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_vehicle_class"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_series_id"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_is_special_purpose"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_is_four_wheel_drive"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_is_complete"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_gross_mass_kg"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_body_type"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_index(
        op.f("ix_spec_vehicle_attributes_body_construction"),
        table_name="spec_vehicle_attributes",
    )
    op.drop_table("spec_vehicle_attributes")
    op.drop_index(
        op.f("ix_spec_powertrains_transmission_type"), table_name="spec_powertrains"
    )
    op.drop_index(op.f("ix_spec_powertrains_series_id"), table_name="spec_powertrains")
    op.drop_index(
        op.f("ix_spec_powertrains_recycling_fee_powertrain_type"),
        table_name="spec_powertrains",
    )
    op.drop_index(op.f("ix_spec_powertrains_model_year"), table_name="spec_powertrains")
    op.drop_index(
        op.f("ix_spec_powertrains_is_complete"), table_name="spec_powertrains"
    )
    op.drop_index(
        op.f("ix_spec_powertrains_engine_model"), table_name="spec_powertrains"
    )
    op.drop_index(
        op.f("ix_spec_powertrains_engine_layout"), table_name="spec_powertrains"
    )
    op.drop_index(
        op.f("ix_spec_powertrains_energy_type"), table_name="spec_powertrains"
    )
    op.drop_index(op.f("ix_spec_powertrains_drive_type"), table_name="spec_powertrains")
    op.drop_index(
        op.f("ix_spec_powertrains_cylinder_layout"), table_name="spec_powertrains"
    )
    op.drop_index(
        op.f("ix_spec_powertrains_clutch_type"), table_name="spec_powertrains"
    )
    op.drop_index(op.f("ix_spec_powertrains_body_type"), table_name="spec_powertrains")
    op.drop_index(
        op.f("ix_spec_powertrains_aspiration_type"), table_name="spec_powertrains"
    )
    op.drop_table("spec_powertrains")
    op.drop_index(op.f("ix_spec_parameters_spec_id"), table_name="spec_parameters")
    op.drop_index(op.f("ix_spec_parameters_parameter_id"), table_name="spec_parameters")
    op.drop_table("spec_parameters")
    op.drop_index(
        op.f("ix_customs_calculations_tnved_code"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_status"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_spec_id"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_rules_version"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_importer_type"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_energy_type"), table_name="customs_calculations"
    )
    op.drop_index(
        op.f("ix_customs_calculations_classification_status"),
        table_name="customs_calculations",
    )
    op.drop_index(
        op.f("ix_customs_calculations_calculation_date"),
        table_name="customs_calculations",
    )
    op.drop_index(
        op.f("ix_customs_calculations_body_type"), table_name="customs_calculations"
    )
    op.drop_table("customs_calculations")
    op.drop_index(op.f("ix_config_crawl_tasks_status"), table_name="config_crawl_tasks")
    op.drop_index(
        op.f("ix_config_crawl_tasks_series_id"), table_name="config_crawl_tasks"
    )
    op.drop_table("config_crawl_tasks")
    op.drop_index(op.f("ix_specs_year"), table_name="specs")
    op.drop_index(op.f("ix_specs_state"), table_name="specs")
    op.drop_index(op.f("ix_specs_series_id"), table_name="specs")
    op.drop_index(op.f("ix_specs_modification_id"), table_name="specs")
    op.drop_index(op.f("ix_specs_config_available"), table_name="specs")
    op.drop_table("specs")
    op.drop_index(
        op.f("ix_series_photo_colors_series_id"), table_name="series_photo_colors"
    )
    op.drop_index(
        op.f("ix_series_photo_colors_photo_id"), table_name="series_photo_colors"
    )
    op.drop_table("series_photo_colors")
    op.drop_index(op.f("ix_series_photos_spec_id"), table_name="series_photos")
    op.drop_index(op.f("ix_series_photos_series_id"), table_name="series_photos")
    op.drop_index(op.f("ix_series_photos_category_id"), table_name="series_photos")
    op.drop_table("series_photos")
    op.drop_index(
        op.f("ix_series_gallery_colors_series_id"), table_name="series_gallery_colors"
    )
    op.drop_table("series_gallery_colors")
    op.drop_index(
        op.f("ix_parameter_definitions_section_id"), table_name="parameter_definitions"
    )
    op.drop_index(
        op.f("ix_parameter_definitions_item_id"), table_name="parameter_definitions"
    )
    op.drop_table("parameter_definitions")
    op.drop_index(
        op.f("ix_modifications_transmission_type"), table_name="modifications"
    )
    op.drop_index(op.f("ix_modifications_series_id"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_model_year"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_is_complete"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_engine_model"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_engine_layout"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_energy_type"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_drive_type"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_cylinder_layout"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_clutch_type"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_body_type"), table_name="modifications")
    op.drop_index(op.f("ix_modifications_aspiration_type"), table_name="modifications")
    op.drop_table("modifications")
    op.drop_index(
        op.f("ix_gallery_crawl_tasks_status"), table_name="gallery_crawl_tasks"
    )
    op.drop_index(
        op.f("ix_gallery_crawl_tasks_series_id"), table_name="gallery_crawl_tasks"
    )
    op.drop_index(
        op.f("ix_gallery_crawl_tasks_category_id"), table_name="gallery_crawl_tasks"
    )
    op.drop_table("gallery_crawl_tasks")
    op.drop_index(op.f("ix_series_state"), table_name="series")
    op.drop_index(op.f("ix_series_manufacturer_id"), table_name="series")
    op.drop_index(op.f("ix_series_is_new_energy"), table_name="series")
    op.drop_index(op.f("ix_series_brand_id"), table_name="series")
    op.drop_table("series")
    op.drop_index(
        op.f("ix_parameter_sections_group_id"), table_name="parameter_sections"
    )
    op.drop_table("parameter_sections")
    op.drop_table("brand_manufacturers")
    op.drop_table("technology_rankings")
    op.drop_index(
        op.f("ix_smart_test_rankings_series_id"), table_name="smart_test_rankings"
    )
    op.drop_table("smart_test_rankings")
    op.drop_index(
        op.f("ix_series_monthly_sales_series_id"), table_name="series_monthly_sales"
    )
    op.drop_index(
        op.f("ix_series_monthly_sales_brand_id"), table_name="series_monthly_sales"
    )
    op.drop_table("series_monthly_sales")
    op.drop_index(
        op.f("ix_resale_value_rankings_series_id"), table_name="resale_value_rankings"
    )
    op.drop_table("resale_value_rankings")
    op.drop_table("parameter_groups")
    op.drop_index(
        op.f("ix_new_energy_rankings_series_id"), table_name="new_energy_rankings"
    )
    op.drop_index(
        op.f("ix_new_energy_rankings_brand_id"), table_name="new_energy_rankings"
    )
    op.drop_table("new_energy_rankings")
    op.drop_index(
        op.f("ix_measured_test_rankings_subrank_type"),
        table_name="measured_test_rankings",
    )
    op.drop_index(
        op.f("ix_measured_test_rankings_subrank_code"),
        table_name="measured_test_rankings",
    )
    op.drop_index(
        op.f("ix_measured_test_rankings_series_id"), table_name="measured_test_rankings"
    )
    op.drop_table("measured_test_rankings")
    op.drop_index(op.f("ix_manufacturers_real_brand_id"), table_name="manufacturers")
    op.drop_table("manufacturers")
    op.drop_index(op.f("ix_discount_rankings_spec_id"), table_name="discount_rankings")
    op.drop_index(
        op.f("ix_discount_rankings_series_id"), table_name="discount_rankings"
    )
    op.drop_table("discount_rankings")
    op.drop_index(
        op.f("ix_cbr_exchange_rates_rate_date"), table_name="cbr_exchange_rates"
    )
    op.drop_table("cbr_exchange_rates")
    op.drop_table("brands")
    op.drop_index(
        op.f("ix_brand_monthly_sales_brand_id"), table_name="brand_monthly_sales"
    )
    op.drop_table("brand_monthly_sales")
    op.drop_index(
        op.f("ix_attention_rankings_series_id"), table_name="attention_rankings"
    )
    op.drop_table("attention_rankings")
