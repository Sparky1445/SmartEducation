from django.urls import path

from . import views

app_name = "ask"

urlpatterns = [
    path("", views.ask_page, name="home"),
    path("<int:pk>/feedback/", views.feedback, name="feedback"),
    path("history/clear/", views.clear_history, name="clear_history"),
]
