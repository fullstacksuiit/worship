from django.contrib import admin

from .models import Category, Invitation, Organization, TeamMember


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "faith", "city", "created_at")
    list_filter = ("faith",)
    search_fields = ("name", "city")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Categories add themselves as people work — this is only for tidying up:
    renaming a label everywhere at once, or retiring one that's fallen out of use."""

    list_display = ("name", "scope", "is_active", "organization")
    list_filter = ("scope", "is_active", "organization")
    search_fields = ("name",)
    list_editable = ("is_active",)


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_owner", "is_active", "organization")
    list_filter = ("role", "is_owner", "is_active", "organization")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("organization", "role", "label", "status", "expires_at", "accepted_by")
    list_filter = ("role", "organization")
    search_fields = ("label", "token")
    readonly_fields = ("token", "created_at", "accepted_at", "accepted_by")
