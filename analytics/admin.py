from django.contrib import admin

from analytics.models import QuizStatistics, StatisticsOutbox


@admin.register(QuizStatistics)
class QuizStatisticsAdmin(admin.ModelAdmin):
    list_display = ("quiz", "attempts_count", "avg_duration", "updated_at")
    raw_id_fields = ("quiz",)
    readonly_fields = ("attempts_count", "total_duration_ms", "data", "updated_at")


@admin.register(StatisticsOutbox)
class StatisticsOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "created_at")
    raw_id_fields = ("attempt",)
