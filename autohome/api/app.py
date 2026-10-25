from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi import Path as ApiPath
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.auth import AuthSettings
from autohome.api.common import (
    EXPECTED_CUSTOMS_PAYMENT_TYPES,
    LEGACY_CUSTOMS_PAYMENT_TYPE_SETS,
)
from autohome.api.common import (
    money as _money,
)
from autohome.api.common import (
    public_payment_details as _public_payment_details,
)
from autohome.api.dependencies import authenticated_user_dependency
from autohome.api.errors import (
    not_found as _not_found,
)
from autohome.api.errors import (
    register_exception_handlers,
)
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION
from autohome.api.pagination import page as _page
from autohome.api.routers.auth import create_auth_router
from autohome.api.routers.brands import create_brands_router
from autohome.api.routers.manufacturers import create_manufacturers_router
from autohome.api.routers.modifications import create_modifications_router
from autohome.api.routers.series import create_series_router
from autohome.api.routers.specs import create_specs_router
from autohome.api.schemas import (
    CustomsCalculationPage,
    CustomsCalculationResponse,
    ErrorResponse,
    GalleryColorsResponse,
    ImporterType,
    PhotoPage,
)
from autohome.api.session import DatabaseSessionManager
from autohome.models import (
    CustomsCalculation,
    CustomsPaymentResult,
    Series,
    SeriesGalleryColor,
    SeriesPhoto,
    SeriesPhotoColor,
    Spec,
)


