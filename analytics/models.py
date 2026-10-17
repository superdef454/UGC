from datetime import timedelta

from django.db import models

from attempts.models import Attempt
from quizzes.models import Quiz


class QuizStatistics(models.Model):
    """Готовая статистика по опросу.

    Пишет её только воркер (см. ``analytics.services.process_outbox_batch``),
    при чтении ничего не пересчитывается. Детализация по вопросам лежит в json,
    схема описана в ``analytics.schemas``. То, по чему нужно сортировать, -
    в обычных колонках.
    """

    quiz = models.OneToOneField(
        Quiz, on_delete=models.CASCADE, primary_key=True, related_name="statistics"
    )
    attempts_count = models.PositiveBigIntegerField("завершённых прохождений", default=0)
    total_duration_ms = models.PositiveBigIntegerField(default=0)
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "статистика опроса"
        verbose_name_plural = "статистика опросов"
        indexes = [
            models.Index(fields=["-attempts_count"], name="stats_attempts_count_idx"),
        ]

    def __str__(self) -> str:
        return f"Статистика: {self.quiz_id}"

    @property
    def avg_duration(self) -> timedelta | None:
        """Среднее время прохождения."""
        if not self.attempts_count:
            return None
        return timedelta(milliseconds=self.total_duration_ms / self.attempts_count)


class StatisticsOutbox(models.Model):
    """Очередь завершённых прохождений, которые ещё не учтены в статистике.

    Запись создаётся в той же транзакции, что и завершение прохождения,
    поэтому событие нельзя ни потерять, ни получить лишнее.
    """

    attempt = models.OneToOneField(Attempt, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "событие для статистики"
        verbose_name_plural = "очередь статистики"

    def __str__(self) -> str:
        return f"Прохождение {self.attempt_id}"
