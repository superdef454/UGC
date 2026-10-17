"""API прохождения. Это горячий путь, поэтому view async.

Чтение идёт через async ORM. Запись ответа - синхронный сервис в транзакции
через sync_to_async: транзакции в async ORM Django пока не поддерживает.
"""

from adrf.views import APIView
from asgiref.sync import sync_to_async
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response

from attempts import services
from attempts.models import Attempt
from attempts.serializers import AnswerInputSerializer, AttemptSerializer, AttemptStateSerializer
from core.schema import errors
from users.utils import request_user


class AttemptCursorPagination(CursorPagination):
    """Прохождения, свежие сверху."""

    page_size = 20
    ordering = ("-started_at", "-id")


class QuizAttemptView(APIView):
    """Прохождение опроса текущим пользователем - одно на пару пользователь + опрос.

    GET отдаёт прогресс и следующий вопрос (``next_question``) и ничего не меняет,
    POST начинает прохождение.
    """

    @extend_schema(responses={200: AttemptStateSerializer, **errors(404)})
    async def get(self, request: Request, quiz_id: int) -> Response:
        state = await services.aget_attempt_state(request_user(request), quiz_id)
        return Response(AttemptStateSerializer(state).data)

    @extend_schema(
        request=None,
        responses={201: AttemptStateSerializer, 200: AttemptStateSerializer, **errors(404, 409)},
        description="Начинает прохождение. Если оно уже есть - возвращает его со статусом 200.",
    )
    async def post(self, request: Request, quiz_id: int) -> Response:
        state, created = await services.astart_attempt(request_user(request), quiz_id)
        if not created:
            return Response(AttemptStateSerializer(state).data)
        return Response(
            AttemptStateSerializer(state).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("quiz-attempt", args=[quiz_id])},
        )


class AttemptAnswerView(APIView):
    """Ответ на текущий вопрос. В ответе - обновлённое прохождение со следующим вопросом."""

    @extend_schema(
        request=AnswerInputSerializer,
        responses={200: AttemptStateSerializer, **errors(400, 404, 409)},
    )
    async def post(self, request: Request, quiz_id: int) -> Response:
        serializer = AnswerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = await sync_to_async(services.submit_answer)(
            request_user(request), quiz_id, **serializer.validated_data
        )
        return Response(AttemptStateSerializer(state).data)


class AttemptListView(APIView):
    """Прохождения текущего пользователя. ``?status=in_progress`` - что можно продолжить."""

    @extend_schema(
        parameters=[OpenApiParameter("status", enum=Attempt.Status.values, required=False)],
        responses=AttemptSerializer(many=True),
    )
    async def get(self, request: Request) -> Response:
        queryset = services.user_attempts(request_user(request))
        if (attempt_status := request.query_params.get("status")) in Attempt.Status.values:
            queryset = queryset.filter(status=attempt_status)
        paginator = AttemptCursorPagination()
        page = await sync_to_async(paginator.paginate_queryset)(queryset, request, view=self)
        return paginator.get_paginated_response(AttemptSerializer(page, many=True).data)
