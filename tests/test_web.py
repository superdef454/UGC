import pytest
from django.test import Client

from analytics.services import process_outbox_batch
from attempts.models import Attempt
from tests.conftest import option_id, question_id

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser(respondent) -> Client:
    client = Client()
    client.force_login(respondent)
    return client


def test_pages_require_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


def test_pass_quiz_in_browser(browser, respondent, quiz):
    page = browser.get(f"/quizzes/{quiz.pk}/")
    assert "Ты любишь буратту с помидорами?" in page.content.decode()

    answers = [
        {"question_id": question_id(quiz, 0), "custom_text": "С базиликом"},
        {"question_id": question_id(quiz, 1), "option": [option_id(quiz, 1, 1)]},
        {"question_id": question_id(quiz, 2), "skip": "1"},
    ]
    for data in answers:
        assert browser.post(f"/quizzes/{quiz.pk}/", data).status_code == 302

    assert "Готово, спасибо!" in browser.get(f"/quizzes/{quiz.pk}/").content.decode()
    assert Attempt.objects.get(user=respondent).status == Attempt.Status.FINISHED


def test_error_keeps_choice(browser, quiz):
    browser.get(f"/quizzes/{quiz.pk}/")
    picked = option_id(quiz, 0, 1)

    response = browser.post(
        f"/quizzes/{quiz.pk}/",
        {"question_id": question_id(quiz, 0), "option": [picked], "custom_text": "Ещё"},
    )

    html = response.content.decode()
    assert response.status_code == 400
    assert "только один вариант" in html
    assert f'value="{picked}" checked' in html


def test_author_pages(author, quiz):
    client = Client()
    client.force_login(author)
    process_outbox_batch()

    assert client.get("/my/").status_code == 200
    assert client.get(f"/my/{quiz.pk}/").status_code == 200
    assert client.get(f"/my/{quiz.pk}/statistics/").status_code == 200
    assert client.get("/my/new/").status_code == 200


def test_statistics_page_is_only_for_author(browser, quiz):
    assert browser.get(f"/my/{quiz.pk}/statistics/").status_code == 403
