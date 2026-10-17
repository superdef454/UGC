from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """Нарушение бизнес-правила. Сервисы кидают его, API превращает в понятный ответ."""

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """Объект не найден или недоступен пользователю."""

    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(DomainError):
    """Действие не подходит текущему состоянию объекта: опрос закрыт, уже пройден и т.п."""

    status_code = status.HTTP_409_CONFLICT


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Обработчик DRF, который дополнительно понимает доменные ошибки."""
    if isinstance(exc, DomainError):
        return Response({"detail": exc.message}, status=exc.status_code)
    return drf_exception_handler(exc, context)
