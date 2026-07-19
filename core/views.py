from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from billing.access import within_limit
from billing.models import Plan, Subscription, SubscriptionStatus
from donations.models import DEFAULT_FUNDS, Fund
from donations.models import DEFAULT_CATEGORIES, Category
from rentals.models import DEFAULT_PROPERTY_TYPES, PropertyType

from .context_processors import FAITH_BRANDING
from .forms import (
    MemberForm,
    OrganizationSettingsForm,
    OrgSignupForm,
    TeamMemberForm,
    TeamRoleForm,
)
from .models import (
    DEFAULT_MEMBERSHIP_LEVELS,
    FaithTradition,
    Member,
    MembershipLevel,
    Organization,
    OrgRole,
    UserOrgMembership,
)
from .permissions import ROLE_META, Cap, require_cap
from .preferences import PREFERENCE_GROUP_META


def landing(request):
    """Public marketing page at the site root. Signed-in users skip straight to
    their dashboard; everyone else sees the pitch."""
    if request.user.is_authenticated:
        return redirect("donations:dashboard")

    # Small inline SVGs (24x24, stroke=currentColor) so feature cards stay crisp.
    def _icon(path):
        return mark_safe(
            '<svg class="h-6 w-6" fill="none" stroke="currentColor" '
            'viewBox="0 0 24 24"><path stroke-linecap="round" '
            f'stroke-linejoin="round" stroke-width="2" d="{path}"/></svg>'
        )

    # Derived from FAITH_BRANDING so new traditions show up automatically.
    # Sorted alphabetically and rendered with one shared icon (tinted per
    # accent) so the grid reads as an equal, inclusive set — never a ranking.
    faiths = sorted(
        (
            {"place": FAITH_BRANDING[f]["place"], "accent": FAITH_BRANDING[f]["accent"]}
            for f in FaithTradition
            if f in FAITH_BRANDING
        ),
        key=lambda f: f["place"].lower(),
    )

    context = {
        "stats": [
            (str(len(faiths)), "Faith traditions"),
            ("1 step", "To get started"),
            ("∞", "Members & gifts"),
            ("0", "Spreadsheets needed"),
        ],
        "faiths": faiths,
        "features": [
            {
                "icon": _icon("M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 "
                              "2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 "
                              "0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"),
                "title": "Donations & receipts",
                "body": "Record every gift in seconds. Receipt numbers are assigned "
                        "automatically, with support for cash, card, and bank transfers.",
            },
            {
                "icon": _icon("M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 "
                              "4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-1-7.87"),
                "title": "Member directory",
                "body": "Keep a tidy register of your community with giving history and "
                        "totals for each member at a glance.",
            },
            {
                "icon": _icon("M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 "
                              "002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 "
                              "2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 "
                              "2 0 01-2-2z"),
                "title": "Reports & CSV export",
                "body": "Filter by date range and fund, see totals by method and month, "
                        "then export a clean CSV for your accountant.",
            },
            {
                "icon": _icon("M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 "
                              "01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 "
                              "2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"),
                "title": "Faith-aware branding",
                "body": "The interface adapts its labels and accent colour to your "
                        "tradition — masjid, mandir, church, or gurudwara.",
            },
            {
                "icon": _icon("M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 "
                              "2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 "
                              "012-2h6a2 2 0 012 2v2M7 7h10"),
                "title": "Secure & private",
                "body": "Each worship place is isolated in its own space — your records "
                        "are never visible to another organization.",
            },
            {
                "icon": _icon("M13 10V3L4 14h7v7l9-11h-7z"),
                "title": "Fast & simple",
                "body": "No training required. Volunteers and staff can record a donation "
                        "from any device the moment they sit down.",
            },
        ],
        "steps": [
            {"title": "Register your place", "body": "Pick your tradition and currency, "
             "create your owner account — all in one short form."},
            {"title": "Add funds & members", "body": "Your faith's common funds are seeded "
             "automatically. Add your members whenever you're ready."},
            {"title": "Record & report", "body": "Log donations with automatic receipts and "
             "watch your reports build themselves."},
        ],
    }
    return render(request, "landing.html", context)


