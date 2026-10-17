from django.contrib import admin

from quizzes.models import AnswerOption, Question, Quiz


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 0


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "created_at", "published_at")
    list_filter = ("status",)
    search_fields = ("title",)
    raw_id_fields = ("author", "cloned_from")
    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order", "type", "is_required")
    raw_id_fields = ("quiz",)
    inlines = (AnswerOptionInline,)
