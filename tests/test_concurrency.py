"""Гонки: параллельные запросы в настоящих транзакциях, каждый поток со своим соединением."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection

from analytics.models import QuizStatistics, StatisticsOutbox
from analytics.services import process_outbox_batch
from attempts.models import Answer
from attempts.services import submit_answer
from core.exceptions import DomainError
from tests.conftest import client_for, option_id, question_id
from tests.test_statistics import pass_quiz
from users.models import User

pytestmark = pytest.mark.django_db(transaction=True)


def run_together[T](func: Callable[[], T], times: int) -> list[T]:
    barrier = threading.Barrier(times)

    def worker() -> T:
        barrier.wait()
        try:
            return func()
        finally:
            connection.close()

    with ThreadPoolExecutor(times) as pool:
        return list(pool.map(lambda _: worker(), range(times)))


def test_double_submit_saves_one_answer(respondent, quiz):
    client_for(respondent).get(f"/api/quizzes/{quiz.pk}/next-question/")

    def send() -> str:
        try:
            submit_answer(respondent, quiz.pk, question_id(quiz, 0), [option_id(quiz, 0, 0)])
        except DomainError:
            return "rejected"
        return "ok"

    results = run_together(send, 5)

    assert sorted(results) == ["ok"] + ["rejected"] * 4
    assert Answer.objects.count() == 1


def test_parallel_workers_count_each_attempt_once(quiz):
    for index in range(12):
        pass_quiz(
            User.objects.create_user(f"user{index}"),
            quiz,
            [{"option_ids": [option_id(quiz, 0, 0)]}, {"option_ids": [option_id(quiz, 1, 1)]}, {}],
            seconds=[1, 2, 3],
        )

    def drain() -> int:
        total = 0
        while processed := process_outbox_batch(batch_size=2):
            total += processed
        return total

    assert sum(run_together(drain, 3)) == 12
    stats = QuizStatistics.objects.get(quiz=quiz)
    assert stats.attempts_count == 12
    assert stats.data["questions"][str(question_id(quiz, 0))]["options"] == {
        str(option_id(quiz, 0, 0)): 12
    }
    assert not StatisticsOutbox.objects.exists()
