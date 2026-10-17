"""Страницы сайта.

Тонкие async view поверх тех же сервисов, что и API. Пользователя берём через
``request.auser()`` и кладём в контекст явно: ленивый ``request.user`` в async
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
from attempts.services import aget_passing_state, submit_answer, user_attempts
from core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from quizzes.models import Quiz
from quizzes.services import aget_own_quiz, close_quiz, publish_quiz
from quizzes.structure import aget_quiz_structure
from users.models import User

PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class QuizRow:
    """Строка списка доступных опросов: опрос и моё прохождение, если есть."""

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
    """Прохождение опроса: один вопрос на странице."""
    user = await _current_user(request)
    error = None
    if request.method == "POST":
        skip = "skip" in request.POST
        try:
            await sync_to_async(submit_answer)(
                user,
                pk,
                question_id=_ints([request.POST.get("question_id", "")])[0],
                option_ids=[] if skip else _ints(request.POST.getlist("option")),
                custom_text="" if skip else request.POST.get("custom_text", ""),
            )
            return redirect("web:take-quiz", pk=pk)
        except DomainError as exc:
            error = exc.message

    try:
        state = await aget_passing_state(user, pk)
    except NotFoundError as exc:
        raise Http404(exc.message) from exc
    except DomainError as exc:
        return await _render(request, "quiz_closed.html", {"message": exc.message}, status=400)

    context = {
        "state": state,
        "error": error,
        "segments": [index < state.progress.answered for index in range(state.progress.total)],
        # После ошибки возвращаем то, что пользователь уже отметил.
        "picked": request.POST.getlist("option") if error else [],
        "custom_text": request.POST.get("custom_text", "") if error else "",
    }
    return await _render(request, "take_quiz.html", context, status=400 if error else 200)


@login_required
@require_GET
async def my_attempts(request: HttpRequest) -> HttpResponse:
    """Мои прохождения: незавершённые можно продолжить."""
    user = await _current_user(request)
    attempts = [attempt async for attempt in user_attempts(user)]
    return await _render(request, "my_attempts.html", {"attempts": attempts})


@login_required
@require_GET
async def my_quizzes(request: HttpRequest) -> HttpResponse:
    """Опросы, которые я создал."""
    user = await _current_user(request)
    quizzes = [
        quiz
        async for quiz in Quiz.objects.filter(author=user)
        .with_questions_count()
        .annotate(attempts_count=Coalesce(F("statistics__attempts_count"), Value(0)))
        .order_by("-created_at")[:PAGE_SIZE]
    ]
    return await _render(request, "my_quizzes.html", {"quizzes": quizzes})


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
    except PermissionDeniedError as exc:
        raise PermissionDenied(exc.message) from exc


async def _quiz_detail(request: HttpRequest, quiz: Quiz, error: str | None = None) -> HttpResponse:
    structure = await aget_quiz_structure(quiz)
    context = {"quiz": quiz, "structure": structure, "error": error}
    return await _render(request, "quiz_detail.html", context, status=400 if error else 200)


@login_required
@require_GET
async def quiz_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Мой опрос: структура и управление."""
    return await _quiz_detail(request, await _own_quiz(request, pk))


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
        return await _quiz_detail(request, quiz, error=exc.message)
    return redirect("web:quiz-detail", pk=pk)


@login_required
@require_GET
async def quiz_statistics(request: HttpRequest, pk: int) -> HttpResponse:
    """Статистика моего опроса."""
    quiz = await _own_quiz(request, pk)
    report = await aget_quiz_report(await _current_user(request), quiz.pk)
    return await _render(request, "statistics.html", {"report": report})
