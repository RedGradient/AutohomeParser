from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text

from autohome.powertrain_schema import ensure_powertrain_schema


class PowertrainSchemaTests(unittest.TestCase):
    def test_adds_recycling_fee_columns_to_existing_table(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE TABLE spec_powertrains (spec_id INTEGER PRIMARY KEY)")
                )

            ensure_powertrain_schema(engine)

            columns = {
                column["name"]
                for column in inspect(engine).get_columns("spec_powertrains")
            }
            self.assertTrue(
                {
                    "recycling_fee_powertrain_type",
                    "recycling_fee_power_kw",
                    "recycling_fee_power_source",
                }.issubset(columns)
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
