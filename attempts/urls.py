from django.urls import path

from attempts import views

urlpatterns = [
    path("quizzes/<int:pk>/next-question/", views.NextQuestionView.as_view(), name="next-question"),
    path("quizzes/<int:pk>/answers/", views.AnswerView.as_view(), name="quiz-answer"),
    path("attempts/", views.MyAttemptListView.as_view(), name="my-attempts"),
]
