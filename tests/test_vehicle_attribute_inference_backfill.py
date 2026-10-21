from __future__ import annotations

from types import SimpleNamespace
import unittest

from sqlalchemy import create_engine, insert, select

from autohome.models import Base, Series, Spec, SpecVehicleAttributes
from autohome.vehicle_attribute_inference import (
    VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION,
)
from backfill_vehicle_attribute_inferences import backfill


class VehicleAttributeInferenceBackfillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                insert(Series),
                {
                    "id": 1,
                    "name": "Грузовая серия",
                    "raw_json": {"name": "运输车"},
                },
            )
            connection.execute(
                insert(Spec),
                {
                    "id": 10,
                    "series_id": 1,
                    "name": "Грузовая комплектация",
                    "raw_json": {"name": "普通运输车"},
                },
            )
            connection.execute(
                insert(SpecVehicleAttributes),
                {
                    "spec_id": 10,
                    "series_id": 1,
                    "body_type": "TRUCK",
                    "vehicle_class": "LIGHT_TRUCK",
                    "seat_count_min": 3,
                    "seat_count_max": 3,
                    "curb_mass_kg": 1590,
                    "payload_kg_min": 1475,
                    "payload_kg_max": 1475,
                    "is_complete": True,
                    "missing_fields_json": [],
                    "warnings_json": [],
                    "normalization_version": 1,
                },
            )

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def args(**overrides):
        values = {
            "batch_size": 100,
            "limit": None,
            "min_spec_id": None,
            "max_spec_id": None,
            "shard_index": 0,
            "shard_count": 1,
            "only_outdated": False,
            "write": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_dry_run_does_not_write(self):
        counts = backfill(self.engine, self.args())

        self.assertEqual(counts["selected"], 1)
        self.assertEqual(counts["is_special_purpose_false"], 1)
        self.assertEqual(counts["field_gross_mass_kg_applied"], 1)
        self.assertEqual(counts["technical_category_N1"], 1)
        with self.engine.connect() as connection:
            row = connection.execute(select(SpecVehicleAttributes)).one()
        self.assertIsNone(row.is_special_purpose)
        self.assertIsNone(row.gross_mass_kg)
        self.assertIsNone(row.vehicle_technical_category)
        self.assertIsNone(row.inference_rules_version)

    def test_write_is_idempotent_and_only_outdated_skips_current_version(self):
        first = backfill(self.engine, self.args(write=True))
        second = backfill(
            self.engine,
            self.args(write=True, only_outdated=True),
        )

        self.assertEqual(first["selected"], 1)
        self.assertEqual(second["selected"], 0)
        with self.engine.connect() as connection:
            row = connection.execute(select(SpecVehicleAttributes)).one()
        self.assertIs(row.is_special_purpose, False)
        self.assertEqual(row.gross_mass_kg, 3260)
        self.assertEqual(row.vehicle_technical_category, "N1")
        self.assertEqual(
            row.inference_rules_version,
            VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION,
        )
        self.assertEqual(row.inference_flags_json, ["INFERRED_INPUTS_USED"])


if __name__ == "__main__":
    unittest.main()
