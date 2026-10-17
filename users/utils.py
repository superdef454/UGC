from django.http import HttpRequest
from rest_framework.request import Request

from users.models import User


def request_user(request: Request | HttpRequest) -> User:
    """Пользователь запроса. Вызывать только во view, закрытых аутентификацией."""
    user = request.user
    if not isinstance(user, User):
        raise TypeError("view должна требовать аутентификацию")
    return user
