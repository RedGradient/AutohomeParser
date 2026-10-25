from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

from autohome.api.app import create_app
from autohome.api.auth import create_access_token
from autohome.models import (
    Base,
    Brand,
    BrandManufacturer,
    CustomsCalculation,
    CustomsPaymentResult,
    Manufacturer,
    Modification,
    Series,
    SeriesGalleryColor,
    SeriesPhoto,
    SeriesPhotoColor,
    Spec,
    SpecPowertrain,
)


class CatalogApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "api.sqlite3"
        self.username = "test-user"
        self.password = "test-password"
        self.app = create_app(
            f"sqlite:///{database_path}",
            api_username=self.username,
            api_password=self.password,
            jwt_secret="test-jwt-secret-longer-than-thirty-two-bytes",
        )
        async with self.app.state.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.app.state.session_factory() as session:
            session.add(Brand(id=1, name="Test Brand", raw_json={}))
            session.add(Manufacturer(id=2, name="Test Manufacturer", raw_json={}))
            session.add(BrandManufacturer(brand_id=1, manufacturer_id=2, position=0))
            session.add(
                Series(
                    id=10,
                    brand_id=1,
                    manufacturer_id=2,
                    name="Test Series",
                    state=20,
                    spec_count=2,
                    raw_json={},
                )
            )
            session.add_all(
                [
                    Modification(
                        id=100,
                        modification_key="test-100",
                        series_id=10,
                        model_year=2026,
                        name="Electric AWD",
                        energy_type="BEV",
                        drive_type="AWD",
                        is_complete=True,
                        spec_count=1,
                        normalization_version=1,
                    ),
                    Modification(
                        id=101,
                        modification_key="test-101",
                        series_id=10,
                        model_year=2025,
                        name="Petrol FWD",
                        energy_type="GASOLINE",
                        drive_type="FWD",
                        is_complete=True,
                        spec_count=1,
                        normalization_version=1,
                    ),
                ]
            )
            session.add_all(
                [
                    CustomsCalculation(
                        id=900,
                        spec_id=1000,
                        importer_type="INDIVIDUAL",
                        calculation_date=date(2026, 10, 1),
                        rules_version="test-v1",
                        price_source="GUIDE",
                        classification_status="CLASSIFIED",
                        status="CALCULATED",
                        input_snapshot_json={},
                        warnings_json=[],
                    ),
                    CustomsCalculation(
                        id=901,
                        spec_id=1001,
                        importer_type="INDIVIDUAL",
                        calculation_date=date(2026, 10, 1),
                        rules_version="test-v1",
                        price_source="GUIDE",
                        classification_status="CLASSIFIED",
                        status="PARTIAL",
                        input_snapshot_json={},
                        warnings_json=[],
                    ),
                ]
            )
            session.add_all(
                [
                    CustomsPaymentResult(
                        calculation_id=900,
                        payment_type="CUSTOMS_FEE",
                        amount_rub=Decimal("4924.00"),
                        status="CALCULATED",
                        rule_code="TEST_RULE",
                        details_json={
                            "source": "https://example.test/rule",
                            "field_labels": {"source": "Нормативный источник"},
                        },
                    ),
                    CustomsPaymentResult(
                        calculation_id=900,
                        payment_type="IMPORT_DUTY",
                        amount_rub=Decimal("100000.00"),
                        status="CALCULATED",
                        rule_code="TEST_RULE",
                        details_json={},
                    ),
                    CustomsPaymentResult(
                        calculation_id=900,
                        payment_type="RECYCLING_FEE",
                        amount_rub=Decimal("3400.00"),
                        status="CALCULATED",
                        rule_code="TEST_RULE",
                        details_json={},
                    ),
                    CustomsPaymentResult(
                        calculation_id=900,
                        payment_type="EXCISE",
                        amount_rub=None,
                        status="NOT_APPLICABLE",
                        rule_code="EXCISE_NOT_APPLICABLE_PERSONAL_USE",
                        details_json={"reason": "PERSONAL_USE"},
                    ),
                    CustomsPaymentResult(
                        calculation_id=900,
                        payment_type="VAT",
                        amount_rub=None,
                        status="NOT_APPLICABLE",
                        rule_code="VAT_NOT_APPLICABLE_PERSONAL_USE",
                        details_json={"reason": "PERSONAL_USE"},
                    ),
                    CustomsPaymentResult(
                        calculation_id=901,
                        payment_type="CUSTOMS_FEE",
                        amount_rub=Decimal("4924.00"),
                        status="CALCULATED",
                        rule_code="TEST_RULE",
                        details_json={},
                    ),
                ]
            )
            session.add_all(
                [
                    Spec(
                        id=1000,
                        series_id=10,
                        modification_id=100,
                        name="Premium",
                        year=2026,
                        state=20,
                        guide_price_yuan=Decimal(200000),
                        raw_json={},
                    ),
                    Spec(
                        id=1001,
                        series_id=10,
                        modification_id=101,
                        name="Comfort",
                        year=2025,
                        state=40,
                        guide_price_yuan=Decimal(120000),
                        raw_json={},
                    ),
                ]
            )
            session.add_all(
                [
                    SpecPowertrain(
                        spec_id=1000,
                        series_id=10,
                        model_year=2026,
                        energy_type="BEV",
                        drive_type="AWD",
                        is_complete=True,
                        missing_fields_json=[],
                        normalization_version=1,
                    ),
                    SpecPowertrain(
                        spec_id=1001,
                        series_id=10,
                        model_year=2025,
                        energy_type="GASOLINE",
                        drive_type="FWD",
                        is_complete=True,
                        missing_fields_json=[],
                        normalization_version=1,
                    ),
                ]
            )
            session.add(
                SeriesGalleryColor(
                    series_id=10,
                    color_scope="exterior",
                    color_id=7,
                    name="White",
                    color_values=["#ffffff"],
                    picture_count=1,
                    gallery_url="https://example.test/gallery",
                    raw_json={},
                )
            )
            session.add(
                SeriesPhoto(
                    id=700,
                    series_id=10,
                    category_id=1,
                    category_name="Exterior",
                    image_url="https://example.test/photo.jpg",
                    page_url="https://example.test/photo",
                    raw_json={},
                )
            )
            session.add(
                SeriesPhoto(
                    id=701,
                    series_id=10,
                    category_id=53,
                    category_name="Официальные изображения",
                    image_url="https://example.test/official.jpg",
                    page_url="https://example.test/official",
                    raw_json={},
                )
            )
            session.add(
                SeriesPhotoColor(
                    photo_id=700,
                    series_id=10,
                    color_scope="exterior",
                    color_id=7,
                )
            )
            await session.commit()
        token = create_access_token(self.username, self.app.state.auth_settings)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.app.state.engine.dispose()
        self.temp_dir.cleanup()

    async def test_protected_endpoint_rejects_missing_token(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/brands")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INVALID_TOKEN")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    async def test_protected_endpoint_rejects_malformed_token(self):
        response = await self.client.get(
            "/api/v1/brands", headers={"Authorization": "Bearer invalid.jwt.token"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INVALID_TOKEN")

    async def test_token_endpoint_issues_working_jwt(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": self.username, "password": self.password},
            )
            token = token_response.json()["access_token"]
            protected_response = await client.get(
                "/api/v1/brands",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(token_response.json()["token_type"], "bearer")
        self.assertEqual(protected_response.status_code, 200)

    async def test_brand_responses_do_not_include_price(self):
        list_response = await self.client.get("/api/v1/brands")
        detail_response = await self.client.get("/api/v1/brands/1")

        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn("price", list_response.json()["items"][0])
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotIn("price", detail_response.json())

    async def test_manufacturers_support_search_and_brand_filter(self):
        response = await self.client.get(
            "/api/v1/manufacturers",
            params={"q": "manufacturer", "brand_id": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [{"id": 2, "name": "Test Manufacturer"}],
        )

        detail_response = await self.client.get("/api/v1/manufacturers/2")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.json(),
            {"id": 2, "name": "Test Manufacturer"},
        )

    async def test_series_uses_normalized_state(self):
        response = await self.client.get("/api/v1/series/10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "CURRENT")

        filtered_response = await self.client.get(
            "/api/v1/series", params={"state": "CURRENT"}
        )
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in filtered_response.json()["items"]],
            [10],
        )

    async def test_specs_use_normalized_state(self):
        detail_response = await self.client.get("/api/v1/specs/1000")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["state"], "CURRENT")

        filtered_response = await self.client.get(
            "/api/v1/specs", params={"state": "DISCONTINUED"}
        )
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in filtered_response.json()["items"]],
            [1001],
        )

    async def test_customs_response_hides_legacy_field_labels(self):
        response = await self.client.get("/api/v1/customs-calculations/900")

        self.assertEqual(response.status_code, 200)
        details = response.json()["payments"][0]["details"]
        self.assertNotIn("field_labels", details)
        self.assertEqual(details["source"], "https://example.test/rule")
        self.assertEqual(response.json()["total_rub"], "108324.00")
        self.assertTrue(response.json()["is_total_complete"])
        excise = next(
            item
            for item in response.json()["payments"]
            if item["payment_type"] == "EXCISE"
        )
        self.assertEqual(excise["status"], "NOT_APPLICABLE")
        self.assertIsNone(excise["amount_rub"])
        vat = next(
            item
            for item in response.json()["payments"]
            if item["payment_type"] == "VAT"
        )
        self.assertEqual(vat["status"], "NOT_APPLICABLE")
        self.assertIsNone(vat["amount_rub"])

    async def test_customs_response_has_no_total_for_incomplete_payments(self):
        response = await self.client.get("/api/v1/customs-calculations/901")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["total_rub"])
        self.assertFalse(response.json()["is_total_complete"])

    async def test_token_endpoint_rejects_invalid_credentials(self):
        response = await self.client.post(
            "/api/v1/auth/token",
            json={"username": self.username, "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INVALID_CREDENTIALS")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    async def test_health_endpoint_is_protected(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        self.assertEqual(response.status_code, 401)

    async def test_docs_endpoint_is_available(self):
        self.assertEqual((await self.client.get("/docs")).status_code, 200)

    async def test_modifications_are_filtered_by_series(self):
        response = await self.client.get("/api/v1/series/10/modifications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [100, 101])
        self.assertTrue(
            all("is_complete" not in item for item in response.json()["items"])
        )

        schema = (await self.client.get("/openapi.json")).json()
        parameters = schema["paths"]["/api/v1/modifications"]["get"]["parameters"]
        self.assertNotIn("is_complete", {item["name"] for item in parameters})

    async def test_specs_support_price_range_and_pagination(self):
        response = await self.client.get(
            "/api/v1/specs",
            params={"price_from": "150000", "price_to": "250000", "limit": 1},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["id"] for item in body["items"]], [1000])
        self.assertFalse(body["pagination"]["has_more"])
        self.assertEqual(body["pagination"]["offset"], 0)
        self.assertIsNone(body["pagination"]["total"])

        next_page = await self.client.get(
            "/api/v1/specs",
            params={"limit": 1, "offset": 1, "include_total": True},
        )
        self.assertEqual(next_page.status_code, 200)
        self.assertEqual([item["id"] for item in next_page.json()["items"]], [1000])
        self.assertEqual(next_page.json()["pagination"]["offset"], 1)
        self.assertEqual(next_page.json()["pagination"]["total"], 2)
        self.assertFalse(next_page.json()["pagination"]["has_more"])

        schema = (await self.client.get("/openapi.json")).json()
        parameters = {
            item["name"]
            for item in schema["paths"]["/api/v1/specs"]["get"]["parameters"]
        }
        self.assertIn("offset", parameters)
        self.assertIn("include_total", parameters)
        self.assertNotIn("cursor", parameters)

    async def test_invalid_price_range_returns_domain_error(self):
        response = await self.client.get(
            "/api/v1/specs", params={"price_from": "250000", "price_to": "100000"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_RANGE")

    async def test_photo_color_scope_filter_maps_public_enum_to_database_value(self):
        response = await self.client.get(
            "/api/v1/series/10/photos", params={"color_scope": "EXTERIOR"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [700])
        self.assertEqual(
            response.json()["items"][0]["colors"][0]["color_scope"], "EXTERIOR"
        )
        self.assertNotIn("page_url", response.json()["items"][0])
        self.assertNotIn("series_id", response.json()["items"][0]["colors"][0])

        response = await self.client.get(
            "/api/v1/series/10/photos", params={"color_scope": "exterior"}
        )
        self.assertEqual([item["id"] for item in response.json()["items"]], [700])

    async def test_series_returns_all_official_images(self):
        response = await self.client.get("/api/v1/series/10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["official_images"],
            [
                {
                    "id": 701,
                    "title": None,
                    "image_url": "https://example.test/official.jpg",
                    "thumbnail_url": None,
                }
            ],
        )

    async def test_main_read_routes_are_operational(self):
        urls = (
            "/api/v1/brands",
            "/api/v1/brands/1",
            "/api/v1/manufacturers",
            "/api/v1/manufacturers/2",
            "/api/v1/series",
            "/api/v1/series?sort=price",
            "/api/v1/series?sort=year&order=desc",
            "/api/v1/series/10",
            "/api/v1/modifications",
            "/api/v1/modifications/100",
            "/api/v1/modifications/100/specs",
            "/api/v1/specs/1000",
            "/api/v1/specs/1000/parameters",
            "/api/v1/series/10/photos",
            "/api/v1/series/10/gallery-colors",
            "/api/v1/customs-calculations",
            "/api/v1/specs/1000/customs-calculations",
        )
        for url in urls:
            with self.subTest(url=url):
                response = await self.client.get(url)
                self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
