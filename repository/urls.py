from django.urls import path, re_path

from . import views

app_name = "repository"

urlpatterns = [
    path("", views.ResourceListView.as_view(), name="list"),
    path("subject/<slug:slug>/", views.ResourceListView.as_view(), name="subject"),
    re_path(r"^archive/(?P<year>20[0-9]{2})/$", views.ResourceListView.as_view(), name="archive"),
    path("upload/", views.ResourceCreateView.as_view(), name="upload"),
    path("bookmarks/", views.BookmarkListView.as_view(), name="bookmarks"),
    path("<int:pk>-<slug:slug>/", views.resource_detail, name="detail"),
    path("<int:pk>/edit/", views.ResourceUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ResourceDeleteView.as_view(), name="delete"),
    path("<int:pk>/bookmark/", views.bookmark_toggle, name="bookmark"),
]
