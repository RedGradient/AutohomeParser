from __future__ import annotations

from twisted.internet import reactor
from twisted.internet.task import deferLater


class DelayedRetryMiddleware:
    """Отложить только запросы, явно помеченные как повторные."""

    def process_request(self, request, spider):
        """Подождать заданное число секунд без блокировки других запросов."""
        delay = request.meta.pop("retry_delay", None)
        if not delay:
            return None
        return deferLater(reactor, float(delay), lambda: None)
