"""Страницы сайта.

Тонкие async view поверх тех же сервисов, что и API. Пользователь берётся через
``request.auser()`` и кладётся в контекст явно: ленивый ``request.user`` в async
view полез бы в базу синхронно.
"""

from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import F, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from analytics.reports import aget_quiz_report
from attempts.models import Attempt
from attempts.services import aget_attempt_state, astart_attempt, submit_answer, user_attempts
from core.exceptions import DomainError, NotFoundError
from quizzes.models import Quiz
from quizzes.services import aget_own_quiz, close_quiz, publish_quiz
from quizzes.structure import aget_quiz_structure
from users.models import User

PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class QuizRow:
    """Строка каталога: опрос и прохождение текущего пользователя, если оно есть."""

    quiz: Quiz
    attempt: Attempt | None


async def _current_user(request: HttpRequest) -> User:
    # Все страницы под login_required, анонима здесь быть не может.
    user = await request.auser()
    if not isinstance(user, User):
        raise PermissionDenied
    return user


async def _render(
    request: HttpRequest, template: str, context: dict[str, Any], status: int = 200
) -> HttpResponse:
    context["user"] = await _current_user(request)
    return render(request, f"web/{template}", context, status=status)


def _ints(values: list[str]) -> list[int]:
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise DomainError("Некорректный вариант ответа") from exc


CUSTOM_CHOICE = "custom"


def _posted_answer(request: HttpRequest) -> tuple[list[int], str]:
    """Варианты и свой ответ из формы вопроса.

    В одиночном вопросе «Свой вариант» - отдельная radio-кнопка, а текст остаётся
    в форме при выборе другого варианта. Поэтому отправляется только выбранное:
    отмечен вариант - текст игнорируется, отмечен «Свой вариант» - только текст.
    """
    if "skip" in request.POST:
        return [], ""
    picked = request.POST.getlist("option")
    option_ids = _ints([value for value in picked if value != CUSTOM_CHOICE])
    custom_text = request.POST.get("custom_text", "")
    if request.POST.get("exclusive_custom") and option_ids and CUSTOM_CHOICE not in picked:
        custom_text = ""
    return option_ids, custom_text


@login_required
@require_GET
async def quiz_list(request: HttpRequest) -> HttpResponse:
    """Опросы, которые можно пройти."""
    user = await _current_user(request)
    # TODO: курсорная пагинация, как в API.
    quizzes = [
        quiz
        async for quiz in Quiz.objects.filter(status=Quiz.Status.PUBLISHED)
        .with_questions_count()
        .select_related("author")
        .order_by("-published_at", "-id")[:PAGE_SIZE]
    ]
    attempts = {
        attempt.quiz_id: attempt
        async for attempt in user_attempts(user).filter(quiz__in=[q.pk for q in quizzes])
    }
    rows = [QuizRow(quiz, attempts.get(quiz.pk)) for quiz in quizzes]
    return await _render(request, "quiz_list.html", {"rows": rows})


@login_required
@require_http_methods(["GET", "POST"])
async def take_quiz(request: HttpRequest, pk: int) -> HttpResponse:
    """Прохождение опроса: один вопрос на странице. Если прохождение не начато - приглашение."""
    user = await _current_user(request)
    error = None
    if request.method == "POST":
        option_ids, custom_text = _posted_answer(request)
        try:
            await sync_to_async(submit_answer)(
                user,
                pk,
                question_id=_ints([request.POST.get("question_id", "")])[0],
                option_ids=option_ids,
                custom_text=custom_text,
            )
            return redirect("web:take-quiz", pk=pk)
        except DomainError as exc:
            error = exc.message

    try:
        state = await aget_attempt_state(user, pk)
    except NotFoundError:
        return await _quiz_intro(request, pk)

    current_id = str(state.next_question.id) if state.next_question else None
    if error and request.POST.get("question_id") != current_id:
        # Форма была для уже отвеченного вопроса (двойной клик, «назад» в браузере):
        # ответ уже сохранён, просто показываем текущий шаг без ошибки.
        return redirect("web:take-quiz", pk=pk)

    context = {
        "state": state,
        "error": error,
        "segments": [index < state.progress.answered for index in range(state.progress.total)],
        # После ошибки возвращаем то, что пользователь уже отметил.
        "picked": request.POST.getlist("option") if error else [],
        "custom_text": request.POST.get("custom_text", "") if error else "",
    }
    return await _render(request, "take_quiz.html", context, status=400 if error else 200)


