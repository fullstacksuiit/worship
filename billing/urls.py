from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("billing/", views.overview, name="overview"),
    path("billing/plans/", views.plans, name="plans"),
    path("billing/change/", views.change_plan, name="change_plan"),
    path("billing/cancel/", views.cancel, name="cancel"),
]
