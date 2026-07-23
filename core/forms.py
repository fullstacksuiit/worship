from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .faiths import FAITH_CHOICES
from .models import Category, Invitation, Organization, TeamMember
from .permissions import ADMIN, ROLE_CHOICES, ROLE_HELP


def _split_name(full_name):
    parts = (full_name or "").strip().split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


class UsernameField(forms.CharField):
    """A login name, checked against every login in the app.

    Usernames are shared across all places of worship, so the check has to be
    global — better to say "already taken" while someone is choosing than to
    fail the whole sign-up on save.
    """

    def clean(self, value):
        username = super().clean(value)
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                "That username is already taken — try adding your place or city to it."
            )
        return username


class PasswordPairMixin:
    """Password + confirmation, run through Django's strength validators.

    Checked in `clean()` rather than `clean_password()` so the name and username
    are already known: that's what lets the similarity validator catch the very
    password people reach for first — their own username.
    """

    def clean(self):
        cleaned = super().clean()
        password, confirm = cleaned.get("password"), cleaned.get("password_confirm")

        if password and confirm and password != confirm:
            self.add_error("password_confirm", "The two passwords don't match.")

        if password:
            whoever = User(
                username=cleaned.get("username") or "",
                first_name=cleaned.get("full_name") or "",
            )
            try:
                validate_password(password, user=whoever)
            except forms.ValidationError as errors:
                self.add_error("password", errors)

        return cleaned


class SignupForm(PasswordPairMixin, forms.Form):
    """Register a place of worship: name it, pick its tradition, create its admin.

    One screen on purpose — a place is signed up and usable in a single step,
    with its tradition's vocabulary already in place.
    """

    place_name = forms.CharField(
        max_length=200,
        label="Name of your place of worship",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Jama Masjid, Shri Ram Mandir"}),
    )
    faith = forms.ChoiceField(choices=FAITH_CHOICES, label="Which tradition?")
    city = forms.CharField(max_length=120, required=False, label="City (optional)")

    full_name = forms.CharField(max_length=200, label="Your name")
    username = UsernameField(max_length=150, label="Choose a username")
    password = forms.CharField(widget=forms.PasswordInput, label="Choose a password")
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        org = Organization.objects.create(
            name=data["place_name"],
            faith=data["faith"],
            city=data["city"],
        )
        # Start the place off with its tradition's vocabulary, so the very
        # first entry has sensible categories to pick from.
        Category.seed(org)
        first, last = _split_name(data["full_name"])
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=first,
            last_name=last,
        )
        TeamMember.objects.create(
            user=user, organization=org, role=ADMIN, is_owner=True
        )
        return org, user


class PlaceSettingsForm(forms.ModelForm):
    """What a place can change about itself after sign-up.

    The tradition isn't here on purpose: it seeded the categories and the whole
    app's vocabulary, so switching it later would leave a place's records
    speaking a language its screens no longer use. The second language, though,
    is only ever display — so that one is free to change any day.
    """

    class Meta:
        model = Organization
        fields = ["name", "city", "show_native"]
        labels = {"name": "Name of your place", "city": "City (optional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = self.instance.language
        if language:
            # Name the language in both languages — "Urdu · اردو" — so the
            # switch is obvious to whichever of the two you read.
            self.fields["show_native"].label = (
                f"Show {language['language']} ({language['native_name']}) alongside English"
            )
        else:
            # Nothing to show alongside English, so don't offer a dead switch.
            del self.fields["show_native"]


class CategoryForm(forms.ModelForm):
    """Rename a label, hide it, or add one without waiting to need it.

    Adding here is the rarer path — a label normally appears by being typed into
    a category box. This form exists for the other three things you eventually
    want: fixing a typo that's now on fifty records, retiring a word without
    losing what's filed under it, and setting a place up ahead of time.
    """

    class Meta:
        model = Category
        fields = ["scope", "name", "is_active"]
        labels = {
            "scope": "Where is it offered?",
            "name": "The word itself",
            "is_active": "Offer this label in the category box",
        }
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Electricity"})}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["is_active"].help_text = (
            "Turn off to retire a word — records already filed under it keep it."
        )
        # Moving a label between modules would strand what's filed under it, so
        # once it's in use the scope is settled and the field simply isn't shown.
        if self.instance.pk and self.instance.in_use:
            del self.fields["scope"]

    @property
    def scope(self):
        """The scope being saved — from the form, or fixed by the instance."""
        return self.cleaned_data.get("scope") or self.instance.scope

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        """Reject a word this place already uses here, however it's capitalised.

        The database says the same thing, but as an IntegrityError — this is the
        version that names the clash and puts it under the field.
        """
        cleaned = super().clean()
        name = cleaned.get("name")
        if not name:
            return cleaned

        clash = Category.objects.filter(
            organization=self.organization, scope=self.scope, name__iexact=name
        ).exclude(pk=self.instance.pk)
        if clash.exists():
            where = dict(Category.SCOPE_CHOICES).get(self.scope, "").lower()
            self.add_error(
                "name", f"“{clash.first().name}” is already one of your {where} labels."
            )
        return cleaned


