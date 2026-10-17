from django.urls import path

from analytics import views

urlpatterns = [
    path(
        "my/quizzes/<int:pk>/statistics/",
        views.QuizStatisticsView.as_view(),
        name="quiz-statistics",
    ),
]
