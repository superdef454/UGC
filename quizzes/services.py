from typing import NotRequired, TypedDict

from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from quizzes.models import AnswerOption, Question, Quiz
from users.models import User


class OptionInput(TypedDict):
    """Вариант ответа при создании опроса."""

    text: str


class QuestionInput(TypedDict):
    """Вопрос при создании опроса."""

    text: str
    type: str
    allow_custom_answer: bool
    is_required: bool
    options: list[OptionInput]


class QuizInput(TypedDict):
    """Опрос целиком, как его присылает автор."""

    title: str
    description: NotRequired[str]
    questions: list[QuestionInput]


def get_own_quiz(user: User, quiz_id: int, *, for_update: bool = False) -> Quiz:
    """Опрос, автором которого является пользователь."""
    queryset = Quiz.objects.select_for_update() if for_update else Quiz.objects.all()
    quiz = queryset.filter(pk=quiz_id).first()
    if quiz is None:
        raise NotFoundError("Опрос не найден")
    if quiz.author_id != user.pk:
        raise PermissionDeniedError("Это не ваш опрос")
    return quiz


@transaction.atomic
def create_quiz(author: User, data: QuizInput) -> Quiz:
    """Создаёт черновик опроса сразу с вопросами и вариантами.

    Порядок вопросов и вариантов - порядок в присланных списках.
    """
    quiz = Quiz.objects.create(
        author=author,
        title=data["title"],
        description=data.get("description", ""),
    )
    questions = Question.objects.bulk_create(
        Question(
            quiz=quiz,
            order=position,
            text=item["text"],
            type=item["type"],
            allow_custom_answer=item["allow_custom_answer"],
            is_required=item["is_required"],
        )
        for position, item in enumerate(data["questions"], start=1)
    )
    AnswerOption.objects.bulk_create(
        AnswerOption(question=question, order=position, text=option["text"])
        for question, item in zip(questions, data["questions"], strict=True)
        for position, option in enumerate(item["options"], start=1)
    )
    return quiz


@transaction.atomic
def publish_quiz(user: User, quiz_id: int) -> Quiz:
    """Публикует черновик. После этого структура опроса больше не меняется."""
    quiz = get_own_quiz(user, quiz_id, for_update=True)
    if quiz.status != Quiz.Status.DRAFT:
        raise DomainError("Опубликовать можно только черновик")

    questions = list(quiz.questions.annotate(options_count=Count("options")))
    if not questions:
        raise DomainError("В опросе нет ни одного вопроса")
    for question in questions:
        if not question.options_count and not question.allow_custom_answer:
            raise DomainError(f"У вопроса «{question.text}» нет вариантов ответа")

    # TODO: отправлять на модерацию (on_moderation), а не публиковать сразу.
    quiz.status = Quiz.Status.PUBLISHED
    quiz.published_at = timezone.now()
    quiz.save(update_fields=["status", "published_at", "updated_at"])
    return quiz


@transaction.atomic
def close_quiz(user: User, quiz_id: int) -> Quiz:
    """Закрывает опрос: новые ответы больше не принимаются."""
    quiz = get_own_quiz(user, quiz_id, for_update=True)
    if quiz.status != Quiz.Status.PUBLISHED:
        raise DomainError("Закрыть можно только опубликованный опрос")
    quiz.status = Quiz.Status.CLOSED
    quiz.save(update_fields=["status", "updated_at"])
    return quiz


def _apply_order[M: (Question, AnswerOption)](
    queryset: QuerySet[M], ordered_ids: list[int]
) -> None:
    items = {item.pk: item for item in queryset.select_for_update()}
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(items):
        raise DomainError("Нужно передать все id ровно по одному разу")

    for position, pk in enumerate(ordered_ids, start=1):
        items[pk].order = position
    # Уникальность (родитель, order) проверяется на коммите (deferrable),
    # поэтому промежуточные совпадения при перестановке не мешают.
    queryset.bulk_update(items.values(), ["order"])


@transaction.atomic
def reorder_questions(user: User, quiz_id: int, question_ids: list[int]) -> None:
    """Задаёт новый порядок вопросов черновика."""
    quiz = get_own_quiz(user, quiz_id, for_update=True)
    if not quiz.is_editable:
        raise DomainError("Порядок можно менять только у черновика")
    _apply_order(Question.objects.filter(quiz=quiz), question_ids)


@transaction.atomic
def reorder_options(user: User, question_id: int, option_ids: list[int]) -> None:
    """Задаёт новый порядок вариантов ответа у вопроса черновика."""
    question = Question.objects.filter(pk=question_id).first()
    if question is None:
        raise NotFoundError("Вопрос не найден")
    quiz = get_own_quiz(user, question.quiz_id, for_update=True)
    if not quiz.is_editable:
        raise DomainError("Порядок можно менять только у черновика")
    _apply_order(AnswerOption.objects.filter(question=question), option_ids)


# TODO: редактирование и удаление черновика по отдельным полям (PATCH/DELETE).
# TODO: clone_quiz(user, quiz_id) - копия структуры в новый черновик с cloned_from.
