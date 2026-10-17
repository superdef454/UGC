from django.urls import path

from web import views

app_name = "web"

urlpatterns = [
    path("", views.quiz_list, name="quiz-list"),
    path("quizzes/<int:pk>/", views.take_quiz, name="take-quiz"),
    path("attempts/", views.my_attempts, name="my-attempts"),
    path("my/", views.my_quizzes, name="my-quizzes"),
    path("my/new/", views.quiz_builder, name="quiz-builder"),
    path("my/<int:pk>/", views.quiz_detail, name="quiz-detail"),
    path("my/<int:pk>/statistics/", views.quiz_statistics, name="quiz-statistics"),
    path("my/<int:pk>/<str:action>/", views.quiz_action, name="quiz-action"),
]