def signup(request):
    """Public org self-registration. Creates the Organization, its first Owner
    user, their membership, and seeds the faith's default funds — all atomically
    — then signs the new owner in."""

    # Already signed in? Send them to their dashboard, not a fresh signup.
    if request.user.is_authenticated:
        return redirect("donations:dashboard")

    if request.method == "POST":
        form = OrgSignupForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                org = Organization.objects.create(
                    name=data["org_name"],
                    slug=form.unique_org_slug(),
                    faith_tradition=data["faith_tradition"],
                    currency=data["currency"],
                    email=data["email"],
                )
                user = User.objects.create_user(
                    username=data["username"],
                    email=data["email"],
                    password=data["password1"],
                )
                UserOrgMembership.objects.create(
                    user=user,
                    organization=org,
                    role=OrgRole.OWNER,
                    is_default=True,
                )
                # Grant a lifetime, all-features subscription on signup: attach
                # the top-tier plan (unlimited members/staff, every feature) and
                # leave current_period_end NULL so is_current never lapses.
                top_plan = Plan.objects.order_by("-tier", "price_amount").first()
                if top_plan is not None:
                    Subscription.objects.create(
                        organization=org,
                        plan=top_plan,
                        status=SubscriptionStatus.ACTIVE,
                    )
                Fund.objects.bulk_create(
                    Fund(organization=org, code=code, name=name)
                    for code, name in DEFAULT_FUNDS.get(org.faith_tradition, [])
                )
                # Seed the faith's membership levels (General, Sadar, ...) so the
                # member form has standings to choose from straight away.
                MembershipLevel.objects.bulk_create(
                    MembershipLevel(
                        organization=org, code=code, name=name, order=order
                    )
                    for order, (code, name) in enumerate(
                        DEFAULT_MEMBERSHIP_LEVELS.get(org.faith_tradition, [])
                    )
                )
                # Seed generic income/expense categories so the books are ready
                # to use the moment the org is created.
                Category.objects.bulk_create(
                    Category(organization=org, kind=kind, code=code, name=name)
                    for kind, entries in DEFAULT_CATEGORIES.items()
                    for code, name in entries
                )
                # Seed default rentable property types (Shop, Hall, Room, ...) so
                # the rentals module is ready to add units immediately.
                PropertyType.objects.bulk_create(
                    PropertyType(organization=org, code=code, name=name)
                    for code, name in DEFAULT_PROPERTY_TYPES
                )

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(
                request, f"Welcome! {org.name} is ready to go."
            )
            return redirect("donations:dashboard")
    else:
        form = OrgSignupForm()

    return render(request, "registration/signup.html", {"form": form})


# --- Members ---------------------------------------------------------------


@login_required
@require_cap(Cap.MEMBERS_VIEW)
def member_list(request):
    org = getattr(request, "organization", None)
    if org is None:
        return render(request, "donations/no_org.html")

    query = request.GET.get("q", "").strip()
    members = (
        Member.objects.filter(organization=org)
        .select_related("level")
        .annotate(
            total_given=Sum("donations__amount"),
            gift_count=Count("donations"),
        )
    )
    if query:
        members = members.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    return render(
        request,
        "members/list.html",
        {"members": members, "query": query},
    )


@login_required
@require_cap(Cap.MEMBERS_MANAGE)
def member_create(request):
    org = getattr(request, "organization", None)
    if org is None:
        return render(request, "donations/no_org.html")

    # Enforce the plan's member cap before letting another one be added.
    current_members = Member.objects.filter(organization=org).count()
    if not within_limit(request, "max_members", current_members):
        return redirect("billing:plans")

    if request.method == "POST":
        form = MemberForm(request.POST, organization=org)
        if form.is_valid():
            member = form.save()
            messages.success(request, f"Added {member.full_name}.")
            return redirect("core:member_list")
    else:
        form = MemberForm(organization=org)

    return render(
        request, "members/form.html", {"form": form, "is_edit": False}
    )


