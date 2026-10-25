"""Общие средства offset-пагинации API."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

INCLUDE_TOTAL_DESCRIPTION = (
    "Если true, возвращает общее количество найденных записей. "
    "Может увеличить время ответа."
)


async def page(
    session: AsyncSession,
    statement: Any,
    limit: int,
    offset: int,
    include_total: bool,
) -> tuple[list[Any], dict[str, int | bool | None]]:
    """Получить страницу результата и метаданные offset-пагинации."""
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
