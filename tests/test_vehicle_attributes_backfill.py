from __future__ import annotations

import unittest

from sqlalchemy import create_engine, func, insert, select

from autohome.models import Base, SpecVehicleAttributes
from autohome.vehicle_attributes_normalizer import normalize_vehicle_attributes
from normalize_vehicle_attributes import (
    build_normalized_rows,
    upsert_rows,
    validate_arguments,
)


class VehicleAttributesBackfillTests(unittest.TestCase):
    def test_build_rows_uses_same_normalized_shape_as_spider(self):
        fields = {
            "vehicle_class": "轻客",
            "body_description": "5门7座MPV",
            "curb_mass_kg": "1980",
            "gross_mass_kg": "2650",
            "length_mm": "5100",
            "width_mm": "1900",
            "height_mm": "1900",
            "wheelbase_mm": "3100",
            "door_count": "-",
            "seat_count": "-",
            "body_type": "客车",
            "body_construction": "承载式",
        }
        reverse_ids = {
            parameter_id: field
            for parameter_id, field in enumerate(fields, start=1)
        }
        parameter_rows = [
            (101, parameter_id, fields[field])
            for parameter_id, field in reverse_ids.items()
        ]

        rows, skipped = build_normalized_rows(
            [(101, 10, "AWD")], parameter_rows, reverse_ids
        )

        self.assertEqual(skipped, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vehicle_class"], "LIGHT_COMMERCIAL_VAN")
        self.assertEqual(rows[0]["body_type"], "VAN")
        self.assertEqual(rows[0]["seat_count_min"], 7)
        self.assertTrue(rows[0]["is_four_wheel_drive"])

    def test_partial_source_row_is_skipped(self):
        reverse_ids = {1: "vehicle_class"}

        rows, skipped = build_normalized_rows(
            [(101, 10, None)], [(101, 1, "轻客")], reverse_ids
        )

        self.assertEqual(rows, [])
        self.assertEqual(skipped, 1)

    def test_build_rows_extracts_seats_from_selected_subitem(self):
        fields = {
            "vehicle_class": "轻客",
            "body_description": "客车",
            "curb_mass_kg": "1980",
            "gross_mass_kg": "2650",
            "length_mm": "5100",
            "width_mm": "1900",
            "height_mm": "1900",
            "wheelbase_mm": "3100",
            "door_count": "-",
            "seat_count": "-",
            "body_type": "客车",
            "body_construction": "承载式",
        }
        reverse_ids = {
            parameter_id: field
            for parameter_id, field in enumerate(fields, start=1)
        }
        parameter_rows = [
            (
                101,
                parameter_id,
                {
                    "itemname": value,
                    "sublist": (
                        [{"name": "10-12", "value": "●"}]
                        if field == "seat_count"
                        else []
                    ),
                },
            )
            for parameter_id, field in reverse_ids.items()
            for value in [fields[field]]
        ]

        rows, skipped = build_normalized_rows(
            [(101, 10, None)],
            parameter_rows,
            reverse_ids,
        )

        self.assertEqual(skipped, 0)
        self.assertEqual(rows[0]["seat_count_min"], 10)
        self.assertEqual(rows[0]["seat_count_max"], 12)

    def test_invalid_shard_configuration_is_rejected(self):
        class Args:
            database_url = "sqlite://"
            batch_size = 100
            limit = None
            min_spec_id = None
            max_spec_id = None
            shard_index = 2
            shard_count = 2

        with self.assertRaises(SystemExit):
            validate_arguments(Args())

    def test_upsert_splits_large_input_into_safe_chunks(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        rows = [
            normalize_vehicle_attributes(
                spec_id,
                10,
                {"vehicle_class": "PICKUP", "body_type": "PICKUP"},
            )
            for spec_id in range(1, 502)
        ]

        with engine.begin() as connection:
            upsert_rows(connection, rows)
            count = connection.scalar(select(func.count(SpecVehicleAttributes.spec_id)))

        engine.dispose()
        self.assertEqual(count, 501)

    def test_normalization_upsert_preserves_inference_metadata(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        original = normalize_vehicle_attributes(
            1,
            10,
            {"vehicle_class": "PICKUP", "body_type": "PICKUP"},
        )
        original.update(
            gross_mass_kg=3260,
            is_special_purpose=False,
            inference_details_json={"decisions": {}},
            inference_flags_json=["INFERRED_INPUTS_USED"],
            inference_rules_version="test-v1",
        )
        refreshed = normalize_vehicle_attributes(
            1,
            10,
            {"vehicle_class": "PICKUP", "body_type": "PICKUP"},
        )

        with engine.begin() as connection:
            connection.execute(insert(SpecVehicleAttributes), original)
            upsert_rows(connection, [refreshed])
            row = connection.execute(select(SpecVehicleAttributes)).one()

        engine.dispose()
        self.assertIs(row.is_special_purpose, False)
        self.assertEqual(row.gross_mass_kg, 3260)
        self.assertEqual(row.inference_flags_json, ["INFERRED_INPUTS_USED"])
        self.assertEqual(row.inference_rules_version, "test-v1")


if __name__ == "__main__":
    unittest.main()
