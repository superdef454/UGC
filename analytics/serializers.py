from rest_framework import serializers


class OptionReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    count = serializers.IntegerField()
    percent = serializers.IntegerField()
    is_top = serializers.BooleanField()


class QuestionReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    text = serializers.CharField()
    type = serializers.CharField()
    answers_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()
    custom_count = serializers.IntegerField()
    avg_time_seconds = serializers.FloatField(allow_null=True)
    is_slowest = serializers.BooleanField()
    options = OptionReportSerializer(many=True)


class QuizReportSerializer(serializers.Serializer):
    quiz_id = serializers.IntegerField()
    title = serializers.CharField()
    status = serializers.CharField()
    attempts_count = serializers.IntegerField()
    avg_duration_seconds = serializers.FloatField(allow_null=True)
    questions = QuestionReportSerializer(many=True)
    updated_at = serializers.DateTimeField(allow_null=True)
