from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Security
from fastapi import Path as ApiPath
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.auth import (
    AuthSettings,
    authenticate_bearer,
    create_access_token,
    credentials_are_valid,
)
from autohome.api.schemas import (
    BrandPage,
    BrandResponse,
    CustomsCalculationPage,
    CustomsCalculationResponse,
    ErrorResponse,
    GalleryColorsResponse,
    ImporterType,
    ManufacturerPage,
    ManufacturerResponse,
    ModificationPage,
    ModificationResponse,
    ParameterGroupsResponse,
    PhotoPage,
    SeriesPage,
    SeriesResponse,
    SeriesState,
    SpecDetailResponse,
    SpecPage,
    TokenRequest,
    TokenResponse,
)
from autohome.api.session import DatabaseSessionManager
from autohome.models import (
    Brand,
    BrandManufacturer,
    CustomsCalculation,
    CustomsPaymentResult,
    Manufacturer,
    Modification,
    ParameterDefinition,
    ParameterGroup,
    ParameterSection,
    ParameterSubitem,
    Series,
    SeriesGalleryColor,
    SeriesPhoto,
    SeriesPhotoColor,
    Spec,
    SpecParameter,
    SpecPowertrain,
    SpecVehicleAttributes,
)

PriceType = Literal["effective", "guide", "dealer"]
SortOrder = Literal["asc", "desc"]
SERIES_STATE_CODES = {
    SeriesState.UPCOMING: (10,),
    SeriesState.CURRENT: (20, 30),
    SeriesState.DISCONTINUED: (0, 40),
}
KNOWN_SERIES_STATE_CODES = tuple(
    code for codes in SERIES_STATE_CODES.values() for code in codes
)
SPEC_STATE_CODES = {
    SeriesState.UPCOMING: (0, 10),
    SeriesState.CURRENT: (20, 30),
    SeriesState.DISCONTINUED: (40,),
}
KNOWN_SPEC_STATE_CODES = tuple(
    code for codes in SPEC_STATE_CODES.values() for code in codes
)
PRICE_FROM_DESCRIPTION = (
    "Минимальная цена в CNY. Тип цены задаётся параметром price_type. "
    "Записи без цены выбранного типа не возвращаются."
)
PRICE_TO_DESCRIPTION = (
    "Максимальная цена в CNY. Тип цены задаётся параметром price_type. "
    "Записи без цены выбранного типа не возвращаются."
)
PRICE_TYPE_DESCRIPTION = (
    "Тип цены: effective — рекомендованная или дилерская при её отсутствии; "
    "guide — рекомендованная; dealer — дилерская."
)
EXPECTED_CUSTOMS_PAYMENT_TYPES = {
    "IMPORT_DUTY",
    "CUSTOMS_FEE",
    "RECYCLING_FEE",
    "EXCISE",
    "VAT",
}
LEGACY_CUSTOMS_PAYMENT_TYPE_SETS = {
    frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES - {"VAT"}),
    frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES - {"VAT", "EXCISE"}),
}
INCLUDE_TOTAL_DESCRIPTION = (
    "Если true, возвращает общее количество найденных записей. "
    "Может увеличить время ответа."
)


def _money(value: Decimal | None) -> str | None:
    return format(value, ".2f") if value is not None else None


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _series_state(value: int | None) -> SeriesState:
    """Преобразовать исходный код Autohome в публичную стадию продаж."""
    for state, codes in SERIES_STATE_CODES.items():
        if value in codes:
            return state
    return SeriesState.UNKNOWN


def _spec_state(value: int | None) -> SeriesState:
    """Преобразовать исходный код комплектации в публичную стадию продаж."""
    for state, codes in SPEC_STATE_CODES.items():
        if value in codes:
            return state
    return SeriesState.UNKNOWN


def _public_payment_details(details: dict[str, Any]) -> dict[str, Any]:
    """Исключить устаревшие интерфейсные подписи из деталей платежа."""
    return {key: value for key, value in details.items() if key != "field_labels"}


def _effective_price():
    return case(
        (Spec.guide_price_yuan > 0, Spec.guide_price_yuan),
        (Spec.dealer_price_yuan > 0, Spec.dealer_price_yuan),
        else_=None,
    )


def _price_column(price_type: PriceType):
    return {
        "effective": _effective_price(),
        "guide": Spec.guide_price_yuan,
        "dealer": Spec.dealer_price_yuan,
    }[price_type]


