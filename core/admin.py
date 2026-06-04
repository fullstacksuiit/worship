from django.contrib import admin

from .models import Member, Organization, UserOrgMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "faith_tradition", "currency", "is_active")
    list_filter = ("faith_tradition", "is_active")
    search_fields = ("name", "email", "phone")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "organization", "email", "phone", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("first_name", "last_name", "email", "phone")
    list_select_related = ("organization",)


@admin.register(UserOrgMembership)
class UserOrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_default")
    list_filter = ("organization", "role")
    search_fields = ("user__username", "organization__name")
    list_select_related = ("user", "organization")
