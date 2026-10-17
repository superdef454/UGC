"""Схема json-поля ``QuizStatistics.data``.

Здесь только суммы и счётчики: их можно считать пачками и складывать.
Средние считаются при чтении.
"""

from typing import Self

from pydantic import BaseModel, Field


class QuestionStats(BaseModel):
    """Статистика одного вопроса."""

    answers_count: int = 0
    skipped_count: int = 0
    custom_count: int = 0
    total_time_ms: int = 0
    options: dict[int, int] = Field(default_factory=dict)  # option_id -> сколько раз выбрали

    def merge(self, other: Self) -> None:
        """Прибавляет к себе другую статистику того же вопроса."""
        self.answers_count += other.answers_count
        self.skipped_count += other.skipped_count
        self.custom_count += other.custom_count
        self.total_time_ms += other.total_time_ms
        for option_id, count in other.options.items():
            self.options[option_id] = self.options.get(option_id, 0) + count


class QuizStatsData(BaseModel):
    """Статистика опроса по вопросам."""

    questions: dict[int, QuestionStats] = Field(default_factory=dict)

    def question(self, question_id: int) -> QuestionStats:
        """Статистика вопроса, создаётся при первом обращении."""
        return self.questions.setdefault(question_id, QuestionStats())

    def merge(self, other: Self) -> None:
        """Прибавляет к себе дельту по пачке прохождений."""
        for question_id, stats in other.questions.items():
            self.question(question_id).merge(stats)
