from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class HeaderUserAuthenticationScheme(OpenApiAuthenticationExtension):
    """Описание X-User-Id для swagger - чтобы можно было авторизоваться прямо в /api/docs/."""

    target_class = "users.authentication.HeaderUserAuthentication"
    name = "UserIdHeader"

    def get_security_definition(self, auto_schema: AutoSchema) -> dict[str, Any]:
        return {"type": "apiKey", "in": "header", "name": "X-User-Id"}
