from collections.abc import Sequence
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from analytics.services import enqueue_finished_attempt
from attempts.models import Answer, AnswerChoice, Attempt
from core.exceptions import DomainError, NotFoundError
from moderation.services import check_text
from quizzes.models import Question, Quiz
from quizzes.structure import QuestionItem, QuizStructure, aget_quiz_structure, get_quiz_structure
from users.models import User


@dataclass(frozen=True, slots=True)
class Progress:
    """Сколько вопросов уже отвечено."""

    answered: int
    total: int

    @property
    def percent(self) -> int:
        return round(self.answered * 100 / self.total) if self.total else 100


@dataclass(frozen=True, slots=True)
class PassingState:
    """Где сейчас пользователь в опросе: следующий вопрос и прогресс."""

    attempt_id: int
    quiz_id: int
    quiz_title: str
    is_finished: bool
    question: QuestionItem | None
    progress: Progress


def _state(attempt: Attempt, structure: QuizStructure, answered_ids: set[int]) -> PassingState:
    question = structure.next_question(answered_ids)
    return PassingState(
        attempt_id=attempt.pk,
        quiz_id=structure.quiz_id,
        quiz_title=structure.title,
        is_finished=question is None,
        question=question,
        progress=Progress(answered=len(answered_ids), total=len(structure.questions)),
    )


def _answered_ids(attempt: Attempt) -> QuerySet[Answer, int]:
    # Index-only scan по уникальному индексу (attempt, question).
    return Answer.objects.filter(attempt=attempt).values_list("question_id", flat=True)


async def aget_passing_state(user: User, quiz_id: int) -> PassingState:
    """Следующий вопрос для пользователя с учётом прогресса.

    При первом обращении создаёт прохождение, при повторном - продолжает его
    с первого неотвеченного вопроса.
    """
    quiz = await Quiz.objects.exclude(status=Quiz.Status.DRAFT).filter(pk=quiz_id).afirst()
    if quiz is None:
        raise NotFoundError("Опрос не найден")

    if quiz.status == Quiz.Status.PUBLISHED:
        attempt, _ = await Attempt.objects.aget_or_create(user=user, quiz=quiz)
    else:
        found = await Attempt.objects.filter(user=user, quiz=quiz).afirst()
        if found is None or found.status != Attempt.Status.FINISHED:
            raise DomainError("Опрос закрыт")
        attempt = found

    structure = await aget_quiz_structure(quiz)
    answered_ids = {question_id async for question_id in _answered_ids(attempt)}
    return _state(attempt, structure, answered_ids)


def _validate_answer(question: QuestionItem, option_ids: list[int], custom_text: str) -> None:
    if unknown := set(option_ids) - question.option_ids:
        raise DomainError(f"Варианты {sorted(unknown)} не относятся к этому вопросу")
    if custom_text and not question.allow_custom_answer:
        raise DomainError("Свой ответ для этого вопроса не предусмотрен")
    if custom_text and not check_text(custom_text):
        raise DomainError("Ответ не прошёл модерацию")

    picked = len(option_ids) + bool(custom_text)
    if picked == 0 and question.is_required:
        raise DomainError("Это обязательный вопрос")
    if picked > 1 and not question.is_multiple:
        raise DomainError("Здесь можно выбрать только один вариант")


def submit_answer(
    user: User,
    quiz_id: int,
    question_id: int,
    option_ids: Sequence[int] = (),
    custom_text: str = "",
) -> PassingState:
    """Сохраняет ответ на текущий вопрос и возвращает следующий шаг.

    Пустой ответ на необязательный вопрос - это пропуск. После последнего
    вопроса прохождение завершается и попадает в очередь на статистику.
    """
    option_ids = list(dict.fromkeys(option_ids))
    custom_text = custom_text.strip()

    with transaction.atomic():
        # Лочим только строку прохождения (of=self), не опрос: иначе все,
        # кто проходит популярный опрос, выстроились бы в очередь на одну строку.
        attempt = (
            Attempt.objects.select_for_update(of=("self",))
            .select_related("quiz")
            .filter(user=user, quiz_id=quiz_id)
            .first()
        )
        if attempt is None:
            raise NotFoundError("Прохождение не найдено, сначала запросите вопрос")
        if attempt.status == Attempt.Status.FINISHED:
            raise DomainError("Опрос уже пройден")
        if attempt.quiz.status != Quiz.Status.PUBLISHED:
            raise DomainError("Опрос закрыт")

        structure = get_quiz_structure(attempt.quiz)
        answered_ids = set(_answered_ids(attempt))
        current = structure.next_question(answered_ids)
        if current is None or current.id != question_id:
            raise DomainError("Можно ответить только на текущий вопрос")
        _validate_answer(current, option_ids, custom_text)

        answer = Answer.objects.create(
            attempt=attempt, question_id=current.id, custom_text=custom_text
        )
        AnswerChoice.objects.bulk_create(
            AnswerChoice(answer=answer, option_id=option_id) for option_id in option_ids
        )
        answered_ids.add(current.id)

        if structure.next_question(answered_ids) is None:
            attempt.status = Attempt.Status.FINISHED
            attempt.finished_at = timezone.now()
            attempt.save(update_fields=["status", "finished_at"])
            enqueue_finished_attempt(attempt)

    return _state(attempt, structure, answered_ids)


def user_attempts(user: User) -> QuerySet[Attempt]:
    """Прохождения пользователя с прогрессом, свежие сверху."""
    answered = (
        Answer.objects.filter(attempt=OuterRef("pk"))
        .values("attempt")
        .annotate(count=Count("pk"))
        .values("count")
    )
    total = (
        Question.objects.filter(quiz=OuterRef("quiz"))
        .values("quiz")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return (
        Attempt.objects.filter(user=user)
        .select_related("quiz")
        .annotate(
            answered_count=Coalesce(Subquery(answered), 0),
            questions_count=Coalesce(Subquery(total), 0),
        )
        .order_by("-started_at")
    )
