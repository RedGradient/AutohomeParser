from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text

from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema


class VehicleAttributeSchemaTests(unittest.TestCase):
    def test_adds_inference_columns_to_existing_table(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE spec_vehicle_attributes "
                        "(spec_id INTEGER PRIMARY KEY)"
                    )
                )

            ensure_vehicle_attribute_schema(engine)

            columns = {
                column["name"]
                for column in inspect(engine).get_columns(
                    "spec_vehicle_attributes"
                )
            }
            self.assertTrue(
                {
                    "vehicle_purpose_type",
                    "inference_details_json",
                    "inference_flags_json",
                    "inference_rules_version",
                }.issubset(columns)
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
