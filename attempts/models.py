from django.conf import settings
from django.db import models
from django.db.models import Q

from quizzes.models import AnswerOption, Question, Quiz


class Attempt(models.Model):
    """Прохождение опроса пользователем. Одно на пару пользователь + опрос."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "В процессе"
        FINISHED = "finished", "Завершено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attempts",
        db_index=False,  # покрыт уникальным индексом (user, quiz)
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "прохождение"
        verbose_name_plural = "прохождения"
        constraints = [
            models.UniqueConstraint(fields=["user", "quiz"], name="attempt_user_quiz_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(status="finished", finished_at__isnull=False)
                    | Q(status="in_progress", finished_at__isnull=True)
                ),
                name="attempt_finished_at_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.quiz_id}"


class Answer(models.Model):
    """Ответ на один вопрос в рамках прохождения.

    Это самая большая таблица (~1 млрд строк на целевых объёмах), поэтому
    лишних индексов здесь нет.
    """

    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name="answers",
        db_index=False,  # покрыт уникальным индексом (attempt, question)
    )
    # Индекс по question запросам не нужен, но без него проверка PROTECT при удалении
    # вопроса из черновика - это seq scan по миллиарду строк. Осознанный компромисс.
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    selected_options = models.ManyToManyField(
        AnswerOption, through="AnswerChoice", related_name="+"
    )
    custom_text = models.CharField("свой ответ", max_length=1000, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ответ"
        verbose_name_plural = "ответы"
        constraints = [
            # Один ответ на вопрос - заодно защита от двойной отправки формы.
            models.UniqueConstraint(
                fields=["attempt", "question"], name="answer_attempt_question_uniq"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id}: {self.question_id}"


class AnswerChoice(models.Model):
    """Выбранный вариант ответа.

    Явная through-модель вместо автоматической M2M: так у таблицы BigAutoField
    и свои индексы, а не те, что Django сгенерирует сам.
    """

    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="choices",
        db_index=False,  # покрыт уникальным индексом (answer, option)
    )
    option = models.ForeignKey(AnswerOption, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "выбранный вариант"
        verbose_name_plural = "выбранные варианты"
        constraints = [
            models.UniqueConstraint(fields=["answer", "option"], name="choice_answer_option_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.answer_id}: {self.option_id}"
