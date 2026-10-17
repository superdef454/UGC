from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Пользователи."""

    name = "users"
    verbose_name = "Пользователи"

    def ready(self) -> None:
        from users import schema  # noqa: F401 - регистрирует расширение для swagger
