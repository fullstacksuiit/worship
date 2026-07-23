from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("rentals/", views.booking_list, name="list"),
    path("rentals/add/", views.booking_add, name="add"),
    path("rentals/<int:pk>/", views.booking_detail, name="detail"),
    path("rentals/<int:pk>/edit/", views.booking_edit, name="edit"),
    path("rentals/<int:pk>/delete/", views.booking_delete, name="delete"),
    path("rentals/<int:pk>/paid/", views.booking_mark_paid, name="mark_paid"),
    path("rentals/<int:pk>/cancel/", views.booking_cancel, name="cancel"),
    path("rentals/properties/", views.property_list, name="property_list"),
    path("rentals/properties/add/", views.property_add, name="property_add"),
    path("rentals/properties/<int:pk>/edit/", views.property_edit, name="property_edit"),
    path("rentals/properties/<int:pk>/delete/", views.property_delete, name="property_delete"),
]
