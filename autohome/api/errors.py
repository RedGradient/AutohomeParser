"""Общий формат ошибок HTTP и валидации API."""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def check_range(minimum: Any, maximum: Any, name: str) -> None:
    """Проверить, что нижняя граница диапазона не превышает верхнюю."""
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(
            400,
            detail={
                "code": "INVALID_RANGE",
                "message": f"{name}_from must not exceed {name}_to",
            },
        )


def not_found(resource: str) -> HTTPException:
    """Создать исключение для отсутствующего ресурса."""
    return HTTPException(
        404, detail={"code": "NOT_FOUND", "message": f"{resource} not found"}
    )


async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
    """Преобразовать HTTPException в единый публичный формат."""
    if isinstance(exc.detail, dict) and {"code", "message"} <= exc.detail.keys():
        payload = exc.detail
    else:
        payload = {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(payload),
        headers=exc.headers,
    )


async def validation_exception_handler(
    _: Any, exc: RequestValidationError
) -> JSONResponse:
    """Преобразовать ошибки Pydantic в единый публичный формат."""
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


def register_exception_handlers(application: FastAPI) -> None:
    """Зарегистрировать общие обработчики ошибок приложения."""
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
