import django.db.models.deletion
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    """Полный индекс по cloned_from -> частичный, без NULL.

    Автогенерация через AlterField пересоздаёт FK-ограничение: ACCESS EXCLUSIVE
    lock и проверка всех строк таблицы. Поэтому в БД меняем только индексы,
    и оба - CONCURRENTLY. Новый создаём раньше, чем удаляем старый.
    """

    atomic = False

    dependencies = [
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="quiz",
                    name="cloned_from",
                    field=models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="clones",
                        to="quizzes.quiz",
                    ),
                ),
            ],
        ),
        AddIndexConcurrently(
            model_name="quiz",
            index=models.Index(
                condition=models.Q(cloned_from__isnull=False),
                fields=["cloned_from"],
                name="quiz_cloned_from_idx",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'DROP INDEX CONCURRENTLY IF EXISTS "quizzes_quiz_cloned_from_id_5a5ee77a";',
                    reverse_sql=(
                        'CREATE INDEX CONCURRENTLY "quizzes_quiz_cloned_from_id_5a5ee77a" '
                        'ON "quizzes_quiz" ("cloned_from_id");'
                    ),
                ),
            ],
        ),
    ]
