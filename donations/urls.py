from django.urls import path

from . import views

app_name = "donations"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("new/", views.donation_create, name="donation_create"),
    path("reports/", views.report, name="report"),
    path("reports/export.csv", views.report_export, name="report_export"),
]
