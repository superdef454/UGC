from django import template

register = template.Library()


@register.filter
def ru_plural(number: int, forms: str) -> str:
    """Форма слова для числа: ``{{ n|ru_plural:"вопрос,вопроса,вопросов" }}``."""
    one, few, many = forms.split(",")
    tail = abs(number) % 100
    if 10 < tail < 20:
        return many
    if tail % 10 == 1:
        return one
    if 2 <= tail % 10 <= 4:
        return few
    return many


@register.filter
def duration(seconds: float | None) -> str:
    """Секунды в человеческом виде: ``1 мин 05 с``, ``12.5 с``."""
    if seconds is None:
        return "нет данных"
    minutes, rest = divmod(round(seconds), 60)
    if minutes:
        return f"{minutes} мин {rest:02d} с"
    return f"{seconds:.1f} с".replace(".", ",")
