"""Маршруты аутентификации API."""

from fastapi import APIRouter, HTTPException

from autohome.api.auth import (
    AuthSettings,
    create_access_token,
    credentials_are_valid,
)
from autohome.api.schemas import TokenRequest, TokenResponse


def create_auth_router(settings: AuthSettings) -> APIRouter:
    """Создать роутер выдачи JWT с настройками приложения."""
    router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

    @router.post(
        "/token",
        response_model=TokenResponse,
        summary="Получить JWT",
        description=(
            "Проверяет логин и пароль и выдаёт Bearer-токен "
            "с ограниченным сроком действия."
        ),
    )
    async def issue_token(credentials: TokenRequest):
        if not credentials_are_valid(
            credentials.username, credentials.password, settings
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
            "access_token": create_access_token(credentials.username, settings),
            "token_type": "bearer",
            "expires_in": settings.access_token_ttl_seconds,
        }

    return router
