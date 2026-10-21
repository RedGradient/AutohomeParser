from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect

from autohome.items import SpecVehicleAttributesItem
from autohome.models import Base, SpecVehicleAttributes
from autohome.pipelines import SqlAlchemyPipeline


class SpecVehicleAttributesModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_table_contains_classification_inputs(self):
        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns(
                SpecVehicleAttributes.__tablename__
            )
        }

        self.assertTrue(
            {
                "vehicle_class",
                "vehicle_technical_category",
                "seat_count_min",
                "seat_count_max",
                "gross_mass_kg",
                "payload_kg_min",
                "payload_kg_max",
                "cargo_length_min_mm",
                "cargo_length_max_mm",
                "ground_clearance_laden_mm",
                "ground_clearance_unladen_mm",
                "has_rear_side_windows",
                "has_separate_cargo_compartment",
                "is_special_purpose",
                "vehicle_purpose_type",
                "inference_details_json",
                "inference_flags_json",
                "inference_rules_version",
                "missing_fields_json",
                "warnings_json",
                "normalization_version",
            }.issubset(columns)
        )

    def test_pipeline_maps_item_to_model(self):
        self.assertIs(
            SqlAlchemyPipeline.model_by_item[SpecVehicleAttributesItem],
            SpecVehicleAttributes,
        )


if __name__ == "__main__":
    unittest.main()
