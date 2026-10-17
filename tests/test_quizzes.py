import pytest

from quizzes.models import Question, Quiz
from tests.conftest import make_draft

pytestmark = pytest.mark.django_db

QUIZZES = "/api/v1/quizzes/"


def test_create_quiz_keeps_order(author_api, author, quiz_payload):
    response = author_api.post(QUIZZES, quiz_payload, format="json")

    assert response.status_code == 201
    body = response.json()
    assert response["Location"] == f"{QUIZZES}{body['id']}/"
    assert body["status"] == "draft"
    assert [q["text"] for q in body["questions"]] == [q["text"] for q in quiz_payload["questions"]]
    assert [q["order"] for q in body["questions"]] == [1, 2, 3]
    assert [o["text"] for o in body["questions"][1]["options"]] == ["Огурцы", "Помидоры", "Перец"]
    assert Quiz.objects.get().author == author


def test_question_needs_options_or_custom_answer(author_api, quiz_payload):
    quiz_payload["questions"][0]["options"] = []
    quiz_payload["questions"][0]["allow_custom_answer"] = False

    response = author_api.post(QUIZZES, quiz_payload, format="json")

    assert response.status_code == 400
    assert not Quiz.objects.exists()


def test_publish(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)

    response = author_api.post(f"{QUIZZES}{draft.pk}/publish/")
    again = author_api.post(f"{QUIZZES}{draft.pk}/publish/")

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["published_at"] is not None
    assert again.status_code == 409


def test_draft_is_visible_only_to_author(author_api, respondent_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)

    assert author_api.get(f"{QUIZZES}{draft.pk}/").status_code == 200
    assert respondent_api.get(f"{QUIZZES}{draft.pk}/").status_code == 404
    assert respondent_api.post(f"{QUIZZES}{draft.pk}/publish/").status_code == 404


def test_published_quiz_is_visible_to_everyone(respondent_api, quiz):
    response = respondent_api.get(f"{QUIZZES}{quiz.pk}/")

    assert response.status_code == 200
    assert len(response.json()["questions"]) == 3


def test_reorder_questions(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)
    first, second, third = draft.questions.order_by("order").values_list("pk", flat=True)

    # Перестановка, при которой порядок на время совпадает, - работает за счёт
    # отложенной проверки уникальности (quiz, order).
    response = author_api.put(
        f"{QUIZZES}{draft.pk}/questions/order/", {"ids": [third, first, second]}, format="json"
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

    response = author_api.put(
        f"{QUIZZES}{draft.pk}/questions/{question.pk}/options/order/",
        {"ids": ids[::-1]},
        format="json",
    )

    assert response.status_code == 204
    assert list(question.options.order_by("order").values_list("pk", flat=True)) == ids[::-1]


def test_reorder_options_of_question_from_other_quiz(author_api, author, quiz_payload, quiz):
    draft = make_draft(author, quiz_payload)
    foreign = quiz.questions.first()

    response = author_api.put(
        f"{QUIZZES}{draft.pk}/questions/{foreign.pk}/options/order/", {"ids": [1]}, format="json"
    )

    assert response.status_code == 404


def test_reorder_requires_all_ids(author_api, author, quiz_payload):
    draft = make_draft(author, quiz_payload)
    ids = list(draft.questions.values_list("pk", flat=True))

    response = author_api.put(
        f"{QUIZZES}{draft.pk}/questions/order/", {"ids": ids[:2]}, format="json"
    )

    assert response.status_code == 400


def test_published_quiz_is_frozen(author_api, quiz):
    ids = list(Question.objects.filter(quiz=quiz).values_list("pk", flat=True))

    response = author_api.put(
        f"{QUIZZES}{quiz.pk}/questions/order/", {"ids": ids[::-1]}, format="json"
    )

    assert response.status_code == 409


def test_catalog_and_authored_lists(author_api, respondent_api, author, quiz_payload, quiz):
    make_draft(author, quiz_payload)

    catalog = respondent_api.get(QUIZZES).json()["results"]
    authored = author_api.get(f"{QUIZZES}?author=me").json()["results"]
    drafts = author_api.get(f"{QUIZZES}?author=me&status=draft").json()["results"]
    nothing = respondent_api.get(f"{QUIZZES}?author=me").json()["results"]

    assert [(q["id"], q["questions_count"]) for q in catalog] == [(quiz.pk, 3)]
    assert sorted(q["status"] for q in authored) == ["draft", "published"]
    assert [q["status"] for q in drafts] == ["draft"]
    assert nothing == []


@pytest.mark.parametrize("query", ["author=42", "author=me&status=unknown"])
def test_list_rejects_bad_filters(author_api, query):
    assert author_api.get(f"{QUIZZES}?{query}").status_code == 400
