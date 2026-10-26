from __future__ import annotations

import unittest

from audit_recycling_fee_commercial_categories import audit_commercial_categories
from autohome.models import Base, Series, Spec, SpecPowertrain, SpecVehicleAttributes
from tests.postgresql import PostgreSQLTestSchema


class RecyclingFeeCommercialCategoriesAuditTests(unittest.TestCase):
    def test_audit_splits_groups_and_reports_missing_inputs_without_writes(self):
        database = PostgreSQLTestSchema().create()
        engine = database.create_engine()
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                Series.__table__.insert(),
                [
                    {"id": 10, "name": "Обычный грузовик", "raw_json": {}},
                    {"id": 20, "name": "Пожарный автомобиль", "raw_json": {}},
                    {"id": 30, "name": "Шасси 4.5 т", "raw_json": {}},
                    {"id": 40, "name": "Автокран", "raw_json": {}},
                ],
            )
            connection.execute(
                Spec.__table__.insert(),
                [
                    {
                        "id": 1,
                        "series_id": 10,
                        "name": "2025",
                        "year": 2025,
                        "raw_json": {},
                    },
                    {
                        "id": 2,
                        "series_id": 20,
                        "name": "2025",
                        "year": 2025,
                        "raw_json": {},
                    },
                    {
                        "id": 3,
                        "series_id": 30,
                        "name": "2025 底盘",
                        "year": None,
                        "raw_json": {},
                    },
                    {
                        "id": 4,
                        "series_id": 40,
                        "name": "2025 автокран",
                        "year": 2025,
                        "raw_json": {},
                    },
                ],
            )
            connection.execute(
                SpecPowertrain.__table__.insert(),
                [
                    {
                        "spec_id": 1,
                        "series_id": 10,
                        "energy_type": "DIESEL",
                        "is_complete": True,
                        "missing_fields_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 2,
                        "series_id": 20,
                        "energy_type": "DIESEL",
                        "is_complete": True,
                        "missing_fields_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 4,
                        "series_id": 40,
                        "energy_type": "DIESEL",
                        "is_complete": True,
                        "missing_fields_json": [],
                        "normalization_version": 1,
                    },
                ],
            )
            connection.execute(
                SpecVehicleAttributes.__table__.insert(),
                [
                    {
                        "spec_id": 1,
                        "series_id": 10,
                        "vehicle_technical_category": "N1",
                        "gross_mass_kg": 3500,
                        "is_special_purpose": False,
                        "vehicle_purpose_type": None,
                        "inference_flags_json": None,
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 2,
                        "series_id": 20,
                        "vehicle_technical_category": "N2",
                        "gross_mass_kg": 8000,
                        "is_special_purpose": True,
                        "vehicle_purpose_type": "FIRE_FIGHTING",
                        "inference_flags_json": ["INFERRED_INPUTS_USED"],
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 3,
                        "series_id": 30,
                        "vehicle_technical_category": "N2",
                        "gross_mass_kg": 4500,
                        "is_special_purpose": False,
                        "vehicle_purpose_type": None,
                        "inference_flags_json": None,
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 4,
                        "series_id": 40,
                        "vehicle_technical_category": None,
                        "gross_mass_kg": 18000,
                        "is_special_purpose": True,
                        "vehicle_purpose_type": "MOBILE_CRANE",
                        "inference_flags_json": ["INFERRED_INPUTS_USED"],
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                ],
            )

        counters = audit_commercial_categories(engine)

        self.assertEqual(counters["category"], {"N2": 2, "N1": 1, "NULL": 1})
        self.assertEqual(counters["vehicle_group"]["ORDINARY"], 1)
        self.assertEqual(counters["vehicle_group"]["SPECIAL_PURPOSE"], 2)
        self.assertEqual(counters["vehicle_group"]["CHASSIS_CANDIDATE"], 1)
        self.assertEqual(counters["readiness"]["READY"], 2)
        self.assertEqual(counters["missing_field"]["model_year"], 1)
        self.assertEqual(counters["missing_field"]["energy_type"], 1)
        self.assertEqual(counters["missing_field"]["vehicle_technical_category"], 1)
        self.assertEqual(counters["purpose_type"]["FIRE_FIGHTING"], 1)
        self.assertEqual(counters["category_provenance"]["INFERRED"], 2)
        engine.dispose()
        database.drop()


if __name__ == "__main__":
    unittest.main()
