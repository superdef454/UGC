from rest_framework import serializers

from attempts.models import Attempt


class OptionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()


class QuestionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    type = serializers.CharField()
    order = serializers.IntegerField()
    is_required = serializers.BooleanField()
    allow_custom_answer = serializers.BooleanField()
    options = OptionItemSerializer(many=True)


class ProgressSerializer(serializers.Serializer):
    answered = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.IntegerField()


class AttemptStateSerializer(serializers.Serializer):
    """Прохождение: прогресс и вопрос, на который нужно ответить (null - опрос пройден)."""

    id = serializers.IntegerField()
    quiz_id = serializers.IntegerField()
    quiz_title = serializers.CharField()
    status = serializers.ChoiceField(choices=Attempt.Status.choices)
    progress = ProgressSerializer()
    next_question = QuestionItemSerializer(allow_null=True)


class AnswerInputSerializer(serializers.Serializer):
    """Ответ на текущий вопрос. Пустой ответ на необязательный вопрос - пропуск."""

    question_id = serializers.IntegerField(min_value=1)
    option_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), default=list, max_length=50
    )
    custom_text = serializers.CharField(max_length=1000, allow_blank=True, default="")


class AttemptSerializer(serializers.ModelSerializer):
    quiz_id = serializers.IntegerField(source="quiz.id")
    quiz_title = serializers.CharField(source="quiz.title")
    answered_count = serializers.IntegerField()
    questions_count = serializers.IntegerField()

    class Meta:
        model = Attempt
        fields = (
            "id",
            "quiz_id",
            "quiz_title",
            "status",
            "started_at",
            "finished_at",
            "answered_count",
            "questions_count",
        )
