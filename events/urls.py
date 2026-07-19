from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("events/", views.overview, name="overview"),
    path("events/schedule/", views.schedule, name="schedule"),
    path("events/export.csv", views.export_csv, name="export_csv"),
    path("events/new/", views.event_create, name="event_create"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("events/<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("events/<int:pk>/attendance/", views.record_attendance, name="record_attendance"),
    path("events/<int:pk>/duplicate/", views.event_duplicate, name="event_duplicate"),
]
