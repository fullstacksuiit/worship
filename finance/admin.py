from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "amount", "category", "party")
    list_filter = ("kind", "organization", "category", "date")
    search_fields = ("category__name", "donor_name", "note")
    date_hierarchy = "date"
