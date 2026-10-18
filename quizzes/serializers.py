from typing import Any

from rest_framework import serializers

from moderation.services import check_text
from quizzes.models import AnswerOption, Question, Quiz


def validate_text(value: str) -> None:
    """Пропускает текст через модерацию."""
    if not check_text(value):
        raise serializers.ValidationError("Текст не прошёл модерацию")


class OptionInputSerializer(serializers.Serializer):
    """Вариант ответа при создании опроса."""

    text = serializers.CharField(max_length=500, validators=[validate_text])


class QuestionInputSerializer(serializers.Serializer):
    """Вопрос при создании опроса: нужны варианты или разрешённый свой ответ."""

    text = serializers.CharField(max_length=1000, validators=[validate_text])
    type = serializers.ChoiceField(choices=Question.Type.choices, default=Question.Type.SINGLE)
    allow_custom_answer = serializers.BooleanField(default=False)
    is_required = serializers.BooleanField(default=True)
    options = serializers.ListField(child=OptionInputSerializer(), required=False, max_length=20)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs.setdefault("options", [])
        if not attrs["options"] and not attrs["allow_custom_answer"]:
            raise serializers.ValidationError("Добавьте варианты ответа или разрешите свой ответ")
        return attrs


class QuizCreateSerializer(serializers.Serializer):
    """Опрос целиком: порядок вопросов и вариантов - порядок в списках."""

    title = serializers.CharField(max_length=255, validators=[validate_text])
    description = serializers.CharField(allow_blank=True, default="", validators=[validate_text])
    questions = serializers.ListField(child=QuestionInputSerializer(), min_length=1, max_length=100)


class AnswerOptionSerializer(serializers.ModelSerializer):
    """Вариант ответа в структуре опроса."""

    class Meta:
        model = AnswerOption
        fields = ("id", "text", "order")


class QuestionSerializer(serializers.ModelSerializer):
    """Вопрос с вариантами в порядке, заданном автором."""

    options = AnswerOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "text", "type", "order", "is_required", "allow_custom_answer", "options")


class QuizDetailSerializer(serializers.ModelSerializer):
    """Опрос со всей структурой: вопросы и варианты по порядку."""

    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ("id", "title", "description", "status", "created_at", "published_at", "questions")


class QuizListSerializer(serializers.ModelSerializer):
    """Опрос в каталоге: без структуры, только число вопросов."""

    questions_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quiz
        fields: tuple[str, ...] = (
            "id",
            "title",
            "description",
            "status",
            "published_at",
            "questions_count",
        )


class AuthoredQuizSerializer(QuizListSerializer):
    """Опрос в списке автора: плюс дата создания и число завершённых прохождений."""

    attempts_count = serializers.IntegerField(read_only=True)

    class Meta(QuizListSerializer.Meta):
        fields = (*QuizListSerializer.Meta.fields, "created_at", "attempts_count")


class OrderSerializer(serializers.Serializer):
    """Новый порядок: все id вопросов (или вариантов) ровно по одному разу."""

    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1)
