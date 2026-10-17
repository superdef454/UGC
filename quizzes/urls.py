from django.urls import path

from quizzes import views

urlpatterns = [
    path("quizzes/", views.AvailableQuizListView.as_view(), name="quiz-list"),
    path("my/quizzes/", views.MyQuizListCreateView.as_view(), name="my-quiz-list"),
    path("my/quizzes/<int:pk>/", views.MyQuizDetailView.as_view(), name="my-quiz-detail"),
    path("my/quizzes/<int:pk>/publish/", views.PublishQuizView.as_view(), name="quiz-publish"),
    path("my/quizzes/<int:pk>/close/", views.CloseQuizView.as_view(), name="quiz-close"),
    path(
        "my/quizzes/<int:pk>/questions/order/",
        views.ReorderQuestionsView.as_view(),
        name="quiz-questions-order",
    ),
    path(
        "my/questions/<int:pk>/options/order/",
        views.ReorderOptionsView.as_view(),
        name="question-options-order",
    ),
]
