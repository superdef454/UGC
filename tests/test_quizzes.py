import pytest

from quizzes.models import Question, Quiz
from tests.conftest import make_draft

pytestmark = pytest.mark.django_db


def test_create_quiz_keeps_order(author_api, author, quiz_payload):
    response = author_api.post("/api/my/quizzes/", quiz_payload, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert [q["text"] for q in body["questions"]] == [q["text"] for q in quiz_payload["questions"]]
    assert [q["order"] for q in body["questions"]] == [1, 2, 3]
    assert [o["text"] for o in body["questions"][1]["options"]] == ["Огурцы", "Помидоры", "Перец"]
    assert Quiz.objects.get().author == author


def test_question_needs_options_or_custom_answer(author_api, quiz_payload):
    quiz_payload["questions"][0]["options"] = []
    quiz_payload["questions"][0]["allow_custom_answer"] = False

    response = author_api.post("/api/my/quizzes/", quiz_payload, format="json")

    assert response.status_code == 400
    assert not Quiz.objects.exists()


def test_publish(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)

    response = author_api.post(f"/api/my/quizzes/{draft.pk}/publish/")
    again = author_api.post(f"/api/my/quizzes/{draft.pk}/publish/")

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["published_at"] is not None
    assert again.status_code == 400


def test_only_author_can_manage_quiz(respondent_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)

    assert respondent_api.post(f"/api/my/quizzes/{draft.pk}/publish/").status_code == 404
    assert respondent_api.get(f"/api/my/quizzes/{draft.pk}/").status_code == 404


def test_reorder_questions(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)
    first, second, third = draft.questions.order_by("order").values_list("pk", flat=True)

    # Перестановка, при которой порядок на время совпадает, - работает за счёт
    # отложенной проверки уникальности (quiz, order).
    response = author_api.post(
        f"/api/my/quizzes/{draft.pk}/questions/order/",
        {"ids": [third, first, second]},
        format="json",
    )

    assert response.status_code == 204
    assert list(draft.questions.order_by("order").values_list("pk", flat=True)) == [
        third,
        first,
        second,
    ]


def test_reorder_options(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)
    question = draft.questions.get(order=1)
    ids = list(question.options.order_by("order").values_list("pk", flat=True))

    response = author_api.post(
        f"/api/my/questions/{question.pk}/options/order/", {"ids": ids[::-1]}, format="json"
    )

    assert response.status_code == 204
    assert list(question.options.order_by("order").values_list("pk", flat=True)) == ids[::-1]


def test_reorder_requires_all_ids(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)
    ids = list(draft.questions.values_list("pk", flat=True))

    response = author_api.post(
        f"/api/my/quizzes/{draft.pk}/questions/order/", {"ids": ids[:2]}, format="json"
    )

    assert response.status_code == 400


def test_published_quiz_is_frozen(author_api, quiz):
    ids = list(Question.objects.filter(quiz=quiz).values_list("pk", flat=True))

    response = author_api.post(
        f"/api/my/quizzes/{quiz.pk}/questions/order/", {"ids": ids[::-1]}, format="json"
    )

    assert response.status_code == 400


def test_lists(author_api, respondent_api, author, quiz_payload, quiz):
    make_draft(author, quiz_payload)

    available = respondent_api.get("/api/quizzes/").json()["results"]
    mine = author_api.get("/api/my/quizzes/").json()["results"]

    assert [(q["id"], q["questions_count"]) for q in available] == [(quiz.pk, 3)]
    assert sorted(q["status"] for q in mine) == ["draft", "published"]
