from django.urls import path

from quizzes import views

urlpatterns = [
    path("quizzes/", views.QuizListCreateView.as_view(), name="quiz-list"),
    path("quizzes/<int:quiz_id>/", views.QuizDetailView.as_view(), name="quiz-detail"),
    path("quizzes/<int:quiz_id>/publish/", views.PublishQuizView.as_view(), name="quiz-publish"),
    path("quizzes/<int:quiz_id>/close/", views.CloseQuizView.as_view(), name="quiz-close"),
    path(
        "quizzes/<int:quiz_id>/questions/order/",
        views.QuestionOrderView.as_view(),
        name="quiz-question-order",
    ),
    path(
        "quizzes/<int:quiz_id>/questions/<int:question_id>/options/order/",
        views.OptionOrderView.as_view(),
        name="question-option-order",
    ),
]
