"""Общие зависимости FastAPI для защищённых маршрутов API."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from autohome.api.auth import AuthSettings, authenticate_bearer

bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    scheme_name="JWT Bearer",
    description="JWT, полученный через POST /api/v1/auth/token.",
    auto_error=False,
)


def authenticated_user_dependency(
    settings: AuthSettings,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Создать зависимость проверки JWT с настройками приложения."""

    async def require_authenticated_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> str:
        """Проверить JWT перед выполнением защищённого эндпоинта."""
        return authenticate_bearer(credentials, settings)

    return require_authenticated_user
