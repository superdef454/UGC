from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from analytics.models import QuizStatistics, StatisticsOutbox
from analytics.schemas import QuizStatsData
from attempts.models import Answer, AnswerChoice, Attempt


def enqueue_finished_attempt(attempt: Attempt) -> None:
    """Ставит завершённое прохождение в очередь на подсчёт статистики.

    Вызывать внутри той же транзакции, в которой прохождение завершается.
    """
    StatisticsOutbox.objects.create(attempt=attempt)


MAX_QUESTION_TIME = timedelta(minutes=10)


@dataclass
class _QuizDelta:
    attempts_count: int = 0
    total_duration_ms: int = 0
    data: QuizStatsData = field(default_factory=QuizStatsData)


def _ms(delta: timedelta) -> int:
    """Миллисекунды, не больше MAX_QUESTION_TIME.

    Прохождение можно бросить и продолжить через день - без ограничения один
    такой ответ испортил бы среднее время по вопросу и по опросу.
    """
    return max(0, round(min(delta, MAX_QUESTION_TIME).total_seconds() * 1000))


def _collect_deltas(attempt_ids: list[int]) -> dict[int, _QuizDelta]:
    """Считает прирост статистики по пачке прохождений, по опросам."""
    attempts = {
        attempt.pk: attempt
        for attempt in Attempt.objects.filter(pk__in=attempt_ids).only(
            "id", "quiz_id", "started_at"
        )
    }
    choices: dict[int, list[int]] = defaultdict(list)
    for answer_id, option_id in AnswerChoice.objects.filter(
        answer__attempt_id__in=attempt_ids
    ).values_list("answer_id", "option_id"):
        choices[answer_id].append(option_id)

    deltas: dict[int, _QuizDelta] = defaultdict(_QuizDelta)
    for attempt in attempts.values():
        deltas[attempt.quiz_id].attempts_count += 1

    # Время на вопрос - от предыдущего ответа (для первого - от начала прохождения).
    # Время прохождения - сумма времени на вопросы, то есть тоже без долгих пауз.
    previous_at: dict[int, datetime] = {pk: attempt.started_at for pk, attempt in attempts.items()}
    answers = (
        Answer.objects.filter(attempt_id__in=attempt_ids)
        .order_by("attempt_id", "answered_at", "id")
        .values_list("id", "attempt_id", "question_id", "custom_text", "answered_at")
    )
    for answer_id, attempt_id, question_id, custom_text, answered_at in answers:
        delta = deltas[attempts[attempt_id].quiz_id]
        stats = delta.data.question(question_id)
        spent = _ms(answered_at - previous_at[attempt_id])
        stats.total_time_ms += spent
        delta.total_duration_ms += spent
        previous_at[attempt_id] = answered_at

        picked = choices.get(answer_id, [])
        if not picked and not custom_text:
            stats.skipped_count += 1
            continue
        stats.answers_count += 1
        stats.custom_count += bool(custom_text)
        for option_id in picked:
            stats.options[option_id] = stats.options.get(option_id, 0) + 1

    return deltas


def _apply_deltas(deltas: dict[int, _QuizDelta]) -> None:
    quiz_ids = sorted(deltas)
    QuizStatistics.objects.bulk_create(
        [QuizStatistics(quiz_id=quiz_id) for quiz_id in quiz_ids], ignore_conflicts=True
    )
    # Строки лочим строго по порядку quiz_id - тогда параллельные воркеры
    # не поймают дедлок, захватывая одни и те же опросы в разном порядке.
    rows = list(
        QuizStatistics.objects.select_for_update().filter(quiz_id__in=quiz_ids).order_by("quiz_id")
    )
    now = timezone.now()
    for row in rows:
        delta = deltas[row.quiz_id]
        data = QuizStatsData.model_validate(row.data)
        data.merge(delta.data)
        row.data = data.model_dump(mode="json")
        row.attempts_count += delta.attempts_count
        row.total_duration_ms += delta.total_duration_ms
        row.updated_at = now
    QuizStatistics.objects.bulk_update(
        rows, ["attempts_count", "total_duration_ms", "data", "updated_at"]
    )


def process_outbox_batch(batch_size: int = settings.STATISTICS_BATCH_SIZE) -> int:
    """Учитывает в статистике одну пачку прохождений из очереди.

    Всё в одной транзакции: взяли пачку, прибавили, удалили из очереди.
    Если воркер упадёт посередине, транзакция откатится и пачка останется
    в очереди - ничего не потеряется и не посчитается дважды. SKIP LOCKED
    позволяет запускать несколько воркеров: каждый берёт свою пачку.

    Returns:
        Сколько прохождений учтено.
    """
    with transaction.atomic():
        events = list(
            StatisticsOutbox.objects.select_for_update(skip_locked=True)
            .order_by("id")
            .values_list("id", "attempt_id")[:batch_size]
        )
        if not events:
            return 0

        _apply_deltas(_collect_deltas([attempt_id for _, attempt_id in events]))
        StatisticsOutbox.objects.filter(pk__in=[event_id for event_id, _ in events]).delete()
    return len(events)


# TODO: команда полного пересчёта статистики опроса из ответов - на случай багов
# в подсчёте. Считает то же самое, что _collect_deltas, но по всем прохождениям
# опроса, и перезаписывает строку целиком.
