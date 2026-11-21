from django.urls import path

from . import views

app_name = "engagement"

urlpatterns = [
    path("feedback/", views.feedback, name="feedback"),
    path("feedback/thanks/", views.feedback_thanks, name="feedback_thanks"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("newsletter/unsubscribe/<uuid:token>/", views.unsubscribe, name="unsubscribe"),
    path("comments/<int:ct_id>/<int:object_id>/", views.comment_create, name="comment_create"),
    path("comments/<int:pk>/delete/", views.comment_delete, name="comment_delete"),
    path("ratings/<int:ct_id>/<int:object_id>/", views.rate, name="rate"),
]
