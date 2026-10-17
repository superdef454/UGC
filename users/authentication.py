from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from users.models import User


class HeaderUserAuthentication(BaseAuthentication):
    """Временная идентификация по заголовку ``X-User-Id``.

    Нужна для API-клиентов, тестов и нагрузки, пока нет нормальной авторизации.
    Включается флагом HEADER_AUTH_ENABLED, в проде выключена.

    TODO: заменить на токены / OAuth.
    """

    header = "HTTP_X_USER_ID"

    def authenticate(self, request: Request) -> tuple[User, None] | None:
        raw_user_id = request.META.get(self.header)
        if not raw_user_id:
            return None

        try:
            user_id = int(raw_user_id)
        except ValueError as exc:
            raise AuthenticationFailed("X-User-Id должен быть числом") from exc

        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Пользователь не найден")
        return user, None

    def authenticate_header(self, request: Request) -> str:
        return "X-User-Id"
