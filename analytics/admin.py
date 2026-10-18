from django.contrib import admin

from analytics.models import QuizStatistics, StatisticsOutbox
from core.admin import ReadOnlyAdmin


@admin.register(QuizStatistics)
class QuizStatisticsAdmin(ReadOnlyAdmin):
    """Готовая статистика - только просмотр, её пишет воркер."""

    list_display = ("quiz", "attempts_count", "avg_duration", "updated_at")
    raw_id_fields = ("quiz",)


@admin.register(StatisticsOutbox)
class StatisticsOutboxAdmin(ReadOnlyAdmin):
    """Очередь на подсчёт статистики - только просмотр."""

    list_display = ("id", "attempt", "created_at")
    raw_id_fields = ("attempt",)
