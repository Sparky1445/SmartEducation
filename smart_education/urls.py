"""Root URL map for Smart Education.

The AI engine has no public URLs: portal views call ai_engine.services
directly, and run records are visible to staff in the admin only.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.urls import auth_urlpatterns
from media_portal import views as media_views

admin.site.site_header = "Smart Education · Admin"
admin.site.site_title = "Smart Education"
admin.site.index_title = "Site administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(auth_urlpatterns)),  # login (remember me), logout, password change/reset
    path("accounts/", include("accounts.urls")),  # signup, profile
    path("ask/", include("ask.urls")),
    path("repository/", include("repository.urls")),
    path("courses/", include("courses.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("", include("engagement.urls")),
    path("", include("outreach_studio.urls")),
    path("", include("media_portal.urls")),
    path("", media_views.home, name="home"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
