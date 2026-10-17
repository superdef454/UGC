import time
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from analytics.services import process_outbox_batch


class Command(BaseCommand):
    help = "Воркер статистики: переносит завершённые прохождения из очереди в статистику"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--once", action="store_true", help="разобрать очередь и выйти")
        parser.add_argument("--batch-size", type=int, default=settings.STATISTICS_BATCH_SIZE)
        parser.add_argument("--interval", type=float, default=settings.STATISTICS_POLL_INTERVAL)

    def handle(
        self, *args: Any, once: bool, batch_size: int, interval: float, **options: Any
    ) -> None:
        self.stdout.write("Воркер статистики запущен")
        try:
            while True:
                processed = process_outbox_batch(batch_size)
                if processed:
                    self.stdout.write(f"учтено прохождений: {processed}")
                if processed == batch_size:
                    continue  # в очереди ещё есть - не спим
                if once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("Воркер остановлен")