async def _quiz_intro(request: HttpRequest, pk: int) -> HttpResponse:
    quiz = (
        await Quiz.objects.exclude(status=Quiz.Status.DRAFT)
        .with_questions_count()
        .filter(pk=pk)
        .afirst()
    )
    if quiz is None:
        raise Http404("Опрос не найден")
    if quiz.status != Quiz.Status.PUBLISHED:
        return await _render(request, "quiz_closed.html", {"message": "Опрос закрыт"}, status=409)
    return await _render(request, "quiz_intro.html", {"quiz": quiz})


@login_required
@require_POST
async def start_quiz(request: HttpRequest, pk: int) -> HttpResponse:
    """Начинает прохождение (или продолжает начатое) и ведёт к текущему вопросу."""
    try:
        await astart_attempt(await _current_user(request), pk)
    except NotFoundError as exc:
        raise Http404(exc.message) from exc
    except DomainError as exc:
        return await _render(request, "quiz_closed.html", {"message": exc.message}, status=409)
    return redirect("web:take-quiz", pk=pk)


@login_required
@require_GET
async def attempt_list(request: HttpRequest) -> HttpResponse:
    """Прохождения текущего пользователя: незавершённые можно продолжить."""
    user = await _current_user(request)
    # TODO: пагинация, как в API.
    attempts = [attempt async for attempt in user_attempts(user)[:PAGE_SIZE]]
    return await _render(request, "attempt_list.html", {"attempts": attempts})


@login_required
@require_GET
async def authored_quizzes(request: HttpRequest) -> HttpResponse:
    """Опросы, созданные текущим пользователем."""
    user = await _current_user(request)
    quizzes = [
        quiz
        async for quiz in Quiz.objects.filter(author=user)
        .with_questions_count()
        .annotate(attempts_count=Coalesce(F("statistics__attempts_count"), Value(0)))
        .order_by("-created_at")[:PAGE_SIZE]
    ]
    return await _render(request, "authored_quizzes.html", {"quizzes": quizzes})


@login_required
@require_GET
async def quiz_builder(request: HttpRequest) -> HttpResponse:
    """Конструктор опроса. Сохраняет через API, см. static/js/builder.js."""
    return await _render(request, "quiz_builder.html", {})


async def _own_quiz(request: HttpRequest, pk: int) -> Quiz:
    try:
        return await aget_own_quiz(await _current_user(request), pk)
    except NotFoundError as exc:
        raise Http404(exc.message) from exc


async def _quiz_manage(request: HttpRequest, quiz: Quiz, error: str | None = None) -> HttpResponse:
    structure = await aget_quiz_structure(quiz)
    context = {"quiz": quiz, "structure": structure, "error": error}
    return await _render(request, "quiz_manage.html", context, status=409 if error else 200)


@login_required
@require_GET
async def quiz_manage(request: HttpRequest, pk: int) -> HttpResponse:
    """Управление опросом: структура, публикация, закрытие. Только для автора."""
    return await _quiz_manage(request, await _own_quiz(request, pk))


@login_required
@require_POST
async def quiz_action(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    """Публикация или закрытие опроса."""
    services = {"publish": publish_quiz, "close": close_quiz}
    if action not in services:
        raise Http404
    quiz = await _own_quiz(request, pk)
    try:
        await sync_to_async(services[action])(await _current_user(request), quiz.pk)
    except DomainError as exc:
        return await _quiz_manage(request, quiz, error=exc.message)
    return redirect("web:quiz-manage", pk=pk)


@login_required
@require_GET
async def quiz_statistics(request: HttpRequest, pk: int) -> HttpResponse:
    """Статистика опроса. Только для автора."""
    quiz = await _own_quiz(request, pk)
    report = await aget_quiz_report(await _current_user(request), quiz.pk)
    return await _render(request, "statistics.html", {"report": report})
