from django.contrib import admin

from .models import Member, MembershipLevel, Organization, UserOrgMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "faith_tradition", "currency", "is_active")
    list_filter = ("faith_tradition", "is_active")
    search_fields = ("name", "email", "phone")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MembershipLevel)
class MembershipLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "order", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("organization",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "organization", "level", "email", "phone", "is_active")
    list_filter = ("organization", "level", "is_active")
    search_fields = ("first_name", "last_name", "email", "phone")
    list_select_related = ("organization", "level")
    autocomplete_fields = ("level",)


@admin.register(UserOrgMembership)
class UserOrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_default")
    list_filter = ("organization", "role")
    search_fields = ("user__username", "organization__name")
    list_select_related = ("user", "organization")
