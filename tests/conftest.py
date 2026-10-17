from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from quizzes.models import Quiz
from quizzes.serializers import QuizCreateSerializer
from quizzes.services import create_quiz, publish_quiz
from users.models import User


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def author(db) -> User:
    return User.objects.create_user("author", password="pass12345")


@pytest.fixture
def respondent(db) -> User:
    return User.objects.create_user("respondent", password="pass12345")


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_USER_ID=str(user.pk))
    return client


@pytest.fixture
def author_api(author) -> APIClient:
    return client_for(author)


@pytest.fixture
def respondent_api(respondent) -> APIClient:
    return client_for(respondent)


@pytest.fixture
def quiz_payload() -> dict[str, Any]:
    return {
        "title": "Овощи",
        "description": "Короткий опрос про овощи",
        "questions": [
            {
                "text": "Ты любишь буратту с помидорами?",
                "type": "single",
                "allow_custom_answer": True,
                "options": [
                    {"text": "Да"},
                    {"text": "Нет"},
                    {"text": "У меня непереносимость лактозы"},
                ],
            },
            {
                "text": "Какие овощи ешь чаще всего?",
                "type": "multiple",
                "options": [{"text": "Огурцы"}, {"text": "Помидоры"}, {"text": "Перец"}],
            },
            {
                "text": "Ты любишь огуречный салат?",
                "is_required": False,
                "options": [{"text": "Да"}, {"text": "Нет"}, {"text": "Только с уксусом"}],
            },
        ],
    }


def make_draft(author: User, payload: dict[str, Any]) -> Quiz:
    serializer = QuizCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return create_quiz(author, serializer.validated_data)


@pytest.fixture
def quiz(author, quiz_payload) -> Quiz:
    """Опубликованный опрос из трёх вопросов."""
    return publish_quiz(author, make_draft(author, quiz_payload).pk)


def option_id(quiz: Quiz, question_index: int, option_index: int) -> int:
    question = quiz.questions.order_by("order")[question_index]
    return question.options.order_by("order")[option_index].pk


def question_id(quiz: Quiz, question_index: int) -> int:
    return quiz.questions.order_by("order")[question_index].pk
