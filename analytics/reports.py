"""Отчёт по опросу для автора: готовая статистика + структура опроса."""

from dataclasses import dataclass
from datetime import datetime

from analytics.models import QuizStatistics
from analytics.schemas import QuestionStats, QuizStatsData
from quizzes.models import Quiz
from quizzes.services import aget_own_quiz
from quizzes.structure import QuestionItem, QuizStructure, aget_quiz_structure
from users.models import User


@dataclass(frozen=True, slots=True)
class OptionReport:
    """Вариант ответа: сколько раз выбрали."""

    id: int
    text: str
    count: int
    percent: int
    is_top: bool


@dataclass(frozen=True, slots=True)
class QuestionReport:
    """Вопрос: ответы, пропуски, время."""

    id: int
    order: int
    text: str
    type: str
    answers_count: int
    skipped_count: int
    custom_count: int
    avg_time_seconds: float | None
    is_slowest: bool
    options: tuple[OptionReport, ...]


@dataclass(frozen=True, slots=True)
class QuizReport:
    """Статистика опроса целиком."""

    quiz_id: int
    title: str
    status: str
    attempts_count: int
    avg_duration_seconds: float | None
    questions: tuple[QuestionReport, ...]
    updated_at: datetime | None


def _avg_time(stats: QuestionStats) -> float | None:
    seen = stats.answers_count + stats.skipped_count
    return round(stats.total_time_ms / seen / 1000, 1) if seen else None


def _question_report(
    question: QuestionItem, stats: QuestionStats, *, slowest: bool
) -> QuestionReport:
    top = max(stats.options.values(), default=0)
    return QuestionReport(
        id=question.id,
        order=question.order,
        text=question.text,
        type=question.type,
        answers_count=stats.answers_count,
        skipped_count=stats.skipped_count,
        custom_count=stats.custom_count,
        avg_time_seconds=_avg_time(stats),
        is_slowest=slowest,
        options=tuple(
            OptionReport(
                id=option.id,
                text=option.text,
                count=(count := stats.options.get(option.id, 0)),
                percent=round(count * 100 / stats.answers_count) if stats.answers_count else 0,
                is_top=0 < count == top,
            )
            for option in question.options
        ),
    )


def build_report(
    quiz: Quiz, structure: QuizStructure, statistics: QuizStatistics | None
) -> QuizReport:
    """Собирает отчёт. Если прохождений ещё не было - отчёт с нулями."""
    data = QuizStatsData.model_validate(statistics.data) if statistics else QuizStatsData()
    per_question = {q.id: data.questions.get(q.id, QuestionStats()) for q in structure.questions}

    times = {qid: t for qid, stats in per_question.items() if (t := _avg_time(stats)) is not None}
    slowest_id = max(times, key=times.__getitem__) if times else None

    avg_duration = statistics.avg_duration if statistics else None
    return QuizReport(
        quiz_id=quiz.pk,
        title=quiz.title,
        status=quiz.status,
        attempts_count=statistics.attempts_count if statistics else 0,
        avg_duration_seconds=round(avg_duration.total_seconds(), 1) if avg_duration else None,
        questions=tuple(
            _question_report(q, per_question[q.id], slowest=q.id == slowest_id)
            for q in structure.questions
        ),
        updated_at=statistics.updated_at if statistics else None,
    )


async def aget_quiz_report(user: User, quiz_id: int) -> QuizReport:
    """Отчёт по опросу. Доступен только автору."""
    quiz = await aget_own_quiz(user, quiz_id)
    statistics = await QuizStatistics.objects.filter(quiz=quiz).afirst()
    structure = await aget_quiz_structure(quiz)
    return build_report(quiz, structure, statistics)
