from adrf.views import APIView
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.reports import aget_quiz_report
from analytics.serializers import QuizReportSerializer
from users.utils import request_user


class QuizStatisticsView(APIView):
    """Статистика по моему опросу.

    Отдаётся уже посчитанная статистика: ответы при запросе не агрегируются,
    это делает воркер. Данные отстают от реальности на пару секунд.
    """

    @extend_schema(responses=QuizReportSerializer)
    async def get(self, request: Request, pk: int) -> Response:
        report = await aget_quiz_report(request_user(request), pk)
        return Response(QuizReportSerializer(report).data)
