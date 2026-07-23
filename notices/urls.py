from django.urls import path

from . import views

app_name = "notices"

urlpatterns = [
    path("notices/", views.notice_list, name="list"),
    path("notices/add/", views.notice_add, name="add"),
    path("notices/<int:pk>/", views.notice_detail, name="detail"),
    path("notices/<int:pk>/edit/", views.notice_edit, name="edit"),
    path("notices/<int:pk>/delete/", views.notice_delete, name="delete"),
]
