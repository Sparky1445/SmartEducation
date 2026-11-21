from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("me/", views.StudentDashboardView.as_view(), name="student"),
    path("teacher/", views.TeacherDashboardView.as_view(), name="teacher"),
    path("preferences/", views.set_preference, name="preferences"),
]
