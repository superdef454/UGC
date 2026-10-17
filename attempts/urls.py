from django.urls import path

from attempts import views

urlpatterns = [
    path("quizzes/<int:quiz_id>/attempt/", views.QuizAttemptView.as_view(), name="quiz-attempt"),
    path(
        "quizzes/<int:quiz_id>/attempt/answers/",
        views.AttemptAnswerView.as_view(),
        name="quiz-attempt-answers",
    ),
    path("attempts/", views.AttemptListView.as_view(), name="attempt-list"),
]
