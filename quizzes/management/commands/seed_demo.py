import random
from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from analytics.services import process_outbox_batch
from attempts.models import Answer, Attempt
from attempts.services import aget_passing_state, submit_answer
from quizzes.models import Quiz
from quizzes.services import QuizInput, create_quiz, publish_quiz
from users.models import User

PASSWORD = "demo-pass"

VEGETABLES: QuizInput = {
    "title": "Овощи",
    "description": "Пример из задания: немного про помидоры и огурцы",
    "questions": [
        {
            "text": "Ты любишь буратту с помидорами?",
            "type": "single",
            "allow_custom_answer": True,
            "is_required": True,
            "options": [
                {"text": "Да"},
                {"text": "Нет"},
                {"text": "У меня непереносимость лактозы"},
            ],
        },
        {
            "text": "Ты любишь огурцы?",
            "type": "single",
            "allow_custom_answer": False,
            "is_required": True,
            "options": [{"text": "Да"}, {"text": "Нет"}, {"text": "Только в коктейлях"}],
        },
        {
            "text": "Какие овощи берёшь чаще всего?",
            "type": "multiple",
            "allow_custom_answer": True,
            "is_required": True,
            "options": [
                {"text": "Помидоры"},
                {"text": "Огурцы"},
                {"text": "Перец"},
                {"text": "Кабачки"},
                {"text": "Морковь"},
            ],
        },
        {
            "text": "Ты любишь помидоры?",
            "type": "single",
            "allow_custom_answer": False,
            "is_required": True,
            "options": [{"text": "Да"}, {"text": "Нет"}, {"text": "Только если гаспачо"}],
        },
        {
            "text": "Ты любишь огуречный салат?",
            "type": "single",
            "allow_custom_answer": False,
            "is_required": False,
            "options": [{"text": "Да"}, {"text": "Нет"}, {"text": "Только с уксусом"}],
        },
    ],
}

CUSTOM_ANSWERS = ["С базиликом", "Только летом", "Спаржа", "Тыква"]


class Command(BaseCommand):
    help = "Демо-данные: пользователи alice и bob, опрос «Овощи» и случайные прохождения"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--bots", type=int, default=40, help="сколько случайных прохождений")

    def handle(self, *args: Any, bots: int, **options: Any) -> None:
        alice = self._user("alice")
        self._user("bob")

        quiz = Quiz.objects.filter(author=alice, title=VEGETABLES["title"]).first()
        if quiz is None:
            quiz = publish_quiz(alice, create_quiz(alice, VEGETABLES).pk)
            self.stdout.write(f"Создан опрос «{quiz.title}» (id={quiz.pk})")

        rng = random.Random(42)
        for index in range(1, bots + 1):
            bot = self._user(f"bot{index}")
            if not Attempt.objects.filter(user=bot, quiz=quiz).exists():
                self._pass(bot, quiz, rng)

        while process_outbox_batch():
            pass
        self.stdout.write(self.style.SUCCESS(f"Готово. Пароль у всех: {PASSWORD}"))

    def _user(self, username: str) -> User:
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _pass(self, user: User, quiz: Quiz, rng: random.Random) -> None:
        state = async_to_sync(aget_passing_state)(user, quiz.pk)
        while (question := state.question) is not None:
            options = [option.id for option in question.options]
            picked = rng.sample(options, rng.randint(1, 3)) if question.is_multiple else []
            custom = ""
            if not question.is_multiple:
                if question.allow_custom_answer and rng.random() < 0.15:
                    custom = rng.choice(CUSTOM_ANSWERS)
                elif question.is_required or rng.random() < 0.7:
                    picked = [rng.choices(options, weights=range(len(options), 0, -1))[0]]
            state = submit_answer(user, quiz.pk, question.id, picked, custom)

        self._spread_in_time(user, quiz, rng)

    @transaction.atomic
    def _spread_in_time(self, user: User, quiz: Quiz, rng: random.Random) -> None:
        """Бот отвечает мгновенно - растягиваем ответы во времени, чтобы статистика была живой."""
        attempt = Attempt.objects.get(user=user, quiz=quiz)
        moment = timezone.now() - timedelta(days=rng.randint(0, 6), minutes=rng.randint(5, 600))
        Attempt.objects.filter(pk=attempt.pk).update(started_at=moment)
        for answer in Answer.objects.filter(attempt=attempt).order_by("id"):
            moment += timedelta(
                seconds=rng.uniform(2, 9) * (2 if answer.question.order == 3 else 1)
            )
            Answer.objects.filter(pk=answer.pk).update(answered_at=moment)
        Attempt.objects.filter(pk=attempt.pk).update(finished_at=moment)
