from django.contrib import admin

from .models import Purchase, Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization")
    list_filter = ("organization",)
    search_fields = ("name", "phone")
    list_select_related = ("organization",)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "voucher_number",
        "item",
        "vendor",
        "category",
        "amount",
        "currency",
        "method",
        "purchased_on",
        "organization",
    )
    list_filter = ("organization", "method", "purchased_on")
    search_fields = ("item", "reference", "note", "vendor__name")
    date_hierarchy = "purchased_on"
    list_select_related = ("organization", "vendor", "category")
    readonly_fields = ("voucher_number",)
