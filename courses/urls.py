from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("class/<int:grade>/<slug:subject>/", views.syllabus, name="syllabus"),
    path("topic/<int:pk>-<slug:slug>/", views.topic_detail, name="topic"),
    path("quiz/<int:pk>/", views.take_quiz, name="quiz"),
    path("quiz/<int:pk>/report/", views.quiz_report, name="report"),
    path("result/<int:pk>/", views.quiz_result, name="result"),
    path("progress/", views.my_progress, name="progress"),
    path("quiz/from-kit/<int:kit_id>/", views.quiz_from_kit, name="from_kit"),
]
