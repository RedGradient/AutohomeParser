"""Выдача и проверка JWT для HTTP API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


JWT_ALGORITHM = "HS256"
JWT_ISSUER = "autohome-catalog-api"
JWT_AUDIENCE = "autohome-api"
DEFAULT_JWT_SECRET = "development-only-autohome-jwt-secret-change-me"


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
            username=username or os.getenv("API_USERNAME", "autohome"),
            password=password or os.getenv("API_PASSWORD", "autohome"),
            secret=secret or os.getenv("API_JWT_SECRET", DEFAULT_JWT_SECRET),
            access_token_ttl_seconds=ttl,
        )
        if not settings.username or not settings.password:
            raise ValueError("API_USERNAME и API_PASSWORD не должны быть пустыми")
        if len(settings.secret.encode()) < 32:
            raise ValueError("API_JWT_SECRET должен содержать не менее 32 байт")
        if settings.access_token_ttl_seconds <= 0:
            raise ValueError("API_JWT_TTL_SECONDS должен быть положительным")
        return settings


def _base64url_encode(value: bytes) -> str:
    """Закодировать JWT-сегмент без символов заполнения."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    """Декодировать JWT-сегмент с восстановлением заполнения."""
    return base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )


def _json_segment(value: dict[str, Any]) -> str:
    """Сериализовать объект в канонический JWT-сегмент."""
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _base64url_encode(payload.encode("utf-8"))


def create_access_token(username: str, settings: AuthSettings) -> str:
    """Создать подписанный HS256 access token."""
    issued_at = int(time.time())
    header = _json_segment({"alg": JWT_ALGORITHM, "typ": "JWT"})
    payload = _json_segment(
        {
            "sub": username,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": issued_at,
            "exp": issued_at + settings.access_token_ttl_seconds,
        }
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(settings.secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_base64url_encode(signature)}"


def decode_access_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    """Проверить подпись и обязательные claims JWT."""
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(_base64url_decode(header_part))
        payload = json.loads(_base64url_decode(payload_part))
        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise ValueError("JWT должен содержать JSON-объекты")
        supplied_signature = _base64url_decode(signature_part)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected_signature = hmac.new(
            settings.secret.encode(), signing_input, hashlib.sha256
        ).digest()
        if header != {"alg": JWT_ALGORITHM, "typ": "JWT"}:
            raise ValueError("Неподдерживаемый заголовок JWT")
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("Неверная подпись JWT")
        if payload.get("iss") != JWT_ISSUER or payload.get("aud") != JWT_AUDIENCE:
            raise ValueError("Неверный издатель или получатель JWT")
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise ValueError("Отсутствует subject JWT")
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= int(time.time()):
            raise ValueError("JWT истёк")
        if not isinstance(payload.get("iat"), int) or payload["iat"] > int(time.time()) + 30:
            raise ValueError("Некорректное время выдачи JWT")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise invalid_token_error() from exc
    return payload


def credentials_are_valid(username: str, password: str, settings: AuthSettings) -> bool:
    """Сравнить логин и пароль без раннего выхода по несовпавшему байту."""
    return secrets.compare_digest(username.encode(), settings.username.encode()) and secrets.compare_digest(
        password.encode(), settings.password.encode()
    )


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
