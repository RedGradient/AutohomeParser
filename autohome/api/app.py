from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from autohome.api.auth import AuthSettings
from autohome.api.dependencies import authenticated_user_dependency
from autohome.api.errors import (
    register_exception_handlers,
)
from autohome.api.routers.auth import create_auth_router
from autohome.api.routers.brands import create_brands_router
from autohome.api.routers.customs import create_customs_router
from autohome.api.routers.manufacturers import create_manufacturers_router
from autohome.api.routers.modifications import create_modifications_router
from autohome.api.routers.photos import create_photos_router
from autohome.api.routers.series import create_series_router
from autohome.api.routers.specs import create_specs_router
from autohome.api.schemas import (
    ErrorResponse,
)
from autohome.api.session import DatabaseSessionManager


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
    application.include_router(
        create_photos_router(get_session, require_authenticated_user)
    )
    application.include_router(
        create_customs_router(get_session, require_authenticated_user)
    )

    @application.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return application
