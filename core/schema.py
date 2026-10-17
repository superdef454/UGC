"""Общие куски OpenAPI-схемы."""

from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers

ERROR = inline_serializer("Error", fields={"detail": serializers.CharField()})

_DESCRIPTIONS = {
    400: "Невалидные данные или нарушено правило (например, обязательный вопрос без ответа)",
    401: "Пользователь не идентифицирован",
    404: "Не найдено или недоступно текущему пользователю",
    409: "Действие не подходит текущему состоянию (опрос закрыт, уже пройден и т.п.)",
}


def errors(*codes: int) -> dict[int, OpenApiResponse]:
    """Описание ошибочных ответов для ``extend_schema(responses=...)``."""
    return {code: OpenApiResponse(ERROR, description=_DESCRIPTIONS[code]) for code in codes}
