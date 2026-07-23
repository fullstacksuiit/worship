from django.contrib import admin

from .models import Booking, Property


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "organization")
    list_filter = ("is_active", "organization")
    search_fields = ("name",)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("property", "renter_name", "start_date", "end_date", "rent_amount", "is_paid", "status")
    list_filter = ("status", "is_paid", "organization", "property")
    search_fields = ("renter_name", "renter_phone", "purpose")
    date_hierarchy = "start_date"
