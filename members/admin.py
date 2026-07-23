from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "household", "join_date", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "phone", "household", "email")
