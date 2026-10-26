from __future__ import annotations

import unittest

from audit_vehicle_classifications import audit_classifications
from autohome.models import Base, SpecVehicleAttributes
from tests.postgresql import PostgreSQLTestSchema, seed_specs


class VehicleClassificationAuditTests(unittest.TestCase):
    def test_audit_counts_statuses_and_missing_fields_without_writes(self):
        database = PostgreSQLTestSchema().create()
        engine = database.create_engine()
        Base.metadata.create_all(engine)
        seed_specs(engine, (1, 2))
        with engine.begin() as connection:
            connection.execute(
                SpecVehicleAttributes.__table__.insert(),
                {
                    "spec_id": 1,
                    "series_id": 10,
                    "body_type": "SEDAN",
                    "vehicle_class": "MIDSIZE_CAR",
                    "seat_count_min": 5,
                    "seat_count_max": 5,
                    "is_complete": True,
                    "missing_fields_json": [],
                    "warnings_json": [],
                    "normalization_version": 1,
                },
            )
            connection.execute(
                SpecVehicleAttributes.__table__.insert(),
                {
                    "spec_id": 2,
                    "series_id": 10,
                    "body_type": "TRUCK",
                    "vehicle_class": "LIGHT_TRUCK",
                    "gross_mass_kg": 3500,
                    "is_complete": True,
                    "missing_fields_json": [],
                    "warnings_json": [],
                    "normalization_version": 1,
                },
            )

        counters = audit_classifications(engine)

        self.assertEqual(counters["status"]["CLASSIFIED"], 1)
        self.assertEqual(counters["status"]["MISSING_DATA"], 1)
        self.assertEqual(counters["heading"]["8703"], 1)
        self.assertEqual(counters["missing_field"]["is_special_purpose"], 1)
        engine.dispose()
        database.drop()


if __name__ == "__main__":
    unittest.main()
