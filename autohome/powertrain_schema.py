from __future__ import annotations

from sqlalchemy import inspect, text

from autohome.models import Base


POWERTRAIN_COLUMNS = {
    "recycling_fee_powertrain_type": "VARCHAR(30)",
    "recycling_fee_power_kw": "NUMERIC(12, 3)",
    "recycling_fee_power_source": "VARCHAR(60)",
}


def ensure_powertrain_schema(engine) -> None:
    """Создать таблицы и безопасно добавить нормативные поля мощности."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(12911713)"))
        Base.metadata.create_all(connection)
        existing = {
            column["name"]
            for column in inspect(connection).get_columns("spec_powertrains")
        }
        for name, declared_type in POWERTRAIN_COLUMNS.items():
            if name in existing:
                continue
            clause = (
                "ADD COLUMN IF NOT EXISTS"
                if connection.dialect.name == "postgresql"
                else "ADD COLUMN"
            )
            connection.execute(
                text(f"ALTER TABLE spec_powertrains {clause} {name} {declared_type}")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_spec_powertrains_recycling_fee_powertrain_type "
                "ON spec_powertrains (recycling_fee_powertrain_type)"
            )
        )
