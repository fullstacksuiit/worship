from django.contrib import admin

from .models import Donation, Fund


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("organization",)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "display_donor",
        "amount",
        "currency",
        "fund",
        "method",
        "received_at",
        "organization",
    )
    list_filter = ("organization", "fund", "method", "received_at")
    search_fields = ("donor_name", "reference", "donor__first_name", "donor__last_name")
    date_hierarchy = "received_at"
    autocomplete_fields = ("donor",)
    list_select_related = ("organization", "fund", "donor")
    readonly_fields = ("receipt_number",)
