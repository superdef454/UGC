from datetime import timedelta

import pytest
from django.utils import timezone

from analytics.models import QuizStatistics, StatisticsOutbox
from analytics.services import process_outbox_batch
from attempts.models import Answer, Attempt
from attempts.services import submit_answer
from quizzes.models import Quiz
from tests.conftest import client_for, option_id, question_id
from users.models import User

pytestmark = pytest.mark.django_db


def pass_quiz(user: User, quiz: Quiz, answers: list[dict], seconds: list[int]) -> None:
    """Проходит опрос и выставляет время ответов: ``seconds`` - от начала прохождения."""
    client_for(user).get(f"/api/quizzes/{quiz.pk}/next-question/")
    for index, answer in enumerate(answers):
        submit_answer(user, quiz.pk, question_id(quiz, index), **answer)

    started = timezone.now() - timedelta(hours=1)
    attempt = Attempt.objects.get(user=user, quiz=quiz)
    Attempt.objects.filter(pk=attempt.pk).update(
        started_at=started, finished_at=started + timedelta(seconds=seconds[-1])
    )
    for answer, second in zip(
        Answer.objects.filter(attempt=attempt).order_by("id"), seconds, strict=True
    ):
        Answer.objects.filter(pk=answer.pk).update(answered_at=started + timedelta(seconds=second))


@pytest.fixture
def two_attempts(quiz):
    first = User.objects.create_user("first")
    second = User.objects.create_user("second")
    pass_quiz(
        first,
        quiz,
        [
            {"option_ids": [option_id(quiz, 0, 0)]},
            {"option_ids": [option_id(quiz, 1, 0), option_id(quiz, 1, 2)]},
            {},
        ],
        seconds=[10, 40, 45],
    )
    pass_quiz(
        second,
        quiz,
        [
            {"custom_text": "Только с базиликом"},
            {"option_ids": [option_id(quiz, 1, 0)]},
            {"option_ids": [option_id(quiz, 2, 1)]},
        ],
        seconds=[20, 30, 60],
    )


def test_worker_aggregates_finished_attempts(author_api, quiz, two_attempts):
    assert process_outbox_batch() == 2

    report = author_api.get(f"/api/my/quizzes/{quiz.pk}/statistics/").json()

    assert report["attempts_count"] == 2
    assert report["avg_duration_seconds"] == 52.5

    first, second, third = report["questions"]
    assert (first["answers_count"], first["custom_count"]) == (2, 1)
    assert [(o["count"], o["percent"], o["is_top"]) for o in first["options"]] == [
        (1, 50, True),
        (0, 0, False),
        (0, 0, False),
    ]
    assert first["avg_time_seconds"] == 15.0

    assert [o["count"] for o in second["options"]] == [2, 0, 1]
    assert second["avg_time_seconds"] == 20.0
    assert second["is_slowest"] is True

    assert (third["answers_count"], third["skipped_count"]) == (1, 1)
    assert third["avg_time_seconds"] == 17.5


def test_worker_counts_each_attempt_once(quiz, two_attempts):
    process_outbox_batch()
    snapshot = QuizStatistics.objects.get(quiz=quiz)

    assert process_outbox_batch() == 0
    assert not StatisticsOutbox.objects.exists()
    assert QuizStatistics.objects.get(quiz=quiz).data == snapshot.data


def test_statistics_is_incremental(quiz, two_attempts):
    process_outbox_batch()
    late = User.objects.create_user("late")
    pass_quiz(
        late,
        quiz,
        [{"option_ids": [option_id(quiz, 0, 1)]}, {"option_ids": [option_id(quiz, 1, 1)]}, {}],
        seconds=[5, 10, 15],
    )

    process_outbox_batch()

    stats = QuizStatistics.objects.get(quiz=quiz)
    assert stats.attempts_count == 3
    assert stats.data["questions"][str(question_id(quiz, 2))]["skipped_count"] == 2


def test_unfinished_attempts_are_not_counted(respondent, quiz):
    client_for(respondent).get(f"/api/quizzes/{quiz.pk}/next-question/")
    submit_answer(respondent, quiz.pk, question_id(quiz, 0), option_ids=[option_id(quiz, 0, 0)])

    assert process_outbox_batch() == 0
    assert not QuizStatistics.objects.exists()


def test_empty_report(author_api, quiz):
    report = author_api.get(f"/api/my/quizzes/{quiz.pk}/statistics/").json()

    assert report["attempts_count"] == 0
    assert report["avg_duration_seconds"] is None
    assert all(q["answers_count"] == 0 for q in report["questions"])


def test_statistics_is_only_for_author(respondent_api, quiz):
    response = respondent_api.get(f"/api/my/quizzes/{quiz.pk}/statistics/")

    assert response.status_code == 403


def test_worker_command_drains_queue(quiz, two_attempts):
    from django.core.management import call_command

    call_command("process_statistics", "--once", "--batch-size", "1")

    assert not StatisticsOutbox.objects.exists()
    assert QuizStatistics.objects.get(quiz=quiz).attempts_count == 2
