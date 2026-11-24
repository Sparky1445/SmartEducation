from django.urls import path, re_path

from . import views

app_name = "media_portal"

urlpatterns = [
    path("news/", views.ArticleListView.as_view(), name="news"),
    path("news/feed/", views.NewsFeed(), name="feed"),
    re_path(r"^news/(?P<year>20[0-9]{2})/$", views.ArticleListView.as_view(), name="news_year"),
    re_path(r"^news/(?P<year>20[0-9]{2})/(?P<slug>[-\w]+)/$", views.article_detail, name="article"),
    path("news/from-kit/<int:kit_id>/", views.article_from_kit, name="from_kit"),
    path("events/", views.EventListView.as_view(), name="events"),
    path("events/<int:pk>-<slug:slug>/", views.event_detail, name="event"),
    path("events/<int:pk>/calendar.ics", views.event_ics, name="event_ics"),
    path("announcements/<int:pk>/hide/", views.hide_announcement, name="hide_announcement"),
]
