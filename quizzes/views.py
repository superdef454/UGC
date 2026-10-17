"""API опросов.

Список доступных опросов - горячий путь, он async. Остальное - редкие действия
автора, это обычные sync view: под ASGI Django сам выполнит их в пуле потоков.
"""

from typing import Any

from adrf.views import APIView as AsyncAPIView
from asgiref.sync import sync_to_async
from django.db.models import F, QuerySet, Value
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from quizzes import services
from quizzes.models import Quiz
from quizzes.serializers import (
    MyQuizListSerializer,
    OrderSerializer,
    QuizCreateSerializer,
    QuizDetailSerializer,
    QuizListSerializer,
)
from users.utils import request_user


class PublishedCursorPagination(CursorPagination):
    """Курсор вместо offset: на миллионе опросов OFFSET 100000 - это скан 100000 строк."""

    page_size = 20
    ordering = ("-published_at", "-id")


class CreatedCursorPagination(CursorPagination):
    """Мои опросы, свежие сверху."""

    page_size = 20
    ordering = ("-created_at", "-id")


class AvailableQuizListView(AsyncAPIView):
    """Опубликованные опросы, свежие сверху."""

    @extend_schema(responses=QuizListSerializer(many=True))
    async def get(self, request: Request) -> Response:
        paginator = PublishedCursorPagination()
        queryset = Quiz.objects.filter(status=Quiz.Status.PUBLISHED).with_questions_count()
        page = await sync_to_async(paginator.paginate_queryset)(queryset, request, view=self)
        return paginator.get_paginated_response(QuizListSerializer(page, many=True).data)


class MyQuizListCreateView(generics.ListCreateAPIView[Quiz]):
    """Мои опросы и создание нового."""

    pagination_class = CreatedCursorPagination

    def get_queryset(self) -> QuerySet[Quiz]:
        return (
            Quiz.objects.filter(author=request_user(self.request))
            .with_questions_count()
            .annotate(attempts_count=Coalesce(F("statistics__attempts_count"), Value(0)))
        )

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.request.method == "POST":
            return QuizCreateSerializer
        return MyQuizListSerializer

    @extend_schema(request=QuizCreateSerializer, responses={201: QuizDetailSerializer})
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = QuizCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quiz = services.create_quiz(request_user(request), serializer.validated_data)
        return Response(_detail(quiz.pk), status=status.HTTP_201_CREATED)


class MyQuizDetailView(generics.RetrieveAPIView[Quiz]):
    """Мой опрос со всей структурой."""

    serializer_class = QuizDetailSerializer

    def get_queryset(self) -> QuerySet[Quiz]:
        return Quiz.objects.filter(author=request_user(self.request)).prefetch_related(
            "questions__options"
        )


class PublishQuizView(APIView):
    """Публикация черновика."""

    @extend_schema(request=None, responses=QuizDetailSerializer)
    def post(self, request: Request, pk: int) -> Response:
        quiz = services.publish_quiz(request_user(request), pk)
        return Response(_detail(quiz.pk))


class CloseQuizView(APIView):
    """Закрытие опроса."""

    @extend_schema(request=None, responses=QuizDetailSerializer)
    def post(self, request: Request, pk: int) -> Response:
        quiz = services.close_quiz(request_user(request), pk)
        return Response(_detail(quiz.pk))


class ReorderQuestionsView(APIView):
    """Новый порядок вопросов: все id вопросов опроса в нужном порядке."""

    @extend_schema(request=OrderSerializer, responses={204: None})
    def post(self, request: Request, pk: int) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_questions(request_user(request), pk, serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReorderOptionsView(APIView):
    """Новый порядок вариантов: все id вариантов вопроса в нужном порядке."""

    @extend_schema(request=OrderSerializer, responses={204: None})
    def post(self, request: Request, pk: int) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_options(request_user(request), pk, serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def _detail(quiz_id: int) -> dict[str, Any]:
    quiz = Quiz.objects.prefetch_related("questions__options").get(pk=quiz_id)
    return QuizDetailSerializer(quiz).data
