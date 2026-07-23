from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("events/", views.event_list, name="list"),
    path("events/add/", views.event_add, name="add"),
    path("events/<int:pk>/", views.event_detail, name="detail"),
    path("events/<int:pk>/edit/", views.event_edit, name="edit"),
    path("events/<int:pk>/delete/", views.event_delete, name="delete"),
    path("events/<int:pk>/attendance/", views.event_attendance, name="attendance"),
]
