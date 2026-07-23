from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Getting in: registering a place, or joining one you were invited to.
    path("signup/", views.signup, name="signup"),
    path("join/<str:token>/", views.join, name="join"),
    path("no-access/", views.paused, name="paused"),
    # The place itself.
    path("settings/", views.place_settings, name="settings"),
    # The words this place files things under.
    path("settings/categories/", views.category_list, name="category_list"),
    path("settings/categories/add/", views.category_add, name="category_add"),
    path("settings/categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("settings/categories/<int:pk>/merge/", views.category_merge, name="category_merge"),
    path("settings/categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    # Team & roles.
    path("team/", views.team_list, name="team_list"),
    path("team/add/", views.team_add, name="team_add"),
    path("team/invite/", views.invite_create, name="invite_create"),
    path("team/invite/<int:pk>/", views.invite_detail, name="invite_detail"),
    path("team/invite/<int:pk>/cancel/", views.invite_revoke, name="invite_revoke"),
    path("team/<int:pk>/edit/", views.team_edit, name="team_edit"),
    path("team/<int:pk>/remove/", views.team_remove, name="team_remove"),
]
