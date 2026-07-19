from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("purchases/", views.overview, name="overview"),
    path("purchases/new/", views.purchase_create, name="purchase_create"),
    path("purchases/<int:pk>/edit/", views.purchase_edit, name="purchase_edit"),
    path("purchases/<int:pk>/delete/", views.purchase_delete, name="purchase_delete"),
    path("purchases/export.csv", views.purchases_export, name="purchases_export"),
    path("purchases/vendors/", views.vendor_list, name="vendor_list"),
    path("purchases/vendors/<int:pk>/edit/", views.vendor_edit, name="vendor_edit"),
    path("purchases/vendors/<int:pk>/delete/", views.vendor_delete, name="vendor_delete"),
]
