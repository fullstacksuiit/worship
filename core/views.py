from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import RestrictedError, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .faiths import faith_options, vocabulary
from .forms import (
    CategoryForm, CategoryMergeForm, InviteForm, JoinForm, PlaceSettingsForm,
    SignupForm, TeamMemberForm, TeamRoleForm,
)
from .models import Category, Invitation, TeamMember
from .navigation import visible_modules
from .permissions import cap_required

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


# --- Signing up & signing in ------------------------------------------------

def signup(request):
    """Register a new place of worship and its first admin.

    Open to anyone: this is how a place gets onto the app. Whoever fills it in
    becomes the owner-admin and lands straight on their own dashboard, with
    their tradition's vocabulary already seeded.
    """
    if getattr(request, "organization", None):
        return redirect("core:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            org, user = form.save()
            login(request, user, backend=AUTH_BACKEND)
            messages.success(
                request, f"Welcome — {org.name} is ready. {org.preset.get('greeting', '')}"
            )
            return redirect("core:dashboard")
    else:
        form = SignupForm()

    return render(request, "core/signup.html", {"form": form, "faiths": faith_options()})


def join(request, token):
    """Accept an invitation link: pick a username and password, and you're in.

    The place and the role are fixed by the link, so there is nothing to get
    wrong here — the person only chooses how they sign in.
    """
    invitation = Invitation.objects.filter(token=token).select_related("organization").first()

    if invitation is None or not invitation.is_usable:
        return render(request, "core/join_invalid.html", {"invitation": invitation}, status=410)

    if request.user.is_authenticated:
        # Already signed in as someone else — joining would swap accounts silently.
        return render(request, "core/join_invalid.html",
                      {"invitation": invitation, "already_signed_in": True}, status=409)

    if request.method == "POST":
        form = JoinForm(request.POST)
        if form.is_valid():
            user = form.save(invitation)
            login(request, user, backend=AUTH_BACKEND)
            messages.success(request, f"Welcome to {invitation.organization.name}.")
            return redirect("core:dashboard")
    else:
        form = JoinForm()

    return render(request, "core/join.html", {"form": form, "invitation": invitation})


@login_required
def paused(request):
    """Signed in, but the membership was switched off or removed."""
    return render(request, "core/paused.html", status=403)


# --- Dashboard --------------------------------------------------------------

@login_required
def dashboard(request):
    """Home screen — a faith-aware welcome, today's numbers, and the way in to
    every module. The module cards come from `core.navigation`, the same list
    the sidebar is built from, so home and nav can never drift apart."""
    org = request.organization

    # Imported here, not at module load: core is the app everything else
    # depends on, so it must not import them while the registry is loading.
    from events.models import Event
    from finance.models import Transaction
    from members.models import Member
    from notices.models import Notice
    from rentals.models import Booking

    today = timezone.localdate()
    now = timezone.now()

    money = Transaction.objects.filter(organization=org, date__year=today.year)
    income = money.filter(kind=Transaction.INCOME).aggregate(s=Sum("amount"))["s"] or 0
    expense = money.filter(kind=Transaction.EXPENSE).aggregate(s=Sum("amount"))["s"] or 0

    upcoming = list(
        Event.objects.filter(organization=org, start__gte=now).order_by("start")[:3]
    )
    unpaid = Booking.objects.filter(
        organization=org, is_paid=False, status=Booking.BOOKED
    ).count()

    return render(request, "core/dashboard.html", {
        "org": org,
        "today": today,
        # Skip "Home" itself — you're already on it.
        "modules": visible_modules(org, request.user)[1:],
        "stats": {
            "people": Member.objects.filter(organization=org, is_active=True).count(),
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "year": today.year,
            "unpaid_rentals": unpaid,
        },
        "upcoming": upcoming,
        "notices": Notice.objects.filter(organization=org)[:3],
    })


# --- The place itself (admin only) -----------------------------------------

@login_required
@cap_required("manage_team")
def place_settings(request):
    """Rename the place, correct its city, choose whether screens are bilingual."""
    org = request.organization
    if request.method == "POST":
        form = PlaceSettingsForm(request.POST, instance=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved.")
            return redirect("core:settings")
    else:
        form = PlaceSettingsForm(instance=org)
    return render(request, "core/settings.html", {
        "form": form,
        "org": org,
        # Shown next to the switch, so "both languages" is something you can see
        # before you decide, not a promise you have to take on trust.
        "vocabulary": vocabulary(org.faith),
    })


# --- Categories (admin only) ------------------------------------------------
#
# Nobody is sent here to get started: a label appears the moment someone types a
# new word into a category box, and that stays true. This is the screen for what
# happens later — the typo that's now on fifty entries, the word two people
# spelled two ways, the one nobody uses any more.

def _records(count):
    """"3 records" / "1 record" — the phrase these screens keep needing."""
    return f"{count} record{'' if count == 1 else 's'}"


@login_required
@cap_required("manage_categories")
def category_list(request):
    """Every label this place files things under, grouped by where it's offered."""
    categories = Category.with_usage(request.organization)
    by_scope = {}
    for category in categories:
        by_scope.setdefault(category.scope, []).append(category)

    return render(request, "core/category_list.html", {
        "groups": [
            {
                "scope": scope,
                "label": label,
                "icon": Category.SCOPE_ICONS.get(scope, "🏷️"),
                "help": Category.SCOPE_HELP.get(scope, ""),
                "items": by_scope.get(scope, []),
            }
            for scope, label in Category.SCOPE_CHOICES
        ],
        "total": len(categories),
    })


@login_required
@cap_required("manage_categories")
def category_add(request):
    org = request.organization
    if request.method == "POST":
        form = CategoryForm(request.POST, organization=org)
        if form.is_valid():
            category = form.save(commit=False)
            category.organization = org
            category.save()
            messages.success(
                request,
                f"“{category.name}” added to your "
                f"{category.get_scope_display().lower()} categories.",
            )
            return redirect("core:category_list")
    else:
        # The "＋ Add" beside a group arrives with that group already chosen.
        scope = request.GET.get("scope")
        form = CategoryForm(organization=org, initial={
            "scope": scope if scope in dict(Category.SCOPE_CHOICES) else Category.INCOME,
        })
    return render(request, "core/category_form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_categories")
def category_edit(request, pk):
    org = request.organization
    category = get_object_or_404(Category.with_usage(org), pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category, organization=org)
        if form.is_valid():
            saved = form.save()
            # A rename isn't local to this screen — say how far it reached.
            if "name" in form.changed_data and category.usage:
                messages.success(
                    request,
                    f"Renamed to “{saved.name}” — the {_records(category.usage)} "
                    "filed under it now read the new word.",
                )
            else:
                messages.success(request, "Changes saved.")
            return redirect("core:category_list")
    else:
        form = CategoryForm(instance=category, organization=org)
    return render(request, "core/category_form.html", {
        "form": form, "mode": "edit", "category": category,
    })


@login_required
@cap_required("manage_categories")
def category_merge(request, pk):
    """Fold one label into another, so a word in use can still be retired."""
    org = request.organization
    category = get_object_or_404(Category.with_usage(org), pk=pk)
    alternatives = Category.objects.filter(
        organization=org, scope=category.scope
    ).exclude(pk=category.pk)

    if not alternatives.exists():
        messages.info(
            request,
            f"“{category.name}” is the only {category.get_scope_display().lower()} "
            "label you have — add the one it should merge into first.",
        )
        return redirect(f"{reverse('core:category_add')}?scope={category.scope}")

    if request.method == "POST":
        form = CategoryMergeForm(request.POST, category=category)
        if form.is_valid():
            target = form.cleaned_data["into"]
            name, moved = category.name, category.merge_into(target)
            messages.success(
                request,
                f"“{name}” merged into “{target.name}”"
                + (f" — {_records(moved)} moved." if moved else "."),
            )
            return redirect("core:category_list")
    else:
        form = CategoryMergeForm(category=category)
    return render(request, "core/category_merge.html", {
        "form": form, "category": category,
    })


@login_required
@cap_required("manage_categories")
def category_delete(request, pk):
    """Delete a label nothing is filed under. One in use is sent to merge instead."""
    org = request.organization
    category = get_object_or_404(Category.with_usage(org), pk=pk)

    if category.usage:
        messages.info(
            request,
            f"“{category.name}” is on {_records(category.usage)} — merge it into "
            "another label instead, so nothing is left unfiled.",
        )
        return redirect("core:category_merge", pk=category.pk)

    if request.method == "POST":
        name = category.name
        try:
            category.delete()
        except RestrictedError:
            # Something was filed under it between the check and the delete.
            messages.error(request, f"“{name}” is in use — merge it into another label.")
            return redirect("core:category_merge", pk=category.pk)
        messages.success(request, f"“{name}” removed.")
        return redirect("core:category_list")

    return render(request, "core/category_confirm_delete.html", {"category": category})


# --- Team & roles (admin only) ---------------------------------------------

@login_required
@cap_required("manage_team")
def team_list(request):
    org = request.organization
    return render(request, "core/team_list.html", {
        "members": TeamMember.objects.filter(organization=org).select_related("user"),
        "invitations": Invitation.objects.filter(organization=org, accepted_at__isnull=True),
    })


@login_required
@cap_required("manage_team")
def team_add(request):
    if request.method == "POST":
        form = TeamMemberForm(request.POST)
        if form.is_valid():
            tm = form.save(organization=request.organization)
            messages.success(request, f"{tm.user.get_full_name() or tm.user.username} added to the team.")
            return redirect("core:team_list")
    else:
        form = TeamMemberForm()
    return render(request, "core/team_form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_team")
def team_edit(request, pk):
    tm = get_object_or_404(TeamMember, pk=pk, organization=request.organization)
    if tm.is_owner:
        messages.error(request, "The owner's role can't be changed.")
        return redirect("core:team_list")
    if request.method == "POST":
        form = TeamRoleForm(request.POST, instance=tm)
        if form.is_valid():
            form.save()
            messages.success(request, "Role updated.")
            return redirect("core:team_list")
    else:
        form = TeamRoleForm(instance=tm)
    return render(request, "core/team_form.html", {"form": form, "mode": "edit", "member": tm})


@login_required
@cap_required("manage_team")
def team_remove(request, pk):
    tm = get_object_or_404(TeamMember, pk=pk, organization=request.organization)
    if tm.is_owner:
        messages.error(request, "The owner of this place can't be removed.")
        return redirect("core:team_list")
    if request.method == "POST":
        name = tm.user.get_full_name() or tm.user.username
        tm.user.delete()  # removes the login and the TeamMember (cascade)
        messages.success(request, f"{name} removed from the team.")
        return redirect("core:team_list")
    return render(request, "core/team_confirm_delete.html", {"member": tm})


# --- Invitations ------------------------------------------------------------

@login_required
@cap_required("manage_team")
def invite_create(request):
    """Make a join link to send someone, instead of typing a password for them."""
    if request.method == "POST":
        form = InviteForm(request.POST)
        if form.is_valid():
            invite = form.save(organization=request.organization, invited_by=request.user)
            return redirect("core:invite_detail", pk=invite.pk)
    else:
        form = InviteForm()
    return render(request, "core/invite_form.html", {"form": form})


@login_required
@cap_required("manage_team")
def invite_detail(request, pk):
    """Show the link, ready to copy — the only place it's displayed."""
    invite = get_object_or_404(Invitation, pk=pk, organization=request.organization)
    url = request.build_absolute_uri(invite.get_join_path())
    return render(request, "core/invite_detail.html", {"invite": invite, "join_url": url})


@login_required
@cap_required("manage_team")
def invite_revoke(request, pk):
    invite = get_object_or_404(Invitation, pk=pk, organization=request.organization,
                              accepted_at__isnull=True)
    if request.method == "POST":
        invite.delete()
        messages.success(request, "Invite link cancelled — it no longer works.")
    return redirect("core:team_list")
