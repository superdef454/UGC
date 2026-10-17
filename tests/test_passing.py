import pytest
from rest_framework.test import APIClient

from analytics.models import StatisticsOutbox
from attempts.models import Answer, Attempt
from quizzes.models import Quiz
from tests.conftest import client_for, make_draft, option_id, question_id
from users.models import User

pytestmark = pytest.mark.django_db


def attempt_url(quiz: Quiz) -> str:
    return f"/api/v1/quizzes/{quiz.pk}/attempt/"


def answers_url(quiz: Quiz) -> str:
    return f"/api/v1/quizzes/{quiz.pk}/attempt/answers/"


def answer(client: APIClient, quiz: Quiz, index: int, **payload):
    return client.post(
        answers_url(quiz), {"question_id": question_id(quiz, index), **payload}, format="json"
    )


def test_start_attempt(respondent_api, respondent, quiz):
    response = respondent_api.post(attempt_url(quiz))

    assert response.status_code == 201
    assert response["Location"] == attempt_url(quiz)
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["next_question"]["id"] == question_id(quiz, 0)
    assert [o["text"] for o in body["next_question"]["options"]] == [
        "Да",
        "Нет",
        "У меня непереносимость лактозы",
    ]
    assert body["progress"] == {"answered": 0, "total": 3, "percent": 0}
    assert Attempt.objects.filter(user=respondent, quiz=quiz).count() == 1


def test_start_is_idempotent(respondent_api, respondent, quiz):
    respondent_api.post(attempt_url(quiz))

    again = respondent_api.post(attempt_url(quiz))

    assert again.status_code == 200
    assert Attempt.objects.filter(user=respondent, quiz=quiz).count() == 1


def test_get_does_not_start_attempt(respondent_api, quiz):
    response = respondent_api.get(attempt_url(quiz))

    assert response.status_code == 404
    assert not Attempt.objects.exists()


def test_full_pass(respondent_api, respondent, quiz):
    respondent_api.post(attempt_url(quiz))

    first = answer(respondent_api, quiz, 0, custom_text="Только с базиликом")
    assert first.status_code == 200
    assert first.json()["next_question"]["id"] == question_id(quiz, 1)

    second = answer(
        respondent_api, quiz, 1, option_ids=[option_id(quiz, 1, 0), option_id(quiz, 1, 2)]
    )
    assert second.json()["progress"]["answered"] == 2

    # Третий вопрос необязательный - пропускаем пустым ответом.
    body = answer(respondent_api, quiz, 2).json()

    assert body["status"] == "finished"
    assert body["next_question"] is None
    assert body["progress"] == {"answered": 3, "total": 3, "percent": 100}

    attempt = Attempt.objects.get(user=respondent, quiz=quiz)
    assert attempt.status == Attempt.Status.FINISHED
    assert attempt.finished_at is not None
    assert StatisticsOutbox.objects.filter(attempt=attempt).exists()


def test_attempt_can_be_continued(respondent_api, quiz):
    respondent_api.post(attempt_url(quiz))
    answer(respondent_api, quiz, 0, option_ids=[option_id(quiz, 0, 1)])

    # Пользователь ушёл и вернулся - продолжает со второго вопроса.
    response = respondent_api.get(attempt_url(quiz))

    assert response.json()["next_question"]["id"] == question_id(quiz, 1)
    assert response.json()["progress"]["answered"] == 1

    in_progress = respondent_api.get("/api/v1/attempts/?status=in_progress").json()["results"]
    assert [(a["quiz_id"], a["answered_count"], a["questions_count"]) for a in in_progress] == [
        (quiz.pk, 1, 3)
    ]


@pytest.mark.parametrize(
    ("picked", "error"),
    [
        ([], "обязательный"),
        ([0, 1], "только один"),
        ([999_999], "не относятся"),
    ],
)
def test_invalid_answers(respondent_api, quiz, picked, error):
    respondent_api.post(attempt_url(quiz))
    options = {0: option_id(quiz, 0, 0), 1: option_id(quiz, 0, 1)}

    response = answer(respondent_api, quiz, 0, option_ids=[options.get(i, i) for i in picked])

    assert response.status_code == 400
    assert error in response.json()["detail"]
    assert not Answer.objects.exists()


def test_custom_answer_only_where_allowed(respondent_api, quiz):
    respondent_api.post(attempt_url(quiz))
    answer(respondent_api, quiz, 0, option_ids=[option_id(quiz, 0, 0)])

    response = answer(respondent_api, quiz, 1, custom_text="Кабачки")

    assert response.status_code == 400
    assert "не предусмотрен" in response.json()["detail"]


def test_cannot_skip_ahead(respondent_api, quiz):
    respondent_api.post(attempt_url(quiz))

    response = answer(respondent_api, quiz, 2, option_ids=[option_id(quiz, 2, 0)])

    assert response.status_code == 409
    assert "текущий вопрос" in response.json()["detail"]


def test_answer_without_attempt(respondent_api, quiz):
    response = answer(respondent_api, quiz, 0, option_ids=[option_id(quiz, 0, 0)])

    assert response.status_code == 404


def test_quiz_cannot_be_passed_twice(respondent_api, respondent, quiz):
    respondent_api.post(attempt_url(quiz))
    for index, options in enumerate([[option_id(quiz, 0, 0)], [option_id(quiz, 1, 0)], []]):
        answer(respondent_api, quiz, index, option_ids=options)

    again = respondent_api.post(attempt_url(quiz))
    answer_again = answer(respondent_api, quiz, 0, option_ids=[option_id(quiz, 0, 0)])

    assert again.status_code == 200
    assert again.json()["status"] == "finished"
    assert answer_again.status_code == 409
    assert Attempt.objects.filter(user=respondent).count() == 1


def test_closed_quiz_rejects_answers_and_new_attempts(respondent_api, author_api, quiz):
    respondent_api.post(attempt_url(quiz))
    author_api.post(f"/api/v1/quizzes/{quiz.pk}/close/")

    response = answer(respondent_api, quiz, 0, option_ids=[option_id(quiz, 0, 0)])
    newcomer = client_for(User.objects.create_user("late")).post(attempt_url(quiz))

    assert response.status_code == 409
    assert "закрыт" in response.json()["detail"]
    assert newcomer.status_code == 409


def test_draft_is_not_available(author, respondent, quiz_payload):
    draft = make_draft(author, quiz_payload)

    response = client_for(respondent).post(attempt_url(draft))

    assert response.status_code == 404


def test_anonymous_and_unknown_users_are_rejected(quiz):
    unknown = APIClient()
    unknown.credentials(HTTP_X_USER_ID="999999")

    assert unknown.get(attempt_url(quiz)).status_code == 401
    assert APIClient().get(attempt_url(quiz)).status_code == 401
