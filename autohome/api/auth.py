"""Выдача и проверка JWT для HTTP API."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt import PyJWTError

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "autohome-catalog-api"
JWT_AUDIENCE = "autohome-api"


@dataclass(frozen=True)
class AuthSettings:
    """Настройки единственного локального пользователя и JWT."""

    username: str
    password: str
    secret: str
    access_token_ttl_seconds: int

    @classmethod
    def from_environment(
        cls,
        *,
        username: str | None = None,
        password: str | None = None,
        secret: str | None = None,
        access_token_ttl_seconds: int | None = None,
    ) -> AuthSettings:
        """Собрать настройки из аргументов либо переменных окружения."""
        ttl = access_token_ttl_seconds
        if ttl is None:
            ttl = int(os.getenv("API_JWT_TTL_SECONDS", "3600"))
        settings = cls(
            username=username
            if username is not None
            else os.getenv("API_USERNAME", ""),
            password=password
            if password is not None
            else os.getenv("API_PASSWORD", ""),
            secret=secret if secret is not None else os.getenv("API_JWT_SECRET", ""),
            access_token_ttl_seconds=ttl,
        )
        if not settings.username or not settings.password:
            raise ValueError("API_USERNAME и API_PASSWORD не должны быть пустыми")
        if len(settings.secret.encode()) < 32:
            raise ValueError("API_JWT_SECRET должен содержать не менее 32 байт")
        if settings.access_token_ttl_seconds <= 0:
            raise ValueError("API_JWT_TTL_SECONDS должен быть положительным")
        return settings


def create_access_token(username: str, settings: AuthSettings) -> str:
    """Создать подписанный HS256 access token."""
    issued_at = int(time.time())
    return jwt.encode(
        {
            "sub": username,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": issued_at,
            "exp": issued_at + settings.access_token_ttl_seconds,
        },
        settings.secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str, settings: AuthSettings) -> dict:
    """Проверить подпись и обязательные claims JWT."""
    try:
        payload = jwt.decode(
            token,
            settings.secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise ValueError("Отсутствует subject JWT")
        if not isinstance(payload.get("iat"), int):
            raise ValueError("Некорректное время выдачи JWT")
    except (PyJWTError, ValueError, TypeError) as exc:
        raise invalid_token_error() from exc
    return payload


def credentials_are_valid(username: str, password: str, settings: AuthSettings) -> bool:
    """Сравнить логин и пароль без раннего выхода по несовпавшему байту."""
    return secrets.compare_digest(
        username.encode(), settings.username.encode()
    ) and secrets.compare_digest(password.encode(), settings.password.encode())


def invalid_token_error() -> HTTPException:
    """Создать единообразную ошибку отсутствующего или неверного токена."""
    return HTTPException(
        status_code=401,
        detail={"code": "INVALID_TOKEN", "message": "Valid Bearer token required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_bearer(
    credentials: HTTPAuthorizationCredentials | None,
    settings: AuthSettings,
) -> str:
    """Проверить Bearer credentials и вернуть имя пользователя."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise invalid_token_error()
    payload = decode_access_token(credentials.credentials, settings)
    if not secrets.compare_digest(payload["sub"].encode(), settings.username.encode()):
        raise invalid_token_error()
    return payload["sub"]
