from django.urls import path

from web import views

app_name = "web"

urlpatterns = [
    path("", views.quiz_list, name="quiz-list"),
    path("quizzes/new/", views.quiz_builder, name="quiz-builder"),
    path("quizzes/authored/", views.authored_quizzes, name="authored-quizzes"),
    path("quizzes/<int:pk>/", views.take_quiz, name="take-quiz"),
    path("quizzes/<int:pk>/start/", views.start_quiz, name="start-quiz"),
    path("quizzes/<int:pk>/manage/", views.quiz_manage, name="quiz-manage"),
    path("quizzes/<int:pk>/statistics/", views.quiz_statistics, name="quiz-statistics"),
    path(
        "quizzes/<int:pk>/publish/", views.quiz_action, {"action": "publish"}, name="quiz-publish"
    ),
    path("quizzes/<int:pk>/close/", views.quiz_action, {"action": "close"}, name="quiz-close"),
    path("attempts/", views.attempt_list, name="attempt-list"),
]
