import pytest
from django.test import Client

from analytics.services import process_outbox_batch
from attempts.models import Answer, Attempt
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
    intro = browser.get(f"/quizzes/{quiz.pk}/")
    assert "Начать" in intro.content.decode()
    assert not Attempt.objects.exists()  # просмотр страницы ничего не создаёт

    assert browser.post(f"/quizzes/{quiz.pk}/start/").status_code == 302
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
    browser.post(f"/quizzes/{quiz.pk}/start/")

    # Выбран «Свой вариант», но текст не написан - обязательный вопрос без ответа.
    response = browser.post(
        f"/quizzes/{quiz.pk}/",
        {
            "question_id": question_id(quiz, 0),
            "option": ["custom"],
            "custom_text": "  ",
            "exclusive_custom": "1",
        },
    )

    html = response.content.decode()
    assert response.status_code == 400
    assert "обязательный" in html
    assert 'value="custom" checked' in html


def test_custom_text_is_kept_but_option_wins(browser, quiz):
    # Пользователь написал свой ответ, потом передумал и выбрал вариант - текст
    # остался в форме, но отправляется только выбранный вариант.
    browser.post(f"/quizzes/{quiz.pk}/start/")
    picked = option_id(quiz, 0, 1)

    response = browser.post(
        f"/quizzes/{quiz.pk}/",
        {
            "question_id": question_id(quiz, 0),
            "option": [picked],
            "custom_text": "Сырники",
            "exclusive_custom": "1",
        },
    )

    assert response.status_code == 302
    answer = Answer.objects.get()
    assert answer.custom_text == ""
    assert list(answer.selected_options.values_list("pk", flat=True)) == [picked]


def test_custom_choice_sends_text(browser, quiz):
    browser.post(f"/quizzes/{quiz.pk}/start/")

    response = browser.post(
        f"/quizzes/{quiz.pk}/",
        {
            "question_id": question_id(quiz, 0),
            "option": ["custom"],
            "custom_text": "Сырники",
            "exclusive_custom": "1",
        },
    )

    assert response.status_code == 302
    answer = Answer.objects.get()
    assert answer.custom_text == "Сырники"
    assert not answer.selected_options.exists()


def test_double_click_is_not_an_error(browser, quiz):
    browser.post(f"/quizzes/{quiz.pk}/start/")
    data = {"question_id": question_id(quiz, 0), "option": [option_id(quiz, 0, 0)]}

    first = browser.post(f"/quizzes/{quiz.pk}/", data)
    second = browser.post(f"/quizzes/{quiz.pk}/", data)

    assert first.status_code == second.status_code == 302


def test_author_pages(author, quiz):
    client = Client()
    client.force_login(author)
    process_outbox_batch()

    assert client.get("/quizzes/authored/").status_code == 200
    assert client.get(f"/quizzes/{quiz.pk}/manage/").status_code == 200
    assert client.get(f"/quizzes/{quiz.pk}/statistics/").status_code == 200
    assert client.get("/quizzes/new/").status_code == 200


def test_statistics_page_is_only_for_author(browser, quiz):
    assert browser.get(f"/quizzes/{quiz.pk}/statistics/").status_code == 404