def create_app(
    database_url: str | None = None,
    *,
    api_username: str | None = None,
    api_password: str | None = None,
    jwt_secret: str | None = None,
    jwt_ttl_seconds: int | None = None,
) -> FastAPI:
    auth_settings = AuthSettings.from_environment(
        username=api_username,
        password=api_password,
        secret=jwt_secret,
        access_token_ttl_seconds=jwt_ttl_seconds,
    )
    database = DatabaseSessionManager(database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Освободить ресурсы приложения при его остановке."""
        try:
            yield
        finally:
            await database.engine.dispose()

    application = FastAPI(
        title="Autohome Catalog API",
        description=(
            "API чтения каталога Autohome. Доступные данные:\n\n"
            "- бренды;\n"
            "- производители;\n"
            "- серии;\n"
            "- комплектации;\n"
            "- технические модификации;\n"
            "- характеристики;\n"
            "- фотографии.\n\n"
            "API также возвращает предварительно рассчитанные таможенные платежи: "
            "ввозную таможенную пошлину, таможенный сбор, утилизационный сбор, "
            "акциз и НДС."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Auth", "description": "Получение JWT для доступа к API."},
            {"name": "Brands", "description": "Бренды автомобилей."},
            {"name": "Manufacturers", "description": "Производители автомобилей."},
            {"name": "Series", "description": "Серии и их изображения."},
            {
                "name": "Modifications",
                "description": "Нормализованные технические модификации.",
            },
            {"name": "Specs", "description": "Комплектации и полные характеристики."},
            {
                "name": "Customs",
                "description": "Сохранённые расчёты таможенных платежей.",
            },
        ],
        responses={
            400: {
                "model": ErrorResponse,
                "description": "Некорректный фильтр или диапазон.",
            },
            401: {
                "model": ErrorResponse,
                "description": "JWT отсутствует, истёк или недействителен.",
            },
            404: {
                "model": ErrorResponse,
                "description": "Запрошенная сущность не найдена.",
            },
            422: {
                "model": ErrorResponse,
                "description": "Параметры или тело запроса не прошли валидацию.",
            },
        },
    )
    application.state.database = database
    application.state.engine = database.engine
    application.state.session_factory = database.session_factory
    application.state.auth_settings = auth_settings
    get_session = database.get_session

    require_authenticated_user = authenticated_user_dependency(auth_settings)
    protected_router = APIRouter(dependencies=[Depends(require_authenticated_user)])
    register_exception_handlers(application)
    application.include_router(create_auth_router(auth_settings))
    application.include_router(
        create_brands_router(get_session, require_authenticated_user)
    )
    application.include_router(
        create_manufacturers_router(get_session, require_authenticated_user)
    )
    application.include_router(
        create_series_router(get_session, require_authenticated_user)
    )
    application.include_router(
        create_modifications_router(get_session, require_authenticated_user)
    )
    application.include_router(
        create_specs_router(get_session, require_authenticated_user)
    )

    @application.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @protected_router.get(
        "/api/v1/series/{series_id}/photos",
        response_model=PhotoPage,
        tags=["Series"],
        summary="Получить фотографии серии",
    )
    async def photos(
        series_id: int = ApiPath(description="Идентификатор серии."),
        spec_id: int | None = Query(
            None, description="Оставить фотографии указанной комплектации."
        ),
        category_id: int | None = Query(
            None, description="Оставить фотографии указанной категории."
        ),
        color_scope: str | None = Query(
            None, description="Область цвета: EXTERIOR или INTERIOR."
        ),
        color_id: int | None = Query(None, description="Идентификатор цвета."),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Series, series_id) is None:
            raise _not_found("Series")
        statement = select(SeriesPhoto).where(SeriesPhoto.series_id == series_id)
        if spec_id is not None:
            statement = statement.where(SeriesPhoto.spec_id == spec_id)
        if category_id is not None:
            statement = statement.where(SeriesPhoto.category_id == category_id)
        if color_scope is not None or color_id is not None:
            color_match = select(SeriesPhotoColor.photo_id).where(
                SeriesPhotoColor.photo_id == SeriesPhoto.id
            )
            if color_scope is not None:
                color_match = color_match.where(
                    func.lower(SeriesPhotoColor.color_scope) == color_scope.lower()
                )
            if color_id is not None:
                color_match = color_match.where(SeriesPhotoColor.color_id == color_id)
            statement = statement.where(exists(color_match))
        statement = statement.order_by(SeriesPhoto.id)
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        photos_list = [row[0] for row in rows]
        ids = [photo.id for photo in photos_list]
        color_rows = (
            (
                await session.execute(
                    select(SeriesPhotoColor, SeriesGalleryColor)
                    .join(
                        SeriesGalleryColor,
                        and_(
                            SeriesGalleryColor.series_id == SeriesPhotoColor.series_id,
                            SeriesGalleryColor.color_scope
                            == SeriesPhotoColor.color_scope,
                            SeriesGalleryColor.color_id == SeriesPhotoColor.color_id,
                        ),
                    )
                    .where(SeriesPhotoColor.photo_id.in_(ids))
                )
            ).all()
            if ids
            else []
        )
        by_photo: dict[int, list] = {}
        for link, color in color_rows:
            by_photo.setdefault(link.photo_id, []).append(
                {
                    "color_scope": color.color_scope.upper(),
                    "color_id": color.color_id,
                    "name": color.name,
                    "color_values": color.color_values,
                    "picture_count": color.picture_count,
                    "gallery_url": color.gallery_url,
                }
            )
        items = [
            {
                "id": photo.id,
                "series_id": photo.series_id,
                "spec_id": photo.spec_id,
                "category_id": photo.category_id,
                "category_name": photo.category_name,
                "title": photo.title,
                "image_url": photo.image_url,
                "thumbnail_url": photo.thumbnail_url,
                "colors": by_photo.get(photo.id, []),
            }
            for photo in photos_list
        ]
        return {"items": items, "pagination": pagination}

    @protected_router.get(
        "/api/v1/series/{series_id}/gallery-colors",
        response_model=GalleryColorsResponse,
        tags=["Series"],
        summary="Получить цвета галереи",
    )
    async def gallery_colors(
        series_id: int = ApiPath(description="Идентификатор серии."),
        color_scope: str | None = Query(
            None, description="Область цвета: EXTERIOR или INTERIOR."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Series, series_id) is None:
            raise _not_found("Series")
        statement = select(SeriesGalleryColor).where(
            SeriesGalleryColor.series_id == series_id
        )
        if color_scope is not None:
            statement = statement.where(
                func.lower(SeriesGalleryColor.color_scope) == color_scope.lower()
            )
        values = await session.execute(
            statement.order_by(SeriesGalleryColor.color_scope, SeriesGalleryColor.name)
        )
        values = values.scalars()
        return {
            "items": [
                {
                    "series_id": item.series_id,
                    "color_scope": item.color_scope.upper(),
                    "color_id": item.color_id,
                    "name": item.name,
                    "color_values": item.color_values,
                    "picture_count": item.picture_count,
                    "gallery_url": item.gallery_url,
                }
                for item in values
            ]
        }

    async def calculation_payments(
        session: AsyncSession, calculation_ids: list[int]
    ) -> dict[int, list[CustomsPaymentResult]]:
        """Загрузить платежи нескольких расчётов одним упорядоченным запросом."""
        if not calculation_ids:
            return {}
        values = (
            await session.execute(
                select(CustomsPaymentResult)
                .where(CustomsPaymentResult.calculation_id.in_(calculation_ids))
                .order_by(
                    CustomsPaymentResult.calculation_id,
                    CustomsPaymentResult.payment_type,
                )
            )
        ).scalars()
        grouped = {calculation_id: [] for calculation_id in calculation_ids}
        for payment in values:
            grouped[payment.calculation_id].append(payment)
        return grouped

    def calculation_payload(
        calculation: CustomsCalculation,
        payments: list[CustomsPaymentResult],
    ):
        """Сформировать публичный расчёт из заранее загруженных платежей."""
        payment_types = {item.payment_type for item in payments}
        expected_types_present = payment_types in {
            frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES),
            *LEGACY_CUSTOMS_PAYMENT_TYPE_SETS,
        }
        complete = expected_types_present and all(
            (item.status == "CALCULATED" and item.amount_rub is not None)
            or (item.status == "NOT_APPLICABLE" and item.amount_rub is None)
            for item in payments
        )
        amounts = (
            [
                item.amount_rub
                for item in payments
                if item.status == "CALCULATED" and item.amount_rub is not None
            ]
            if complete
            else []
        )
        return {
            "id": calculation.id,
            "spec_id": calculation.spec_id,
            "importer_type": calculation.importer_type,
            "calculation_date": calculation.calculation_date,
            "rules_version": calculation.rules_version,
            "price_source": calculation.price_source,
            "vehicle_price_cny": _money(calculation.vehicle_price_cny),
            "customs_value_rub": _money(calculation.customs_value_rub),
            "energy_type": calculation.energy_type,
            "body_type": calculation.body_type,
            "engine_displacement_ml": calculation.engine_displacement_ml,
            "tnved_code": calculation.tnved_code,
            "classification_status": calculation.classification_status,
            "warnings": calculation.warnings_json,
            "payments": [
                {
                    "payment_type": item.payment_type,
                    "amount_rub": _money(item.amount_rub),
                    "status": item.status,
                    "rule_code": item.rule_code,
                    "details": _public_payment_details(item.details_json),
                }
                for item in payments
            ],
            "total_rub": _money(sum(amounts, Decimal(0))) if complete else None,
            "is_total_complete": complete,
        }

    async def calculations_impl(
        session: AsyncSession,
        limit: int,
        offset: int,
        include_total: bool,
        spec_id=None,
        brand_id=None,
        series_id=None,
        importer_type=None,
    ):
        statement = (
            select(CustomsCalculation)
            .join(Spec, Spec.id == CustomsCalculation.spec_id)
            .join(Series, Series.id == Spec.series_id)
        )
        filters = []
        for column, value in (
            (CustomsCalculation.spec_id, spec_id),
            (Series.brand_id, brand_id),
            (Spec.series_id, series_id),
            (CustomsCalculation.importer_type, importer_type),
        ):
            if value is not None:
                filters.append(column == value)
        statement = statement.where(*filters).order_by(
            CustomsCalculation.calculation_date.desc(), CustomsCalculation.id.desc()
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        calculations = [row[0] for row in rows]
        payments = await calculation_payments(
            session, [calculation.id for calculation in calculations]
        )
        return {
            "items": [
                calculation_payload(
                    calculation,
                    payments.get(calculation.id, []),
                )
                for calculation in calculations
            ],
            "pagination": pagination,
        }

    @protected_router.get(
        "/api/v1/customs-calculations",
        response_model=CustomsCalculationPage,
        tags=["Customs"],
        summary="Получить актуальные таможенные расчёты",
    )
    async def calculations(
        spec_id: int | None = Query(None, description="Идентификатор комплектации."),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        series_id: int | None = Query(None, description="Идентификатор серии."),
        importer_type: ImporterType | None = Query(None, description="Тип импортёра."),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        return await calculations_impl(
            session,
            limit,
            offset,
            include_total,
            spec_id=spec_id,
            brand_id=brand_id,
            series_id=series_id,
            importer_type=importer_type,
        )

    @protected_router.get(
        "/api/v1/customs-calculations/{calculation_id}",
        response_model=CustomsCalculationResponse,
        tags=["Customs"],
        summary="Получить актуальный таможенный расчёт",
    )
    async def calculation_detail(
        calculation_id: int = ApiPath(
            description="Идентификатор сценария таможенного расчёта."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        item = await session.get(CustomsCalculation, calculation_id)
        if item is None:
            raise _not_found("Customs calculation")
        payments = await calculation_payments(session, [item.id])
        return calculation_payload(item, payments.get(item.id, []))

    @protected_router.get(
        "/api/v1/specs/{spec_id}/customs-calculations",
        response_model=CustomsCalculationPage,
        tags=["Customs"],
        summary="Получить актуальные таможенные расчёты комплектации",
    )
    async def spec_calculations(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        importer_type: ImporterType | None = Query(None, description="Тип импортёра."),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Spec, spec_id) is None:
            raise _not_found("Spec")
        return await calculations_impl(
            session,
            limit,
            offset,
            include_total,
            spec_id=spec_id,
            importer_type=importer_type,
        )

    application.include_router(protected_router)
    return application
