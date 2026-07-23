from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("members/", views.member_list, name="list"),
    path("members/add/", views.member_add, name="add"),
    path("members/<int:pk>/", views.member_detail, name="detail"),
    path("members/<int:pk>/edit/", views.member_edit, name="edit"),
    path("members/<int:pk>/delete/", views.member_delete, name="delete"),
]
