"""Неизменяемый снимок структуры опроса для прохождения и статистики.

После публикации вопросы и варианты не меняются, поэтому структуру можно
один раз достать из базы и держать в кэше. На горячем пути (следующий вопрос,
ответ) в базу тогда ходим только за ответами самого пользователя.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from django.core.cache import cache
from django.db.models import QuerySet

from quizzes.models import Question, Quiz

CACHE_TIMEOUT = 60 * 60


@dataclass(frozen=True, slots=True)
class OptionItem:
    """Вариант ответа."""

    id: int
    text: str


@dataclass(frozen=True, slots=True)
class QuestionItem:
    """Вопрос с вариантами в порядке, который задал автор."""

    id: int
    text: str
    type: str
    order: int
    is_required: bool
    allow_custom_answer: bool
    options: tuple[OptionItem, ...]
    option_ids: frozenset[int] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_ids", frozenset(option.id for option in self.options))

    @property
    def is_multiple(self) -> bool:
        return self.type == Question.Type.MULTIPLE


@dataclass(frozen=True, slots=True)
class QuizStructure:
    """Опрос целиком: вопросы по порядку."""

    quiz_id: int
    title: str
    questions: tuple[QuestionItem, ...]

    def next_question(self, answered_ids: Collection[int]) -> QuestionItem | None:
        """Первый по порядку вопрос, на который ещё нет ответа."""
        return next((q for q in self.questions if q.id not in answered_ids), None)


def _cache_key(quiz_id: int) -> str:
    return f"quiz-structure:{quiz_id}"


def _build(quiz: Quiz, questions: Iterable[Question]) -> QuizStructure:
    return QuizStructure(
        quiz_id=quiz.pk,
        title=quiz.title,
        questions=tuple(
            QuestionItem(
                id=question.pk,
                text=question.text,
                type=question.type,
                order=question.order,
                is_required=question.is_required,
                allow_custom_answer=question.allow_custom_answer,
                options=tuple(
                    OptionItem(id=option.pk, text=option.text) for option in question.options.all()
                ),
            )
            for question in questions
        ),
    )


def _questions(quiz: Quiz) -> QuerySet[Question]:
    return Question.objects.filter(quiz=quiz).prefetch_related("options").order_by("order")


def get_quiz_structure(quiz: Quiz) -> QuizStructure:
    """Структура опроса. Для опубликованных и закрытых берётся из кэша."""
    if not quiz.is_editable and (cached := cache.get(_cache_key(quiz.pk))) is not None:
        return cached

    structure = _build(quiz, _questions(quiz))
    if not quiz.is_editable:
        cache.set(_cache_key(quiz.pk), structure, CACHE_TIMEOUT)
    return structure


async def aget_quiz_structure(quiz: Quiz) -> QuizStructure:
    """Async-версия :func:`get_quiz_structure`."""
    if not quiz.is_editable and (cached := await cache.aget(_cache_key(quiz.pk))) is not None:
        return cached

    structure = _build(quiz, [question async for question in _questions(quiz)])
    if not quiz.is_editable:
        await cache.aset(_cache_key(quiz.pk), structure, CACHE_TIMEOUT)
    return structure
