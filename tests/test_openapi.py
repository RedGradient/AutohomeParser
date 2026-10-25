from __future__ import annotations

import unittest

from autohome.api.app import create_app


class OpenApiSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app(
            "sqlite+aiosqlite:///:memory:",
            api_username="test-user",
            api_password="test-password",
            jwt_secret="test-jwt-secret-longer-than-thirty-two-bytes",
        )
        cls.schema = app.openapi()

    def test_swagger_uses_documented_pydantic_schemas(self):
        schema = self.schema
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertIn("- производители;", schema["info"]["description"])
        self.assertIn("- фотографии.", schema["info"]["description"])
        self.assertIn("ввозную таможенную пошлину", schema["info"]["description"])
        self.assertIn("утилизационный сбор", schema["info"]["description"])
        self.assertEqual(
            schema["paths"]["/api/v1/customs-calculations"]["get"]["summary"],
            "Получить актуальные таможенные расчёты",
        )
        customs_parameters = {
            item["name"]: item
            for item in schema["paths"]["/api/v1/customs-calculations"]["get"][
                "parameters"
            ]
        }
        self.assertNotIn("status", customs_parameters)
        self.assertNotIn("calculation_date_from", customs_parameters)
        self.assertNotIn("calculation_date_to", customs_parameters)
        calculation_schema = schema["components"]["schemas"][
            "CustomsCalculationResponse"
        ]
        self.assertIn("актуальный сценарий", calculation_schema["description"].lower())
        self.assertNotIn("status", calculation_schema["properties"])
        self.assertIn(
            "/api/v1/series/{series_id}/modifications",
            schema["paths"],
        )
        self.assertEqual(
            schema["paths"]["/api/v1/specs"]["get"]["security"],
            [{"JWT Bearer": []}],
        )
        self.assertNotIn("security", schema["paths"]["/api/v1/auth/token"]["post"])
        self.assertEqual(
            schema["components"]["securitySchemes"]["JWT Bearer"]["scheme"],
            "bearer",
        )
        spec_schema = schema["components"]["schemas"]["SpecResponse"]
        self.assertIn("description", spec_schema)
        self.assertNotIn("config_available", spec_schema["properties"])
        self.assertEqual(
            spec_schema["properties"]["state"]["description"],
            "Стадия продаж комплектации.",
        )
        operation = schema["paths"]["/api/v1/specs"]["get"]
        self.assertEqual(
            operation["responses"]["422"]["content"]["application/json"]["schema"][
                "$ref"
            ],
            "#/components/schemas/ErrorResponse",
        )
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"][
                "$ref"
            ],
            "#/components/schemas/SpecPage",
        )
        parameters = {item["name"]: item for item in operation["parameters"]}
        self.assertNotIn("config_available", parameters)
        self.assertIn("effective", parameters["price_type"]["description"])
        self.assertIn("параметром price_type", parameters["price_from"]["description"])
        brand_parameters = {
            item["name"]: item
            for item in schema["paths"]["/api/v1/brands"]["get"]["parameters"]
        }
        self.assertNotIn("price_from", brand_parameters)
        self.assertNotIn("price_to", brand_parameters)
        self.assertEqual(
            brand_parameters["sort"]["schema"]["enum"],
            ["name", "series_count"],
        )
        for path, methods in schema["paths"].items():
            operation = methods.get("get")
            if operation is None:
                continue
            for parameter in operation.get("parameters", []):
                self.assertTrue(
                    parameter.get("description"),
                    f"GET {path}: параметр {parameter['name']} не имеет description",
                )
        for page_name in (
            "BrandPage",
            "ManufacturerPage",
            "SeriesPage",
            "ModificationPage",
            "SpecPage",
            "PhotoPage",
            "CustomsCalculationPage",
        ):
            properties = schema["components"]["schemas"][page_name]["properties"]
            self.assertIn("description", properties["items"])
            self.assertIn("description", properties["pagination"])


if __name__ == "__main__":
    unittest.main()
