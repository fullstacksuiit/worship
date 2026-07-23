from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "start", "location")
    list_filter = ("organization", "category")
    search_fields = ("title", "category__name", "location")
    date_hierarchy = "start"
    filter_horizontal = ("attendees",)
