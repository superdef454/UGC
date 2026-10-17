from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Пользователь.

    Своих полей пока нет, но модель заведена сразу: заменить стандартного User
    в живом проекте потом очень больно.
    """
