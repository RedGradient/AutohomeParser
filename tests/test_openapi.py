from __future__ import annotations

import unittest

from autohome.api.app import create_app


class OpenApiSchemaTests(unittest.TestCase):
    EXPECTED_OPERATIONS = {
        ("POST", "/api/v1/auth/token"),
        ("GET", "/api/v1/brands"),
        ("GET", "/api/v1/brands/{brand_id}"),
        ("GET", "/api/v1/manufacturers"),
        ("GET", "/api/v1/manufacturers/{manufacturer_id}"),
        ("GET", "/api/v1/series"),
        ("GET", "/api/v1/series/{series_id}"),
        ("GET", "/api/v1/modifications"),
        ("GET", "/api/v1/series/{series_id}/modifications"),
        ("GET", "/api/v1/modifications/{modification_id}"),
        ("GET", "/api/v1/specs"),
        ("GET", "/api/v1/modifications/{modification_id}/specs"),
        ("GET", "/api/v1/specs/{spec_id}"),
        ("GET", "/api/v1/specs/{spec_id}/parameters"),
        ("GET", "/api/v1/series/{series_id}/photos"),
        ("GET", "/api/v1/series/{series_id}/gallery-colors"),
        ("GET", "/api/v1/customs-calculations"),
        ("GET", "/api/v1/customs-calculations/{calculation_id}"),
        ("GET", "/api/v1/specs/{spec_id}/customs-calculations"),
    }
    EXPECTED_TAGS = {
        "/api/v1/auth/token": "Auth",
        "/api/v1/brands": "Brands",
        "/api/v1/brands/{brand_id}": "Brands",
        "/api/v1/manufacturers": "Manufacturers",
        "/api/v1/manufacturers/{manufacturer_id}": "Manufacturers",
        "/api/v1/series": "Series",
        "/api/v1/series/{series_id}": "Series",
        "/api/v1/modifications": "Modifications",
        "/api/v1/series/{series_id}/modifications": "Modifications",
        "/api/v1/modifications/{modification_id}": "Modifications",
        "/api/v1/specs": "Specs",
        "/api/v1/modifications/{modification_id}/specs": "Specs",
        "/api/v1/specs/{spec_id}": "Specs",
        "/api/v1/specs/{spec_id}/parameters": "Specs",
        "/api/v1/series/{series_id}/photos": "Series",
        "/api/v1/series/{series_id}/gallery-colors": "Series",
        "/api/v1/customs-calculations": "Customs",
        "/api/v1/customs-calculations/{calculation_id}": "Customs",
        "/api/v1/specs/{spec_id}/customs-calculations": "Customs",
    }

    @classmethod
    def setUpClass(cls):
        app = create_app(
            "postgresql+psycopg://test:test@127.0.0.1:5432/test",
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
        self.assertIn("акциз", schema["info"]["description"])
        self.assertIn("НДС", schema["info"]["description"])
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
        importer_schema = customs_parameters["importer_type"]["schema"]["anyOf"][0]
        self.assertEqual(importer_schema["$ref"], "#/components/schemas/ImporterType")
        self.assertNotIn("status", customs_parameters)
        self.assertNotIn("calculation_date_from", customs_parameters)
        self.assertNotIn("calculation_date_to", customs_parameters)
        spec_customs_parameters = {
            item["name"]: item
            for item in schema["paths"]["/api/v1/specs/{spec_id}/customs-calculations"][
                "get"
            ]["parameters"]
        }
        self.assertNotIn("calculation_date", spec_customs_parameters)
        calculation_schema = schema["components"]["schemas"][
            "CustomsCalculationResponse"
        ]
        self.assertIn("актуальный сценарий", calculation_schema["description"].lower())
        self.assertNotIn("status", calculation_schema["properties"])
        self.assertEqual(
            calculation_schema["properties"]["importer_type"]["$ref"],
            "#/components/schemas/ImporterType",
        )
        payment_schema = schema["components"]["schemas"]["CustomsPaymentResponse"]
        self.assertEqual(
            payment_schema["properties"]["payment_type"]["$ref"],
            "#/components/schemas/CustomsPaymentType",
        )
        self.assertEqual(
            payment_schema["properties"]["status"]["$ref"],
            "#/components/schemas/CalculationStatus",
        )
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

    def test_public_api_operations_have_complete_contract(self):
        """Проверяет состав, документацию и авторизацию публичных операций API."""
        operations = {
            (method.upper(), path): operation
            for path, methods in self.schema["paths"].items()
            for method, operation in methods.items()
            if method in {"get", "post", "put", "patch", "delete"}
        }

        self.assertEqual(set(operations), self.EXPECTED_OPERATIONS)
        for (method, path), operation in operations.items():
            self.assertTrue(operation.get("summary"), f"{method} {path}: нет summary")
            self.assertIn(
                "200", operation["responses"], f"{method} {path}: нет ответа 200"
            )
            if path == "/api/v1/auth/token":
                self.assertNotIn("security", operation)
            else:
                self.assertEqual(
                    operation.get("security"),
                    [{"JWT Bearer": []}],
                    f"{method} {path}: неверная схема авторизации",
                )

    def test_operations_keep_their_swagger_sections_and_unique_ids(self):
        """Фиксирует разделы Swagger и уникальность идентификаторов операций."""
        operations = [
            (path, operation)
            for path, methods in self.schema["paths"].items()
            for method, operation in methods.items()
            if method in {"get", "post", "put", "patch", "delete"}
        ]

        operation_ids = []
        for path, operation in operations:
            self.assertEqual(operation.get("tags"), [self.EXPECTED_TAGS[path]])
            operation_ids.append(operation["operationId"])

        self.assertEqual(len(operation_ids), len(set(operation_ids)))


if __name__ == "__main__":
    unittest.main()
