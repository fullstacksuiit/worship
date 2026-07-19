from django.contrib import admin

from .models import Budget, Category, Donation, Fund, Pledge, Transaction


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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "code", "organization", "is_active")
    list_filter = ("organization", "kind", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("organization",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "voucher_number",
        "kind",
        "category",
        "party",
        "amount",
        "currency",
        "method",
        "occurred_at",
        "organization",
    )
    list_filter = ("organization", "kind", "category", "method", "occurred_at")
    search_fields = ("party", "reference", "note")
    date_hierarchy = "occurred_at"
    list_select_related = ("organization", "category")
    readonly_fields = ("voucher_number",)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category", "year", "amount", "organization")
    list_filter = ("organization", "year")
    list_select_related = ("organization", "category")


@admin.register(Pledge)
class PledgeAdmin(admin.ModelAdmin):
    list_display = ("member", "fund", "year", "amount", "organization")
    list_filter = ("organization", "year", "fund")
    search_fields = ("member__first_name", "member__last_name")
    list_select_related = ("organization", "member", "fund")
