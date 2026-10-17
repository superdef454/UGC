from django.urls import path

from analytics import views

urlpatterns = [
    path(
        "quizzes/<int:quiz_id>/statistics/",
        views.QuizStatisticsView.as_view(),
        name="quiz-statistics",
    ),
]
