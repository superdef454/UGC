from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from quizzes.models import AnswerOption, Question, Quiz

# Структура опубликованного опроса заморожена и в админке тоже: иначе ответы
# и статистика начнут относиться к другим вопросам. Статус меняется только
# через сайт / API, там проверки публикации.


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True

    def _editable(self, quiz: Quiz | None) -> bool:
        return quiz is None or quiz.is_editable

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_delete_permission(request, obj)


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 0

    def _editable(self, question: Question | None) -> bool:
        return question is None or question.quiz.is_editable

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._editable(obj) and super().has_delete_permission(request, obj)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "created_at", "published_at")
    list_filter = ("status",)
    search_fields = ("title",)
    raw_id_fields = ("author", "cloned_from")
    readonly_fields = ("status", "published_at")
    inlines = (QuestionInline,)

    def has_change_permission(self, request: HttpRequest, obj: Quiz | None = None) -> bool:
        editable = obj is None or obj.is_editable
        return editable and super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Quiz | None = None) -> bool:
        editable = obj is None or obj.is_editable
        return editable and super().has_delete_permission(request, obj)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order", "type", "is_required")
    raw_id_fields = ("quiz",)
    inlines = (AnswerOptionInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # вопросы добавляются из опроса, где видно, черновик ли он

    def has_change_permission(self, request: HttpRequest, obj: Question | None = None) -> bool:
        editable = obj is None or obj.quiz.is_editable
        return editable and super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Question | None = None) -> bool:
        editable = obj is None or obj.quiz.is_editable
        return editable and super().has_delete_permission(request, obj)
