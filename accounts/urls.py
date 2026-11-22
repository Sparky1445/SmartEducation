from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
]

# Django's own auth views (password change and reset) keep their usual URL names,
# so they are included outside the "accounts" namespace in smart_education/urls.py.
auth_urlpatterns = [
    path("login/", views.RememberMeLoginView.as_view(), name="login"),
    path("", include("django.contrib.auth.urls")),
]
