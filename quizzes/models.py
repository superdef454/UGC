from django.conf import settings
from django.db import models
from django.db.models import Deferrable, Q


class Quiz(models.Model):
    """Опрос.

    Пока опрос черновик, автор свободно меняет структуру. После публикации
    структура замораживается: иначе поедет статистика и уже данные ответы.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        CLOSED = "closed", "Закрыт"
        # TODO: ON_MODERATION = "on_moderation", "На модерации" - между черновиком и публикацией

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quizzes",
        db_index=False,  # покрыт индексом (author, -created_at)
    )
    title = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    cloned_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clones",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "опрос"
        verbose_name_plural = "опросы"
        indexes = [
            models.Index(fields=["author", "-created_at"], name="quiz_author_created_idx"),
            # Список доступных опросов: только опубликованные, свежие сверху.
            models.Index(
                fields=["-published_at", "-id"],
                name="quiz_published_idx",
                condition=Q(status="published"),
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_editable(self) -> bool:
        """Менять структуру можно только у черновика."""
        return self.status == self.Status.DRAFT


class Question(models.Model):
    """Вопрос опроса. Порядок задаёт автор через ``order``."""

    class Type(models.TextChoices):
        SINGLE = "single", "Один вариант"
        MULTIPLE = "multiple", "Несколько вариантов"

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
        db_index=False,  # покрыт уникальным индексом (quiz, order)
    )
    text = models.CharField("текст", max_length=1000)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.SINGLE)
    order = models.PositiveSmallIntegerField()
    allow_custom_answer = models.BooleanField("можно свой ответ", default=False)
    is_required = models.BooleanField("обязательный", default=True)

    class Meta:
        verbose_name = "вопрос"
        verbose_name_plural = "вопросы"
        ordering = ["order"]
        constraints = [
            # Отложенная проверка: при перестановке вопросов порядок в моменте
            # может совпадать, важно только состояние на коммите.
            models.UniqueConstraint(
                fields=["quiz", "order"],
                name="question_quiz_order_uniq",
                deferrable=Deferrable.DEFERRED,
            ),
        ]

    def __str__(self) -> str:
        return self.text


class AnswerOption(models.Model):
    """Вариант ответа на вопрос."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        db_index=False,  # покрыт уникальным индексом (question, order)
    )
    text = models.CharField("текст", max_length=500)
    order = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "вариант ответа"
        verbose_name_plural = "варианты ответов"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"],
                name="option_question_order_uniq",
                deferrable=Deferrable.DEFERRED,
            ),
        ]

    def __str__(self) -> str:
        return self.text