class CategoryMergeForm(forms.Form):
    """Choose the label that everything filed under this one should move to."""

    into = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        label="Move everything to",
        empty_label="Choose a label…",
    )

    def __init__(self, *args, category, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category
        # Same place, same scope: an expense can't end up filed under an event.
        self.fields["into"].queryset = Category.objects.filter(
            organization_id=category.organization_id, scope=category.scope
        ).exclude(pk=category.pk)


ROLE_HELP_TEXT = " · ".join(f"{label}: {ROLE_HELP[val]}" for val, label in ROLE_CHOICES)


class TeamMemberForm(PasswordPairMixin, forms.Form):
    """Add a staff member / volunteer: creates their login and assigns a role."""

    full_name = forms.CharField(max_length=200, label="Full name")
    username = UsernameField(max_length=150, label="Username (to log in)")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )
    role = forms.ChoiceField(choices=ROLE_CHOICES, help_text=ROLE_HELP_TEXT)

    @transaction.atomic
    def save(self, organization):
        data = self.cleaned_data
        first, last = _split_name(data["full_name"])
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=first,
            last_name=last,
        )
        return TeamMember.objects.create(
            user=user, organization=organization, role=data["role"]
        )


class TeamRoleForm(forms.ModelForm):
    """Edit an existing team member's role / active status."""

    class Meta:
        model = TeamMember
        fields = ["role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].help_text = ROLE_HELP_TEXT


class InviteForm(forms.ModelForm):
    """Create a join link for someone who isn't sitting next to you."""

    class Meta:
        model = Invitation
        fields = ["label", "role"]
        labels = {"label": "Who is this link for? (optional)"}
        widgets = {"label": forms.TextInput(attrs={"placeholder": "e.g. Imran — treasurer"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].help_text = ROLE_HELP_TEXT

    def save(self, organization, invited_by, commit=True):
        invite = super().save(commit=False)
        invite.organization = organization
        invite.invited_by = invited_by
        if commit:
            invite.save()
        return invite


class JoinForm(PasswordPairMixin, forms.Form):
    """Accept an invitation: the person names themselves and picks a password.

    The role isn't theirs to choose — it came from whoever made the link.
    """

    full_name = forms.CharField(max_length=200, label="Your name")
    username = UsernameField(max_length=150, label="Choose a username")
    password = forms.CharField(widget=forms.PasswordInput, label="Choose a password")
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )

    @transaction.atomic
    def save(self, invitation):
        data = self.cleaned_data
        first, last = _split_name(data["full_name"])
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=first,
            last_name=last,
        )
        TeamMember.objects.create(
            user=user, organization=invitation.organization, role=invitation.role
        )
        invitation.accept(user)
        return user