@login_required
@require_cap(Cap.MEMBERS_VIEW)
def member_detail(request, pk):
    org = getattr(request, "organization", None)
    if org is None:
        return render(request, "donations/no_org.html")

    member = get_object_or_404(
        Member.objects.select_related("level"), pk=pk, organization=org
    )
    donations = member.donations.select_related("fund").order_by(
        "-received_at", "-created_at"
    )
    totals = donations.aggregate(total=Sum("amount"), count=Count("id"))
    total_given = totals["total"] or 0
    by_fund = list(
        donations.values("fund__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    # Share of the member's total per fund, for proportion bars in the template.
    for row in by_fund:
        row["pct"] = round((row["total"] / total_given) * 100) if total_given else 0

    return render(
        request,
        "members/detail.html",
        {
            "member": member,
            "donations": donations,
            "total_given": total_given,
            "gift_count": totals["count"] or 0,
            "by_fund": by_fund,
        },
    )


@login_required
@require_cap(Cap.MEMBERS_MANAGE)
def member_edit(request, pk):
    org = getattr(request, "organization", None)
    if org is None:
        return render(request, "donations/no_org.html")

    # Scope the lookup to the current org so one tenant can't edit another's.
    member = get_object_or_404(Member, pk=pk, organization=org)

    if request.method == "POST":
        form = MemberForm(request.POST, instance=member, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated {member.full_name}.")
            return redirect("core:member_list")
    else:
        form = MemberForm(instance=member, organization=org)

    return render(
        request,
        "members/form.html",
        {"form": form, "is_edit": True, "member": member},
    )


# --- Organization settings -------------------------------------------------

# Roles permitted to change organization-wide settings.
SETTINGS_ROLES = (OrgRole.OWNER, OrgRole.ADMIN)


@login_required
@require_cap(Cap.SETTINGS_MANAGE)
def org_settings(request):
    """Edit the current organization's profile, locale, and customisable
    preferences. Restricted to Owners and Admins."""
    org = getattr(request, "organization", None)
    if org is None:
        return render(request, "donations/no_org.html")

    role = (
        UserOrgMembership.objects.filter(user=request.user, organization=org)
        .values_list("role", flat=True)
        .first()
    )
    can_edit = role in SETTINGS_ROLES

    if request.method == "POST":
        if not can_edit:
            messages.error(
                request, "You don't have permission to change these settings."
            )
            return redirect("core:org_settings")
        form = OrganizationSettingsForm(request.POST, instance=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("core:org_settings")
    else:
        form = OrganizationSettingsForm(instance=org)

    if not can_edit:
        # Read-only viewers still see their settings, just can't submit.
        for field in form.fields.values():
            field.disabled = True

    # Icons for the two fixed, model-backed sections (Heroicons paths, matching
    # the rest of the UI). Preference-group icons come from the registry.
    PROFILE_ICON = (
        "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
    )
    LOCALE_ICON = (
        "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 "
        "2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 "
        "2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    )

    # One section descriptor per tab: the template iterates these for the tab rail
    # and renders each panel by `key`.
    sections = [
        {
            "key": "profile",
            "label": "Profile",
            "icon": PROFILE_ICON,
            "description": "Your worship place's name, tradition, and contact details.",
        },
        {
            "key": "locale",
            "label": "Locale",
            "icon": LOCALE_ICON,
            "description": "Timezone and the currency used for new records.",
        },
    ]
    for group, fields in form.pref_fields_by_group():
        meta = PREFERENCE_GROUP_META.get(group, {})
        sections.append(
            {
                "key": slugify(group),
                "label": group,
                "icon": meta.get("icon", ""),
                "description": meta.get("description", ""),
                "fields": fields,
            }
        )

    return render(
        request,
        "core/settings.html",
        {
            "form": form,
            "can_edit": can_edit,
            "sections": sections,
        },
    )


# --- Team / user access ----------------------------------------------------


@login_required
@require_cap(Cap.TEAM_MANAGE)
def team_list(request):
    """Everyone with a login to this organization, with their role and status.
    Owners/Admins land here to add, re-role, or deactivate team members."""
    org = request.organization
    memberships = (
        UserOrgMembership.objects.filter(organization=org)
        .select_related("user")
        .order_by("-is_active", "role", "user__username")
    )
    return render(
        request,
        "team/list.html",
        {"memberships": memberships, "role_meta": ROLE_META},
    )


@login_required
@require_cap(Cap.TEAM_MANAGE)
def team_add(request):
    """Create a new login for the org and attach it with a chosen role."""
    org = request.organization

    # Respect the plan's staff-login cap before adding another.
    current_users = UserOrgMembership.objects.filter(organization=org).count()
    if not within_limit(request, "max_users", current_users):
        messages.info(
            request,
            "You've reached your plan's team-member limit — upgrade to add more.",
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = TeamMemberForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data["username"],
                    email=data["email"],
                    password=data["password1"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                )
                UserOrgMembership.objects.create(
                    user=user,
                    organization=org,
                    role=data["role"],
                )
            messages.success(
                request,
                f"Added {user.get_username()} to the team. Share their sign-in "
                "details so they can log in.",
            )
            return redirect("core:team_list")
    else:
        form = TeamMemberForm()

    return render(
        request,
        "team/form.html",
        {"form": form, "role_meta": ROLE_META},
    )


@login_required
@require_cap(Cap.TEAM_MANAGE)
def team_edit(request, pk):
    """Change a team member's role or deactivate them. The owner's membership
    and your own can't be edited here — guarding against self-lockout and
    removing the org's only owner."""
    org = request.organization
    membership = get_object_or_404(
        UserOrgMembership.objects.select_related("user"),
        pk=pk,
        organization=org,
    )

    if membership.is_owner:
        messages.error(request, "The owner's role can't be changed here.")
        return redirect("core:team_list")
    if membership.user_id == request.user.id:
        messages.error(request, "You can't change your own role or access.")
        return redirect("core:team_list")

    if request.method == "POST":
        form = TeamRoleForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Updated {membership.user.get_username()}."
            )
            return redirect("core:team_list")
    else:
        form = TeamRoleForm(instance=membership)

    return render(
        request,
        "team/form.html",
        {"form": form, "membership": membership, "role_meta": ROLE_META},
    )


@login_required
@require_cap(Cap.TEAM_MANAGE)
def team_remove(request, pk):
    """Remove a team member from the organization (POST only). Deletes the
    membership, not the underlying login — the person simply loses access."""
    org = request.organization
    membership = get_object_or_404(
        UserOrgMembership.objects.select_related("user"),
        pk=pk,
        organization=org,
    )

    if membership.is_owner:
        messages.error(request, "The owner can't be removed from the team.")
        return redirect("core:team_list")
    if membership.user_id == request.user.id:
        messages.error(request, "You can't remove yourself from the team.")
        return redirect("core:team_list")

    if request.method == "POST":
        username = membership.user.get_username()
        membership.delete()
        messages.success(request, f"Removed {username} from the team.")
    return redirect("core:team_list")
