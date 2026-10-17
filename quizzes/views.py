"""API опросов.

Каталог опросов - горячий путь, он async. Остальное - редкие действия автора,
это обычные sync view: под ASGI Django сам выполнит их в пуле потоков.
"""

from typing import Any

from adrf.views import APIView as AsyncAPIView
from asgiref.sync import sync_to_async
from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.schema import errors
from quizzes import services
from quizzes.models import Quiz
from quizzes.serializers import (
    AuthoredQuizSerializer,
    OrderSerializer,
    QuizCreateSerializer,
    QuizDetailSerializer,
    QuizListSerializer,
)
from users.models import User
from users.utils import request_user


class PublishedCursorPagination(CursorPagination):
    """Курсор вместо offset: на миллионе опросов OFFSET 100000 - это скан 100000 строк."""

    page_size = 20
    ordering = ("-published_at", "-id")


class CreatedCursorPagination(CursorPagination):
    """Опросы автора, свежие сверху."""

    page_size = 20
    ordering = ("-created_at", "-id")


def _authored(user: User, quiz_status: str | None) -> QuerySet[Quiz]:
    queryset = (
        Quiz.objects.filter(author=user)
        .with_questions_count()
        .annotate(attempts_count=Coalesce(F("statistics__attempts_count"), Value(0)))
    )
    if quiz_status is not None:
        if quiz_status not in Quiz.Status.values:
            raise ValidationError({"status": f"Допустимые значения: {', '.join(Quiz.Status)}"})
        queryset = queryset.filter(status=quiz_status)
    return queryset


def _detail(quiz_id: int) -> dict[str, Any]:
    quiz = Quiz.objects.prefetch_related("questions__options").get(pk=quiz_id)
    return QuizDetailSerializer(quiz).data


def _created(quiz_id: int) -> Response:
    return Response(
        _detail(quiz_id),
        status=status.HTTP_201_CREATED,
        headers={"Location": reverse("quiz-detail", args=[quiz_id])},
    )


class QuizListCreateView(AsyncAPIView):
    """Каталог опубликованных опросов и создание нового."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "author",
                enum=["me"],
                required=False,
                description="me - опросы текущего пользователя в любом статусе, включая черновики",
            ),
            OpenApiParameter(
                "status",
                enum=Quiz.Status.values,
                required=False,
                description="фильтр по статусу, только вместе с author=me",
            ),
        ],
        responses={200: AuthoredQuizSerializer(many=True), **errors(400)},
    )
    async def get(self, request: Request) -> Response:
        author = request.query_params.get("author")
        if author is None:
            paginator: CursorPagination = PublishedCursorPagination()
            queryset: QuerySet[Quiz] = Quiz.objects.filter(
                status=Quiz.Status.PUBLISHED
            ).with_questions_count()
            serializer_class: type[QuizListSerializer] = QuizListSerializer
        elif author == "me":
            paginator = CreatedCursorPagination()
            queryset = _authored(request_user(request), request.query_params.get("status"))
            serializer_class = AuthoredQuizSerializer
        else:
            # Чужие черновики не видны, а опубликованное и так есть в каталоге.
            raise ValidationError({"author": "Поддерживается только author=me"})

        page = await sync_to_async(paginator.paginate_queryset)(queryset, request, view=self)
        return paginator.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        request=QuizCreateSerializer, responses={201: QuizDetailSerializer, **errors(400)}
    )
    async def post(self, request: Request) -> Response:
        serializer = QuizCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quiz = await sync_to_async(services.create_quiz)(
            request_user(request), serializer.validated_data
        )
        return await sync_to_async(_created)(quiz.pk)


@extend_schema_view(get=extend_schema(responses={200: QuizDetailSerializer, **errors(404)}))
class QuizDetailView(generics.RetrieveAPIView[Quiz]):
    """Опрос со всей структурой. Черновик виден только автору."""

    serializer_class = QuizDetailSerializer
    lookup_url_kwarg = "quiz_id"

    def get_queryset(self) -> QuerySet[Quiz]:
        visible = Q(author=request_user(self.request)) | ~Q(status=Quiz.Status.DRAFT)
        return Quiz.objects.filter(visible).prefetch_related("questions__options")


class PublishQuizView(APIView):
    """Публикация черновика. После неё структура опроса не меняется."""

    @extend_schema(request=None, responses={200: QuizDetailSerializer, **errors(400, 404, 409)})
    def post(self, request: Request, quiz_id: int) -> Response:
        quiz = services.publish_quiz(request_user(request), quiz_id)
        return Response(_detail(quiz.pk))


class CloseQuizView(APIView):
    """Закрытие опроса: новые прохождения и ответы больше не принимаются."""

    @extend_schema(request=None, responses={200: QuizDetailSerializer, **errors(404, 409)})
    def post(self, request: Request, quiz_id: int) -> Response:
        quiz = services.close_quiz(request_user(request), quiz_id)
        return Response(_detail(quiz.pk))


class QuestionOrderView(APIView):
    """Порядок вопросов черновика: все id вопросов опроса в нужном порядке."""

    @extend_schema(request=OrderSerializer, responses={204: None, **errors(400, 404, 409)})
    def put(self, request: Request, quiz_id: int) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_questions(request_user(request), quiz_id, serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OptionOrderView(APIView):
    """Порядок вариантов ответа: все id вариантов вопроса в нужном порядке."""

    @extend_schema(request=OrderSerializer, responses={204: None, **errors(400, 404, 409)})
    def put(self, request: Request, quiz_id: int, question_id: int) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_options(
            request_user(request), quiz_id, question_id, serializer.validated_data["ids"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
