from django.urls import path, re_path

from . import views

app_name = "outreach_studio"

urlpatterns = [
    # Public
    path("learn/", views.LearnListView.as_view(), name="learn"),
    re_path(r"^learn/(?P<pk>[0-9]+)-(?P<slug>[-a-zA-Z0-9_]+)/$", views.learn_kit, name="learn_kit"),
    # Teachers
    path("studio/", views.studio_home, name="studio"),
    path("studio/lessons/<int:ct_id>/<int:object_id>/kit/", views.kit_create, name="kit_create"),
    path("studio/kits/<int:pk>/", views.kit_detail, name="kit"),
    path("studio/kits/<int:pk>/status/", views.kit_status_json, name="kit_status"),
    path("studio/kits/<int:pk>/publish/", views.kit_publish, name="kit_publish"),
    path("studio/kits/<int:pk>/unpublish/", views.kit_unpublish, name="kit_unpublish"),
    path("studio/kits/<int:pk>/regenerate/", views.kit_regenerate, name="kit_regenerate"),
    path("studio/items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("studio/items/<int:pk>/approve/", views.item_approve, name="item_approve"),
]
