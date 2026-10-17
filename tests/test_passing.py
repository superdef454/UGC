import pytest
from rest_framework.test import APIClient

from analytics.models import StatisticsOutbox
from attempts.models import Answer, Attempt
from quizzes.models import Quiz
from tests.conftest import client_for, make_draft, option_id, question_id

pytestmark = pytest.mark.django_db


def next_question_url(quiz: Quiz) -> str:
    return f"/api/quizzes/{quiz.pk}/next-question/"


def answers_url(quiz: Quiz) -> str:
    return f"/api/quizzes/{quiz.pk}/answers/"


def test_first_request_starts_attempt(respondent_api, respondent, quiz):
    response = respondent_api.get(next_question_url(quiz))

    assert response.status_code == 200
    body = response.json()
    assert body["question"]["id"] == question_id(quiz, 0)
    assert [o["text"] for o in body["question"]["options"]] == [
        "Да",
        "Нет",
        "У меня непереносимость лактозы",
    ]
    assert body["progress"] == {"answered": 0, "total": 3, "percent": 0}
    assert Attempt.objects.filter(user=respondent, quiz=quiz).count() == 1


def test_full_pass(respondent_api, respondent, quiz):
    respondent_api.get(next_question_url(quiz))

    first = respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 0), "custom_text": "Только с базиликом"},
        format="json",
    )
    assert first.status_code == 200
    assert first.json()["question"]["id"] == question_id(quiz, 1)

    second = respondent_api.post(
        answers_url(quiz),
        {
            "question_id": question_id(quiz, 1),
            "option_ids": [option_id(quiz, 1, 0), option_id(quiz, 1, 2)],
        },
        format="json",
    )
    assert second.json()["progress"]["answered"] == 2

    # Третий вопрос необязательный - пропускаем пустым ответом.
    last = respondent_api.post(
        answers_url(quiz), {"question_id": question_id(quiz, 2)}, format="json"
    )

    body = last.json()
    assert body["is_finished"] is True
    assert body["question"] is None
    assert body["progress"] == {"answered": 3, "total": 3, "percent": 100}

    attempt = Attempt.objects.get(user=respondent, quiz=quiz)
    assert attempt.status == Attempt.Status.FINISHED
    assert attempt.finished_at is not None
    assert StatisticsOutbox.objects.filter(attempt=attempt).exists()


def test_attempt_can_be_continued(respondent_api, quiz):
    respondent_api.get(next_question_url(quiz))
    respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 0), "option_ids": [option_id(quiz, 0, 1)]},
        format="json",
    )

    # Пользователь ушёл и вернулся - продолжает со второго вопроса.
    response = respondent_api.get(next_question_url(quiz))

    assert response.json()["question"]["id"] == question_id(quiz, 1)
    assert response.json()["progress"]["answered"] == 1

    in_progress = respondent_api.get("/api/attempts/?status=in_progress").json()["results"]
    assert [(a["quiz_id"], a["answered_count"], a["questions_count"]) for a in in_progress] == [
        (quiz.pk, 1, 3)
    ]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"option_ids": []}, "обязательный"),
        ({"option_ids": [0, 1]}, "только один"),
        ({"option_ids": [999_999]}, "не относятся"),
    ],
)
def test_invalid_answers(respondent_api, quiz, payload, error):
    respondent_api.get(next_question_url(quiz))
    options = {0: option_id(quiz, 0, 0), 1: option_id(quiz, 0, 1)}
    payload = {
        "question_id": question_id(quiz, 0),
        "option_ids": [options.get(i, i) for i in payload["option_ids"]],
    }

    response = respondent_api.post(answers_url(quiz), payload, format="json")

    assert response.status_code == 400
    assert error in response.json()["detail"]
    assert not Answer.objects.exists()


def test_custom_answer_only_where_allowed(respondent_api, quiz):
    respondent_api.get(next_question_url(quiz))
    respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 0), "option_ids": [option_id(quiz, 0, 0)]},
        format="json",
    )

    response = respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 1), "custom_text": "Кабачки"},
        format="json",
    )

    assert response.status_code == 400
    assert "не предусмотрен" in response.json()["detail"]


def test_cannot_skip_ahead(respondent_api, quiz):
    respondent_api.get(next_question_url(quiz))

    response = respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 2), "option_ids": [option_id(quiz, 2, 0)]},
        format="json",
    )

    assert response.status_code == 400
    assert "текущий вопрос" in response.json()["detail"]


def test_quiz_cannot_be_passed_twice(respondent_api, respondent, quiz):
    respondent_api.get(next_question_url(quiz))
    for index, options in enumerate([[option_id(quiz, 0, 0)], [option_id(quiz, 1, 0)], []]):
        respondent_api.post(
            answers_url(quiz),
            {"question_id": question_id(quiz, index), "option_ids": options},
            format="json",
        )

    again = respondent_api.get(next_question_url(quiz))
    answer_again = respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 0), "option_ids": [option_id(quiz, 0, 0)]},
        format="json",
    )

    assert again.json()["is_finished"] is True
    assert answer_again.status_code == 400
    assert Attempt.objects.filter(user=respondent).count() == 1


def test_closed_quiz_rejects_answers(respondent_api, author_api, quiz):
    respondent_api.get(next_question_url(quiz))
    author_api.post(f"/api/my/quizzes/{quiz.pk}/close/")

    response = respondent_api.post(
        answers_url(quiz),
        {"question_id": question_id(quiz, 0), "option_ids": [option_id(quiz, 0, 0)]},
        format="json",
    )

    assert response.status_code == 400
    assert "закрыт" in response.json()["detail"]


def test_draft_is_not_available(author, respondent, quiz_payload):
    draft = make_draft(author, quiz_payload)

    response = client_for(respondent).get(next_question_url(draft))

    assert response.status_code == 404


def test_anonymous_and_unknown_users_are_rejected(quiz):
    unknown = APIClient()
    unknown.credentials(HTTP_X_USER_ID="999999")

    assert unknown.get(next_question_url(quiz)).status_code == 401
    assert APIClient().get(next_question_url(quiz)).status_code == 401
