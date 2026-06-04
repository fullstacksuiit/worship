from django.contrib import admin

from .models import Invoice, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "tier",
        "interval",
        "price_amount",
        "currency",
        "is_active",
        "is_public",
    )
    list_filter = ("interval", "is_active", "is_public")
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}


class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0
    fields = ("status", "amount", "currency", "period_start", "period_end", "paid_at")
    readonly_fields = ("created_at",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "plan",
        "status",
        "current_period_end",
        "cancel_at_period_end",
    )
    list_filter = ("status", "plan", "provider")
    search_fields = ("organization__name", "external_subscription_id")
    list_select_related = ("organization", "plan")
    inlines = [InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("subscription", "amount", "currency", "status", "paid_at")
    list_filter = ("status", "currency")
    search_fields = ("subscription__organization__name", "external_invoice_id")
    list_select_related = ("subscription", "subscription__organization")
