from __future__ import annotations

from sqlalchemy import inspect, text

from autohome.models import Base


INFERENCE_COLUMNS = {
    "vehicle_technical_category": "VARCHAR(10)",
    "vehicle_purpose_type": "VARCHAR(50)",
    "inference_details_json": "JSON",
    "inference_flags_json": "JSON",
    "inference_rules_version": "VARCHAR(100)",
}


def ensure_vehicle_attribute_schema(engine) -> None:
    """Создать таблицы и безопасно дополнить существующую таблицу полями вывода."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(87050001)"))
        Base.metadata.create_all(connection)
        existing = {
            column["name"]
            for column in inspect(connection).get_columns(
                "spec_vehicle_attributes"
            )
        }
        for name, declared_type in INFERENCE_COLUMNS.items():
            if name in existing:
                continue
            if connection.dialect.name == "postgresql":
                sql_type = "JSONB" if declared_type == "JSON" else declared_type
                clause = "ADD COLUMN IF NOT EXISTS"
            else:
                sql_type = declared_type
                clause = "ADD COLUMN"
            connection.execute(
                text(
                    "ALTER TABLE spec_vehicle_attributes "
                    f"{clause} {name} {sql_type}"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_spec_vehicle_attributes_vehicle_technical_category "
                "ON spec_vehicle_attributes (vehicle_technical_category)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_spec_vehicle_attributes_vehicle_purpose_type "
                "ON spec_vehicle_attributes (vehicle_purpose_type)"
            )
        )
