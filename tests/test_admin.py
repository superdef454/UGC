import pytest
from django.test import Client

from tests.conftest import make_draft
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_() -> Client:
    client = Client()
    client.force_login(User.objects.create_superuser("root", password="pass12345"))
    return client


def test_published_quiz_is_read_only_in_admin(admin_client_, quiz):
    question = quiz.questions.first()

    # Страница открывается, но только на просмотр - формы сохранения нет.
    page = admin_client_.get(f"/admin/quizzes/quiz/{quiz.pk}/change/")
    response = admin_client_.post(
        f"/admin/quizzes/question/{question.pk}/change/", {"text": "Подменили вопрос"}
    )

    assert page.status_code == 200
    assert 'name="_save"' not in page.content.decode()
    assert response.status_code == 403
    question.refresh_from_db()
    assert question.text != "Подменили вопрос"


def test_draft_is_editable_in_admin(admin_client_, author, quiz_payload):
    draft = make_draft(author, quiz_payload)

    page = admin_client_.get(f"/admin/quizzes/quiz/{draft.pk}/change/")

    assert 'name="_save"' in page.content.decode()


def test_attempts_are_read_only_in_admin(admin_client_):
    assert admin_client_.get("/admin/attempts/attempt/add/").status_code == 403
    assert admin_client_.get("/admin/analytics/statisticsoutbox/add/").status_code == 403
