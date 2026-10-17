from django.contrib import admin

from attempts.models import Attempt
from core.admin import ReadOnlyAdmin


@admin.register(Attempt)
class AttemptAdmin(ReadOnlyAdmin):
    list_display = ("id", "user", "quiz", "status", "started_at", "finished_at")
    list_filter = ("status",)
    raw_id_fields = ("user", "quiz")
    # Ответов на проде миллиард - в админке их не показываю, только сами прохождения.