def _contains_pattern(value: str) -> str:
    """Экранировать пользовательский текст для поиска через SQL LIKE."""
    escaped = value.lower().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _page(
    session: AsyncSession,
    statement,
    limit: int,
    offset: int,
    include_total: bool,
):
    total = None
    if include_total:
        count_statement = select(func.count()).select_from(
            statement.order_by(None).subquery()
        )
        total = int(await session.scalar(count_statement) or 0)
    rows = (await session.execute(statement.offset(offset).limit(limit + 1))).all()
    has_more = len(rows) > limit
    return rows[:limit], {
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": has_more,
    }


def _check_range(minimum, maximum, name: str) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(
            400,
            detail={
                "code": "INVALID_RANGE",
                "message": f"{name}_from must not exceed {name}_to",
            },
        )


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        404, detail={"code": "NOT_FOUND", "message": f"{resource} not found"}
    )


def _brand_ref(brand: Brand | None):
    return {"id": brand.id, "name": brand.name} if brand else None


def _series_ref(series: Series | None):
    return {"id": series.id, "name": series.name} if series else None


def _manufacturer_ref(manufacturer: Manufacturer | None):
    return {"id": manufacturer.id, "name": manufacturer.name} if manufacturer else None


def _price_payload(spec: Spec):
    if spec.guide_price_yuan is not None and spec.guide_price_yuan > 0:
        effective, source = spec.guide_price_yuan, "GUIDE"
    elif spec.dealer_price_yuan is not None and spec.dealer_price_yuan > 0:
        effective, source = spec.dealer_price_yuan, "DEALER"
    else:
        effective, source = None, "MISSING"
    return {
        "guide_cny": _money(spec.guide_price_yuan),
        "dealer_cny": _money(spec.dealer_price_yuan),
        "discount_cny": _money(spec.discount_yuan),
        "effective_cny": _money(effective),
        "source": source,
    }


def _powertrain_payload(item: SpecPowertrain | None):
    if item is None:
        return None
    return {
        "energy_type": item.energy_type,
        "engine_summary": item.engine_summary,
        "engine_displacement_ml": item.engine_displacement_ml,
        "engine_power_kw": _decimal(item.engine_power_kw),
        "engine_power_hp": _decimal(item.engine_power_hp),
        "maximum_power_kw": _decimal(item.maximum_power_kw),
        "transmission_summary": item.transmission_summary,
        "transmission_type": item.transmission_type,
        "drive_type": item.drive_type,
        "motor_total_power_kw": _decimal(item.motor_total_power_kw),
        "motor_total_power_hp": _decimal(item.motor_total_power_hp),
        "battery_capacity_kwh": _decimal(item.battery_capacity_kwh),
        "battery_type": item.battery_type,
    }


def _attributes_payload(item: SpecVehicleAttributes | None):
    if item is None:
        return None
    fields = (
        "vehicle_class",
        "vehicle_technical_category",
        "body_type",
        "body_construction",
        "seat_count_min",
        "seat_count_max",
        "door_count",
        "curb_mass_kg",
        "gross_mass_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "wheelbase_mm",
        "is_four_wheel_drive",
    )
    return {field: getattr(item, field) for field in fields}


def _spec_payload(row, *, detail: bool = False):
    spec, series, brand, modification, powertrain, attributes = row
    result = {
        "id": spec.id,
        "name": spec.name,
        "year": spec.year,
        "state": _spec_state(spec.state),
        "brand": _brand_ref(brand),
        "series": _series_ref(series),
        "modification": (
            {"id": modification.id, "name": modification.name} if modification else None
        ),
        "price": _price_payload(spec),
        "description": spec.description,
        "image_url": spec.image_url,
        "powertrain": _powertrain_payload(powertrain),
    }
    if detail:
        result["vehicle_attributes"] = _attributes_payload(attributes)
    return result


def _spec_select():
    return (
        select(Spec, Series, Brand, Modification, SpecPowertrain, SpecVehicleAttributes)
        .outerjoin(Series, Series.id == Spec.series_id)
        .outerjoin(Brand, Brand.id == Series.brand_id)
        .outerjoin(Modification, Modification.id == Spec.modification_id)
        .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
        .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id)
    )


