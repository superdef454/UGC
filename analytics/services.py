from analytics.models import StatisticsOutbox
from attempts.models import Attempt


def enqueue_finished_attempt(attempt: Attempt) -> None:
    """Ставит завершённое прохождение в очередь на подсчёт статистики.

    Вызывать внутри той же транзакции, в которой прохождение завершается.
    """
    StatisticsOutbox.objects.create(attempt=attempt)
