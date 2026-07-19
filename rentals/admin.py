from django.contrib import admin

from .models import (
    PropertyType,
    RentAdjustment,
    RentalUnit,
    RentPayment,
    RentRevision,
)


@admin.register(PropertyType)
class PropertyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "organization")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("organization",)


@admin.register(RentalUnit)
class RentalUnitAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "property_type",
        "tenant_name",
        "monthly_rent",
        "currency",
        "start_date",
        "is_active",
        "organization",
    )
    list_filter = ("organization", "property_type", "is_active")
    search_fields = ("name", "tenant_name", "tenant_phone")
    list_select_related = ("organization", "property_type")


@admin.register(RentPayment)
class RentPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "unit",
        "period_year",
        "period_month",
        "amount",
        "currency",
        "method",
        "paid_on",
        "organization",
    )
    list_filter = ("organization", "method", "period_year", "paid_on")
    search_fields = ("unit__name", "unit__tenant_name", "reference", "note")
    date_hierarchy = "paid_on"
    list_select_related = ("organization", "unit")
    readonly_fields = ("receipt_number",)


@admin.register(RentRevision)
class RentRevisionAdmin(admin.ModelAdmin):
    list_display = (
        "unit",
        "effective_year",
        "effective_month",
        "monthly_rent",
        "reason",
        "organization",
    )
    list_filter = ("organization", "effective_year")
    search_fields = ("unit__name", "unit__tenant_name", "reason")
    list_select_related = ("organization", "unit")


@admin.register(RentAdjustment)
class RentAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "unit",
        "period_year",
        "period_month",
        "amount",
        "reason",
        "dated_on",
        "organization",
    )
    list_filter = ("organization", "period_year", "dated_on")
    search_fields = ("unit__name", "unit__tenant_name", "reason", "note")
    date_hierarchy = "dated_on"
    list_select_related = ("organization", "unit")
