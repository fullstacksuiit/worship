from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("rentals/", views.overview, name="overview"),
    # Property types (Shop, Hall, Room, ...) — org-defined.
    path("rentals/types/", views.property_type_list, name="property_type_list"),
    path("rentals/types/<int:pk>/edit/", views.property_type_edit, name="property_type_edit"),
    path("rentals/types/<int:pk>/delete/", views.property_type_delete, name="property_type_delete"),
    # Rentable units.
    path("rentals/units/new/", views.unit_create, name="unit_create"),
    path("rentals/units/<int:pk>/", views.unit_detail, name="unit_detail"),
    path("rentals/units/<int:pk>/edit/", views.unit_edit, name="unit_edit"),
    path("rentals/units/<int:pk>/delete/", views.unit_delete, name="unit_delete"),
    path("rentals/units/<int:pk>/ledger/", views.unit_ledger, name="unit_ledger"),
    # Rent demand slip (a bill of what's owed for a unit).
    path("rentals/units/<int:pk>/demand/", views.unit_demand, name="unit_demand"),
    # Rent revisions (increase / decrease from a chosen month).
    path("rentals/units/<int:unit_pk>/revisions/new/", views.revision_add, name="revision_add"),
    path("rentals/revisions/<int:pk>/edit/", views.revision_edit, name="revision_edit"),
    path("rentals/revisions/<int:pk>/delete/", views.revision_delete, name="revision_delete"),
    # Rent rebates / concessions (a credit against one month, mirrored to Finance).
    path("rentals/units/<int:unit_pk>/rebates/new/", views.adjustment_add, name="adjustment_add"),
    path("rentals/rebates/<int:pk>/delete/", views.adjustment_delete, name="adjustment_delete"),
    # Rent receipts.
    path("rentals/pay/", views.payment_new, name="payment_new"),
    path("rentals/units/<int:unit_pk>/pay/", views.payment_create, name="payment_create"),
    path("rentals/payments/<int:pk>/edit/", views.payment_edit, name="payment_edit"),
    path("rentals/payments/<int:pk>/slip/", views.payment_slip, name="payment_slip"),
    path("rentals/payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("rentals/payments/export.csv", views.payments_export, name="payments_export"),
]