def _apply_spec_filters(
    statement,
    *,
    q=None,
    brand_id=None,
    series_id=None,
    modification_id=None,
    manufacturer_id=None,
    year_from=None,
    year_to=None,
    state=None,
    energy_type=None,
    body_type=None,
    drive_type=None,
    transmission_type=None,
    engine_displacement_from=None,
    engine_displacement_to=None,
    power_hp_from=None,
    power_hp_to=None,
    seats_from=None,
    seats_to=None,
    four_wheel_drive=None,
    price_from=None,
    price_to=None,
    price_type="effective",
):
    filters = []
    if q:
        filters.append(func.lower(Spec.name).like(_contains_pattern(q), escape="\\"))
    mappings = (
        (Series.brand_id, brand_id),
        (Spec.series_id, series_id),
        (Spec.modification_id, modification_id),
        (Series.manufacturer_id, manufacturer_id),
        (SpecPowertrain.energy_type, energy_type),
        (SpecPowertrain.body_type, body_type),
        (SpecPowertrain.drive_type, drive_type),
        (SpecPowertrain.transmission_type, transmission_type),
        (SpecVehicleAttributes.is_four_wheel_drive, four_wheel_drive),
    )
    filters.extend(column == value for column, value in mappings if value is not None)
    if state == SeriesState.UNKNOWN:
        filters.append(
            or_(Spec.state.is_(None), Spec.state.not_in(KNOWN_SPEC_STATE_CODES))
        )
    elif state is not None:
        filters.append(Spec.state.in_(SPEC_STATE_CODES[state]))
    ranges = (
        (Spec.year, year_from, year_to),
        (
            SpecPowertrain.engine_displacement_ml,
            engine_displacement_from,
            engine_displacement_to,
        ),
        (SpecPowertrain.engine_power_hp, power_hp_from, power_hp_to),
        (SpecVehicleAttributes.seat_count_max, seats_from, seats_to),
        (_price_column(price_type), price_from, price_to),
    )
    for column, minimum, maximum in ranges:
        if minimum is not None:
            filters.append(column >= minimum)
        if maximum is not None:
            filters.append(column <= maximum)
    return statement.where(*filters)


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
            "ввозную таможенную пошлину, таможенный сбор и утилизационный сбор."
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

    bearer_scheme = HTTPBearer(
        bearerFormat="JWT",
        scheme_name="JWT Bearer",
        description="JWT, полученный через POST /api/v1/auth/token.",
        auto_error=False,
    )

    async def require_authenticated_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> str:
        """Проверить JWT перед выполнением защищённого эндпоинта."""
        return authenticate_bearer(credentials, auth_settings)

    protected_router = APIRouter(dependencies=[Depends(require_authenticated_user)])

    @application.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException):
        if isinstance(exc.detail, dict) and {"code", "message"} <= exc.detail.keys():
            payload = exc.detail
        else:
            payload = {"code": "HTTP_ERROR", "message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload),
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(_, exc: RequestValidationError):
        errors = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
            },
        )

    @application.post(
        "/api/v1/auth/token",
        response_model=TokenResponse,
        tags=["Auth"],
        summary="Получить JWT",
        description="Проверяет логин и пароль и выдаёт Bearer-токен с ограниченным сроком действия.",
    )
    async def issue_token(credentials: TokenRequest):
        if not credentials_are_valid(
            credentials.username, credentials.password, auth_settings
        ):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "INVALID_CREDENTIALS",
                    "message": "Invalid username or password",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "access_token": create_access_token(credentials.username, auth_settings),
            "token_type": "bearer",
            "expires_in": auth_settings.access_token_ttl_seconds,
        }

    @application.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @protected_router.get(
        "/api/v1/brands",
        response_model=BrandPage,
        tags=["Brands"],
        summary="Получить бренды",
        description="Возвращает бренды с фильтрацией и offset-пагинацией.",
    )
    async def brands(
        q: str | None = Query(
            None, description="Поиск по части названия бренда без учёта регистра."
        ),
        manufacturer_id: int | None = Query(
            None, description="Оставить бренды указанного производителя."
        ),
        is_new_energy: bool | None = Query(
            None, description="Оставить бренды с сериями указанной категории NEV."
        ),
        sort: Literal["name", "series_count"] = Query(
            "name", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "asc", description="Направление сортировки: asc или desc."
        ),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        statement = select(Brand)
        matching_series = select(Series.id).where(Series.brand_id == Brand.id)
        if manufacturer_id is not None:
            matching_series = matching_series.where(
                Series.manufacturer_id == manufacturer_id
            )
        if is_new_energy is not None:
            matching_series = matching_series.where(
                Series.is_new_energy == is_new_energy
            )
        if q:
            statement = statement.where(
                func.lower(Brand.name).like(_contains_pattern(q), escape="\\")
            )
        if any(v is not None for v in (manufacturer_id, is_new_energy)):
            statement = statement.where(exists(matching_series))
        sort_column = {"name": Brand.name, "series_count": Brand.series_count}[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(), Brand.id.asc()
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        items = [
            {
                "id": brand.id,
                "name": brand.name,
                "logo_url": brand.logo_url,
                "series_count": brand.series_count,
            }
            for (brand,) in rows
        ]
        return {"items": items, "pagination": pagination}

    @protected_router.get(
        "/api/v1/brands/{brand_id}",
        response_model=BrandResponse,
        tags=["Brands"],
        summary="Получить бренд",
    )
    async def brand_detail(
        brand_id: int = ApiPath(description="Идентификатор бренда."),
        session: AsyncSession = Depends(get_session),
    ):
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise _not_found("Brand")
        return {
            "id": brand.id,
            "name": brand.name,
            "logo_url": brand.logo_url,
            "series_count": brand.series_count,
        }

    @protected_router.get(
        "/api/v1/manufacturers",
        response_model=ManufacturerPage,
        tags=["Manufacturers"],
        summary="Получить производителей",
        description="Возвращает производителей с поиском по названию и фильтром по бренду.",
    )
    async def manufacturers(
        q: str | None = Query(
            None,
            description="Поиск по части названия производителя без учёта регистра.",
        ),
        brand_id: int | None = Query(
            None, description="Оставить производителей указанного бренда."
        ),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        statement = select(Manufacturer)
        if brand_id is not None:
            statement = statement.join(
                BrandManufacturer,
                BrandManufacturer.manufacturer_id == Manufacturer.id,
            ).where(BrandManufacturer.brand_id == brand_id)
        if q:
            statement = statement.where(
                func.lower(Manufacturer.name).like(_contains_pattern(q), escape="\\")
            )
        statement = statement.order_by(Manufacturer.name, Manufacturer.id)
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        return {
            "items": [{"id": item.id, "name": item.name} for (item,) in rows],
            "pagination": pagination,
        }

    @protected_router.get(
        "/api/v1/manufacturers/{manufacturer_id}",
        response_model=ManufacturerResponse,
        tags=["Manufacturers"],
        summary="Получить производителя",
    )
    async def manufacturer_detail(
        manufacturer_id: int = ApiPath(description="Идентификатор производителя."),
        session: AsyncSession = Depends(get_session),
    ):
        manufacturer = await session.get(Manufacturer, manufacturer_id)
        if manufacturer is None:
            raise _not_found("Manufacturer")
        return {"id": manufacturer.id, "name": manufacturer.name}

    def series_statement():
        price = _effective_price()
        prices = (
            select(
                Spec.series_id,
                func.min(price).label("min_price"),
                func.max(price).label("max_price"),
            )
            .group_by(Spec.series_id)
            .subquery()
        )
        return (
            select(
                Series,
                Brand,
                Manufacturer,
                prices.c.min_price,
                prices.c.max_price,
            )
            .outerjoin(Brand, Brand.id == Series.brand_id)
            .outerjoin(Manufacturer, Manufacturer.id == Series.manufacturer_id)
            .outerjoin(prices, prices.c.series_id == Series.id)
        )

    async def official_images(session: AsyncSession, series_ids: list[int]):
        if not series_ids:
            return {}
        photos = await session.execute(
            select(SeriesPhoto)
            .where(
                SeriesPhoto.series_id.in_(series_ids),
                SeriesPhoto.category_id == 53,
            )
            .order_by(SeriesPhoto.series_id, SeriesPhoto.id)
        )
        photos = photos.scalars()
        result: dict[int, list[dict[str, Any]]] = {}
        for photo in photos:
            result.setdefault(photo.series_id, []).append(
                {
                    "id": photo.id,
                    "title": photo.title,
                    "image_url": photo.image_url,
                    "thumbnail_url": photo.thumbnail_url,
                }
            )
        return result

    @protected_router.get(
        "/api/v1/series",
        response_model=SeriesPage,
        tags=["Series"],
        summary="Получить серии",
        description="Фильтрует серии по бренду, производителю и характеристикам комплектаций.",
    )
    async def series_list(
        q: str | None = Query(
            None, description="Поиск по части названия серии без учёта регистра."
        ),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        manufacturer_id: int | None = Query(
            None, description="Идентификатор производителя."
        ),
        is_new_energy: bool | None = Query(
            None, description="Фильтр по принадлежности к категории NEV."
        ),
        state: SeriesState | None = Query(
            None, description="Нормализованная стадия продаж серии."
        ),
        year_from: int | None = Query(
            None, description="Минимальный модельный год комплектаций серии."
        ),
        year_to: int | None = Query(
            None, description="Максимальный модельный год комплектаций серии."
        ),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        sort: Literal["name", "price", "year"] = Query(
            "name", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "asc", description="Направление сортировки: asc или desc."
        ),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        for low, high, name in (
            (year_from, year_to, "year"),
            (engine_displacement_from, engine_displacement_to, "engine_displacement"),
            (power_hp_from, power_hp_to, "power_hp"),
            (price_from, price_to, "price"),
        ):
            _check_range(low, high, name)
        statement = series_statement()
        direct = []
        for column, value in (
            (Series.brand_id, brand_id),
            (Series.manufacturer_id, manufacturer_id),
            (Series.is_new_energy, is_new_energy),
        ):
            if value is not None:
                direct.append(column == value)
        if state == SeriesState.UNKNOWN:
            direct.append(
                or_(
                    Series.state.is_(None),
                    Series.state.not_in(KNOWN_SERIES_STATE_CODES),
                )
            )
        elif state is not None:
            direct.append(Series.state.in_(SERIES_STATE_CODES[state]))
        if q:
            direct.append(
                func.lower(Series.name).like(_contains_pattern(q), escape="\\")
            )
        matching_specs = _apply_spec_filters(
            select(Spec.id)
            .outerjoin(Series, Series.id == Spec.series_id)
            .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
            .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id),
            year_from=year_from,
            year_to=year_to,
            energy_type=energy_type,
            body_type=body_type,
            drive_type=drive_type,
            transmission_type=transmission_type,
            engine_displacement_from=engine_displacement_from,
            engine_displacement_to=engine_displacement_to,
            power_hp_from=power_hp_from,
            power_hp_to=power_hp_to,
            price_from=price_from,
            price_to=price_to,
            price_type=price_type,
        ).where(Spec.series_id == Series.id)
        if any(
            v is not None
            for v in (
                year_from,
                year_to,
                energy_type,
                body_type,
                drive_type,
                transmission_type,
                engine_displacement_from,
                engine_displacement_to,
                power_hp_from,
                power_hp_to,
                price_from,
                price_to,
            )
        ):
            direct.append(exists(matching_specs))
        statement = statement.where(*direct)
        latest_year = (
            select(func.max(Spec.year))
            .where(Spec.series_id == Series.id)
            .scalar_subquery()
        )
        sort_column = {
            "name": Series.name,
            "price": statement.selected_columns.min_price,
            "year": latest_year,
        }[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Series.id.asc(),
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        images_by_series = await official_images(session, [row[0].id for row in rows])
        items = [
            {
                "id": item.id,
                "name": item.name,
                "brand": _brand_ref(brand),
                "manufacturer": _manufacturer_ref(manufacturer),
                "is_new_energy": item.is_new_energy,
                "state": _series_state(item.state),
                "spec_count": item.spec_count,
                "price": {"min_cny": _money(minimum), "max_cny": _money(maximum)},
                "official_images": images_by_series.get(item.id, []),
            }
            for item, brand, manufacturer, minimum, maximum in rows
        ]
        return {"items": items, "pagination": pagination}

    @protected_router.get(
        "/api/v1/series/{series_id}",
        response_model=SeriesResponse,
        tags=["Series"],
        summary="Получить серию",
    )
    async def series_detail(
        series_id: int = ApiPath(description="Идентификатор серии."),
        session: AsyncSession = Depends(get_session),
    ):
        row = (
            await session.execute(series_statement().where(Series.id == series_id))
        ).one_or_none()
        if row is None:
            raise _not_found("Series")
        item, brand, manufacturer, minimum, maximum = row
        return {
            "id": item.id,
            "name": item.name,
            "brand": _brand_ref(brand),
            "manufacturer": _manufacturer_ref(manufacturer),
            "is_new_energy": item.is_new_energy,
            "state": _series_state(item.state),
            "spec_count": item.spec_count,
            "price": {"min_cny": _money(minimum), "max_cny": _money(maximum)},
            "official_images": (await official_images(session, [item.id])).get(
                item.id, []
            ),
        }

    async def modification_list_impl(
        session: AsyncSession,
        *,
        series_id=None,
        brand_id=None,
        year_from=None,
        year_to=None,
        energy_type=None,
        body_type=None,
        drive_type=None,
        transmission_type=None,
        engine_displacement_from=None,
        engine_displacement_to=None,
        power_hp_from=None,
        power_hp_to=None,
        price_from=None,
        price_to=None,
        price_type="effective",
        sort="year",
        order="desc",
        limit=24,
        offset=0,
        include_total=False,
    ):
        for low, high, name in (
            (year_from, year_to, "year"),
            (engine_displacement_from, engine_displacement_to, "engine_displacement"),
            (power_hp_from, power_hp_to, "power_hp"),
            (price_from, price_to, "price"),
        ):
            _check_range(low, high, name)
        price = _price_column(price_type)
        prices = (
            select(
                Spec.modification_id,
                func.min(price).label("min_price"),
                func.max(price).label("max_price"),
            )
            .group_by(Spec.modification_id)
            .subquery()
        )
        statement = select(
            Modification, prices.c.min_price, prices.c.max_price
        ).outerjoin(prices, prices.c.modification_id == Modification.id)
        filters = []
        mappings = (
            (Modification.series_id, series_id),
            (Modification.energy_type, energy_type),
            (Modification.body_type, body_type),
            (Modification.drive_type, drive_type),
            (Modification.transmission_type, transmission_type),
        )
        filters.extend(
            column == value for column, value in mappings if value is not None
        )
        if brand_id is not None:
            filters.append(
                exists(
                    select(Series.id).where(
                        Series.id == Modification.series_id, Series.brand_id == brand_id
                    )
                )
            )
        for column, low, high in (
            (Modification.model_year, year_from, year_to),
            (
                Modification.engine_displacement_ml,
                engine_displacement_from,
                engine_displacement_to,
            ),
            (Modification.engine_power_hp, power_hp_from, power_hp_to),
            (prices.c.min_price, price_from, price_to),
        ):
            if low is not None:
                filters.append(column >= low)
            if high is not None:
                filters.append(column <= high)
        sort_column = {
            "year": Modification.model_year,
            "power": Modification.engine_power_hp,
            "engine_displacement": Modification.engine_displacement_ml,
            "price": prices.c.min_price,
            "name": Modification.name,
        }[sort]
        statement = statement.where(*filters).order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Modification.id.asc(),
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        items = [
            {
                "id": item.id,
                "series_id": item.series_id,
                "model_year": item.model_year,
                "name": item.name,
                "energy_type": item.energy_type,
                "engine_summary": item.engine_summary,
                "engine_displacement_ml": item.engine_displacement_ml,
                "engine_power_kw": _decimal(item.engine_power_kw),
                "engine_power_hp": _decimal(item.engine_power_hp),
                "transmission_summary": item.transmission_summary,
                "transmission_type": item.transmission_type,
                "drive_type": item.drive_type,
                "body_type": item.body_type,
                "battery_capacity_kwh": _decimal(item.battery_capacity_kwh),
                "spec_count": item.spec_count,
                "price": {"min_cny": _money(minimum), "max_cny": _money(maximum)},
            }
            for item, minimum, maximum in rows
        ]
        return {"items": items, "pagination": pagination}

    @protected_router.get(
        "/api/v1/modifications",
        response_model=ModificationPage,
        tags=["Modifications"],
        summary="Получить модификации",
    )
    async def modifications(
        series_id: int | None = Query(None, description="Идентификатор серии."),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        sort: Literal["year", "power", "engine_displacement", "price", "name"] = Query(
            "year", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "desc", description="Направление сортировки: asc или desc."
        ),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        argument_names = {
            "series_id",
            "brand_id",
            "year_from",
            "year_to",
            "energy_type",
            "body_type",
            "drive_type",
            "transmission_type",
            "engine_displacement_from",
            "engine_displacement_to",
            "power_hp_from",
            "power_hp_to",
            "price_from",
            "price_to",
            "price_type",
            "sort",
            "order",
            "limit",
            "offset",
            "include_total",
        }
        return await modification_list_impl(
            session,
            **{key: value for key, value in locals().items() if key in argument_names},
        )

    @protected_router.get(
        "/api/v1/series/{series_id}/modifications",
        response_model=ModificationPage,
        tags=["Modifications"],
        summary="Получить модификации серии",
    )
    async def series_modifications(
        series_id: int = ApiPath(description="Идентификатор серии."),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
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
        return await modification_list_impl(
            session,
            series_id=series_id,
            year_from=year_from,
            year_to=year_to,
            energy_type=energy_type,
            body_type=body_type,
            drive_type=drive_type,
            transmission_type=transmission_type,
            engine_displacement_from=engine_displacement_from,
            engine_displacement_to=engine_displacement_to,
            power_hp_from=power_hp_from,
            power_hp_to=power_hp_to,
            price_from=price_from,
            price_to=price_to,
            price_type=price_type,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    @protected_router.get(
        "/api/v1/modifications/{modification_id}",
        response_model=ModificationResponse,
        tags=["Modifications"],
        summary="Получить модификацию",
    )
    async def modification_detail(
        modification_id: int = ApiPath(
            description="Идентификатор технической модификации."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        item = await session.get(Modification, modification_id)
        if item is None:
            raise _not_found("Modification")
        price = _effective_price()
        minimum, maximum = (
            await session.execute(
                select(func.min(price), func.max(price)).where(
                    Spec.modification_id == modification_id
                )
            )
        ).one()
        return {
            "id": item.id,
            "series_id": item.series_id,
            "model_year": item.model_year,
            "name": item.name,
            "energy_type": item.energy_type,
            "engine_summary": item.engine_summary,
            "engine_displacement_ml": item.engine_displacement_ml,
            "engine_power_kw": _decimal(item.engine_power_kw),
            "engine_power_hp": _decimal(item.engine_power_hp),
            "transmission_summary": item.transmission_summary,
            "transmission_type": item.transmission_type,
            "drive_type": item.drive_type,
            "body_type": item.body_type,
            "battery_capacity_kwh": _decimal(item.battery_capacity_kwh),
            "spec_count": item.spec_count,
            "price": {"min_cny": _money(minimum), "max_cny": _money(maximum)},
        }

    async def specs_impl(
        session: AsyncSession,
        limit: int,
        offset: int,
        include_total: bool,
        sort="price",
        order="asc",
        **filters,
    ):
        ranges = (
            (filters.get("year_from"), filters.get("year_to"), "year"),
            (
                filters.get("engine_displacement_from"),
                filters.get("engine_displacement_to"),
                "engine_displacement",
            ),
            (filters.get("power_hp_from"), filters.get("power_hp_to"), "power_hp"),
            (filters.get("seats_from"), filters.get("seats_to"), "seats"),
            (filters.get("price_from"), filters.get("price_to"), "price"),
        )
        for low, high, name in ranges:
            _check_range(low, high, name)
        statement = _apply_spec_filters(_spec_select(), **filters)
        sort_column = {
            "price": _price_column(filters.get("price_type", "effective")),
            "year": Spec.year,
            "power": SpecPowertrain.engine_power_hp,
            "engine_displacement": SpecPowertrain.engine_displacement_ml,
            "name": Spec.name,
        }[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(), Spec.id.asc()
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        return {"items": [_spec_payload(row) for row in rows], "pagination": pagination}

    @protected_router.get(
        "/api/v1/specs",
        response_model=SpecPage,
        tags=["Specs"],
        summary="Получить комплектации",
        description="Возвращает комплектации с ценами и нормализованной силовой установкой.",
    )
    async def specs(
        q: str | None = Query(
            None, description="Поиск по части названия комплектации без учёта регистра."
        ),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        series_id: int | None = Query(None, description="Идентификатор серии."),
        modification_id: int | None = Query(
            None, description="Идентификатор технической модификации."
        ),
        manufacturer_id: int | None = Query(
            None, description="Идентификатор производителя."
        ),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        state: SeriesState | None = Query(
            None, description="Стадия продаж комплектации."
        ),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        seats_from: int | None = Query(None, description="Минимальное число мест."),
        seats_to: int | None = Query(None, description="Максимальное число мест."),
        four_wheel_drive: bool | None = Query(
            None, description="Фильтр по наличию полного привода."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        sort: Literal["price", "year", "power", "engine_displacement", "name"] = Query(
            "price", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "asc", description="Направление сортировки: asc или desc."
        ),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        filter_names = {
            "q",
            "brand_id",
            "series_id",
            "modification_id",
            "manufacturer_id",
            "year_from",
            "year_to",
            "state",
            "energy_type",
            "body_type",
            "drive_type",
            "transmission_type",
            "engine_displacement_from",
            "engine_displacement_to",
            "power_hp_from",
            "power_hp_to",
            "seats_from",
            "seats_to",
            "four_wheel_drive",
            "price_from",
            "price_to",
            "price_type",
        }
        values = {key: value for key, value in locals().items() if key in filter_names}
        return await specs_impl(
            session, limit, offset, include_total, sort=sort, order=order, **values
        )

    @protected_router.get(
        "/api/v1/modifications/{modification_id}/specs",
        response_model=SpecPage,
        tags=["Specs"],
        summary="Получить комплектации модификации",
    )
    async def modification_specs(
        modification_id: int = ApiPath(
            description="Идентификатор технической модификации."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        limit: int = Query(
            24, ge=1, le=100, description="Максимальное число элементов на странице."
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Modification, modification_id) is None:
            raise _not_found("Modification")
        return await specs_impl(
            session,
            limit,
            offset,
            include_total,
            modification_id=modification_id,
            price_from=price_from,
            price_to=price_to,
            price_type=price_type,
        )

    @protected_router.get(
        "/api/v1/specs/{spec_id}",
        response_model=SpecDetailResponse,
        tags=["Specs"],
        summary="Получить комплектацию",
    )
    async def spec_detail(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        session: AsyncSession = Depends(get_session),
    ):
        row = (
            await session.execute(_spec_select().where(Spec.id == spec_id))
        ).one_or_none()
        if row is None:
            raise _not_found("Spec")
        return _spec_payload(row, detail=True)

    @protected_router.get(
        "/api/v1/specs/{spec_id}/parameters",
        response_model=ParameterGroupsResponse,
        tags=["Specs"],
        summary="Получить полную конфигурацию комплектации",
    )
    async def spec_parameters(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        group_id: int | None = Query(
            None, description="Оставить указанную группу характеристик."
        ),
        section_id: int | None = Query(
            None, description="Оставить указанный раздел характеристик."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Spec, spec_id) is None:
            raise _not_found("Spec")
        statement = (
            select(ParameterGroup, ParameterSection, ParameterDefinition, SpecParameter)
            .join(ParameterSection, ParameterSection.group_id == ParameterGroup.id)
            .join(
                ParameterDefinition,
                ParameterDefinition.section_id == ParameterSection.id,
            )
            .join(
                SpecParameter,
                and_(
                    SpecParameter.parameter_id == ParameterDefinition.id,
                    SpecParameter.spec_id == spec_id,
                ),
            )
            .order_by(
                ParameterGroup.position,
                ParameterSection.position,
                ParameterDefinition.id,
            )
        )
        if group_id is not None:
            statement = statement.where(ParameterGroup.id == group_id)
        if section_id is not None:
            statement = statement.where(ParameterSection.id == section_id)
        subitems = await session.execute(
            select(ParameterSubitem)
            .where(ParameterSubitem.spec_id == spec_id)
            .order_by(ParameterSubitem.parameter_id, ParameterSubitem.position)
        )
        subitems = subitems.scalars()
        subitems_by_parameter: dict[int, list] = {}
        for subitem in subitems:
            subitems_by_parameter.setdefault(subitem.parameter_id, []).append(
                {
                    "name": subitem.name,
                    "value": subitem.value,
                    "option_price_cny": _money(subitem.option_price_yuan),
                }
            )
        groups: dict[int, dict] = {}
        sections: dict[int, dict] = {}
        result = await session.execute(statement)
        for group, section, definition, value in result:
            group_payload = groups.setdefault(
                group.id, {"id": group.id, "name": group.name, "sections": []}
            )
            section_payload = sections.get(section.id)
            if section_payload is None:
                section_payload = {
                    "id": section.id,
                    "name": section.name,
                    "parameters": [],
                }
                sections[section.id] = section_payload
                group_payload["sections"].append(section_payload)
            section_payload["parameters"].append(
                {
                    "id": definition.id,
                    "semantic_key": definition.semantic_key,
                    "name": definition.name,
                    "value": value.value,
                    "option_price_cny": _money(value.option_price_yuan),
                    "video_url": value.video_url,
                    "subitems": subitems_by_parameter.get(definition.id, []),
                }
            )
        return {"items": list(groups.values())}

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

    async def calculation_payload(
        session: AsyncSession, calculation: CustomsCalculation
    ):
        payments = list(
            (
                await session.execute(
                    select(CustomsPaymentResult)
                    .where(CustomsPaymentResult.calculation_id == calculation.id)
                    .order_by(CustomsPaymentResult.payment_type)
                )
            ).scalars()
        )
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
        calculation_date=None,
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
            (CustomsCalculation.calculation_date, calculation_date),
        ):
            if value is not None:
                filters.append(column == value)
        statement = statement.where(*filters).order_by(
            CustomsCalculation.calculation_date.desc(), CustomsCalculation.id.desc()
        )
        rows, pagination = await _page(session, statement, limit, offset, include_total)
        return {
            "items": [await calculation_payload(session, row[0]) for row in rows],
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
        return await calculation_payload(session, item)

    @protected_router.get(
        "/api/v1/specs/{spec_id}/customs-calculations",
        response_model=CustomsCalculationPage,
        tags=["Customs"],
        summary="Получить актуальные таможенные расчёты комплектации",
    )
    async def spec_calculations(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        importer_type: ImporterType | None = Query(None, description="Тип импортёра."),
        calculation_date: date | None = Query(None, description="Точная дата расчёта."),
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
            calculation_date=calculation_date,
        )

    application.include_router(protected_router)
    return application
