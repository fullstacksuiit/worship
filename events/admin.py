from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "kind",
        "starts_at",
        "location",
        "recurrence",
        "attendance",
        "organization",
    )
    list_filter = ("organization", "kind", "recurrence")
    search_fields = ("title", "location", "description")
    date_hierarchy = "starts_at"
    list_select_related = ("organization", "lead")
    autocomplete_fields = ("lead",)
