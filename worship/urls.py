"""URL configuration for the worship project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Django's built-in auth views (login, logout, password reset, ...)
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("members.urls")),
    path("", include("finance.urls")),
    path("", include("events.urls")),
    path("", include("notices.urls")),
    path("", include("rentals.urls")),
    path("", include("core.urls")),
]
