from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("money/", views.overview, name="overview"),
    path("money/ledger/", views.ledger, name="ledger"),
    path("money/ledger/export/", views.export_csv, name="export"),
    path("money/add/<str:kind>/", views.add, name="add"),
    path("money/<int:pk>/edit/", views.edit, name="edit"),
    path("money/<int:pk>/delete/", views.delete, name="delete"),
]
