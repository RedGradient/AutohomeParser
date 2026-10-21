from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from autohome.api.app import create_app
from autohome.models import (
    Base,
    Brand,
    Modification,
    Series,
    SeriesGalleryColor,
    SeriesPhoto,
    SeriesPhotoColor,
    Spec,
    SpecPowertrain,
)


class CatalogApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "api.sqlite3"
        self.app = create_app(f"sqlite:///{database_path}")
        Base.metadata.create_all(self.app.state.engine)
        with Session(self.app.state.engine) as session:
            session.add(Brand(id=1, name="Test Brand", raw_json={}))
            session.add(
                Series(
                    id=10,
                    brand_id=1,
                    name="Test Series",
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
                    Spec(
                        id=1000,
                        series_id=10,
                        modification_id=100,
                        name="Premium",
                        year=2026,
                        guide_price_yuan=Decimal("200000"),
                        raw_json={},
                    ),
                    Spec(
                        id=1001,
                        series_id=10,
                        modification_id=101,
                        name="Comfort",
                        year=2025,
                        guide_price_yuan=Decimal("120000"),
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
            session.commit()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.app.state.engine.dispose()
        self.temp_dir.cleanup()

    async def test_swagger_uses_committed_openapi_specification(self):
        response = await self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["openapi"], "3.1.0")
        self.assertIn("/series/{series_id}/modifications", response.json()["paths"])
        self.assertEqual((await self.client.get("/docs")).status_code, 200)

    async def test_modifications_are_filtered_by_series(self):
        response = await self.client.get("/api/v1/series/10/modifications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [100, 101])

    async def test_specs_support_price_range_and_pagination(self):
        response = await self.client.get(
            "/api/v1/specs",
            params={"price_from": "150000", "price_to": "250000", "limit": 1},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["id"] for item in body["items"]], [1000])
        self.assertFalse(body["pagination"]["has_more"])

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
