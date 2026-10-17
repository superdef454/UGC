"""API прохождения. Это горячий путь, поэтому view async.

Чтение идёт через async ORM. Запись ответа - синхронный сервис в транзакции
через sync_to_async: транзакции в async ORM Django пока не поддерживает.
"""

from adrf.views import APIView
from asgiref.sync import sync_to_async
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response

from attempts import services
from attempts.models import Attempt
from attempts.serializers import AnswerInputSerializer, AttemptSerializer, PassingStateSerializer
from users.utils import request_user


class AttemptCursorPagination(CursorPagination):
    """Мои прохождения, свежие сверху."""

    page_size = 20
    ordering = ("-started_at", "-id")


class NextQuestionView(APIView):
    """Следующий вопрос опроса для текущего пользователя с учётом прогресса."""

    @extend_schema(responses=PassingStateSerializer)
    async def get(self, request: Request, pk: int) -> Response:
        state = await services.aget_passing_state(request_user(request), pk)
        return Response(PassingStateSerializer(state).data)


class AnswerView(APIView):
    """Ответ на текущий вопрос. В ответе сразу следующий вопрос."""

    @extend_schema(request=AnswerInputSerializer, responses=PassingStateSerializer)
    async def post(self, request: Request, pk: int) -> Response:
        serializer = AnswerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = await sync_to_async(services.submit_answer)(
            request_user(request), pk, **serializer.validated_data
        )
        return Response(PassingStateSerializer(state).data)


class MyAttemptListView(APIView):
    """Мои прохождения. ``?status=in_progress`` - что можно продолжить."""

    @extend_schema(
        parameters=[OpenApiParameter("status", enum=Attempt.Status.values, required=False)],
        responses=AttemptSerializer(many=True),
    )
    async def get(self, request: Request) -> Response:
        queryset = services.user_attempts(request_user(request))
        if (status := request.query_params.get("status")) in Attempt.Status.values:
            queryset = queryset.filter(status=status)
        paginator = AttemptCursorPagination()
        page = await sync_to_async(paginator.paginate_queryset)(queryset, request, view=self)
        return paginator.get_paginated_response(AttemptSerializer(page, many=True).data)
