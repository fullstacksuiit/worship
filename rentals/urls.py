from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("rentals/", views.booking_list, name="list"),
    path("rentals/add/", views.booking_add, name="add"),
    path("rentals/<int:pk>/", views.booking_detail, name="detail"),
    path("rentals/<int:pk>/edit/", views.booking_edit, name="edit"),
    path("rentals/<int:pk>/delete/", views.booking_delete, name="delete"),
    path("rentals/<int:pk>/cancel/", views.booking_cancel, name="cancel"),
    path("rentals/<int:pk>/received/", views.booking_payment_add, name="booking_payment"),
    path("rentals/properties/", views.property_list, name="property_list"),
    path("rentals/properties/add/", views.property_add, name="property_add"),
    path("rentals/properties/<int:pk>/edit/", views.property_edit, name="property_edit"),
    path("rentals/properties/<int:pk>/delete/", views.property_delete, name="property_delete"),
    # Units let by the month, and the rent account each tenant keeps.
    path("rentals/tenants/", views.tenancy_list, name="tenancy_list"),
    path("rentals/tenants/add/", views.tenancy_add, name="tenancy_add"),
    path("rentals/tenants/<int:pk>/", views.tenancy_detail, name="tenancy_detail"),
    path("rentals/tenants/<int:pk>/edit/", views.tenancy_edit, name="tenancy_edit"),
    path("rentals/tenants/<int:pk>/end/", views.tenancy_end, name="tenancy_end"),
    path("rentals/tenants/<int:pk>/remove/", views.tenancy_delete, name="tenancy_delete"),
    path("rentals/tenants/<int:pk>/received/", views.payment_add, name="payment_add"),
    path("rentals/tenants/<int:pk>/slip/", views.rent_demand, name="rent_demand"),
    path("rentals/payments/<int:pk>/edit/", views.payment_edit, name="payment_edit"),
    path("rentals/payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("rentals/payments/<int:pk>/receipt/", views.payment_receipt, name="payment_receipt"),
]
