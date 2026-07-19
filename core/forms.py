from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils.text import slugify

from .models import FaithTradition, Member, Organization, UserOrgMembership
from .permissions import ASSIGNABLE_ROLE_CHOICES
from .preferences import ORG_PREFERENCES

_INPUT = (
    # Look lives in the global .field-control stylesheet (templates/base.html):
    # brand-tinted focus ring, custom <select> caret, styled date pickers.
    "field-control mt-1 block w-full border px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm"
)

# A short, practical currency list for the regions these communities cluster in.
CURRENCY_CHOICES = [
    ("USD", "USD — US Dollar"),
    ("GBP", "GBP — British Pound"),
    ("EUR", "EUR — Euro"),
    ("INR", "INR — Indian Rupee"),
    ("PKR", "PKR — Pakistani Rupee"),
    ("BDT", "BDT — Bangladeshi Taka"),
    ("CAD", "CAD — Canadian Dollar"),
    ("AUD", "AUD — Australian Dollar"),
]


class OrgSignupForm(forms.Form):
    """Public registration: a worship place signs itself up and creates its
    first (Owner) user in one step."""

    org_name = forms.CharField(
        label="Worship place name",
        max_length=200,
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Al-Noor Masjid"}),
    )
    faith_tradition = forms.ChoiceField(
        choices=FaithTradition.choices,
        widget=forms.Select(attrs={"class": _INPUT}),
    )
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        initial="USD",
        widget=forms.Select(attrs={"class": _INPUT}),
    )

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": _INPUT}),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": _INPUT}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": _INPUT}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords don't match.")
            else:
                # Run Django's configured password validators.
                try:
                    validate_password(p1)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def unique_org_slug(self):
        """Derive a unique slug from the org name (al-noor-masjid, -2, -3...)."""
        base = slugify(self.cleaned_data["org_name"]) or "organization"
        slug, n = base, 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug


class MemberForm(forms.ModelForm):
    """Add/edit a member, scoped to one organization. The org is supplied by the
    view (never the browser) so members can't be created against another tenant."""

    class Meta:
        model = Member
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "level",
            "notes",
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": _INPUT}),
            "last_name": forms.TextInput(attrs={"class": _INPUT}),
            "email": forms.EmailInput(attrs={"class": _INPUT}),
            "phone": forms.TextInput(attrs={"class": _INPUT}),
            "level": forms.Select(attrs={"class": _INPUT}),
            "notes": forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        # Only this org's active levels are selectable (plus whatever is already
        # set on the member, so editing never silently drops a disabled level).
        levels = self.organization.membershiplevels.filter(is_active=True)
        if self.instance.pk and self.instance.level_id:
            levels = self.organization.membershiplevels.filter(
                Q(is_active=True) | Q(pk=self.instance.level_id)
            )
        self.fields["level"].queryset = levels
        self.fields["level"].label = "Membership level"
        self.fields["level"].empty_label = "— No level —"

    def clean_email(self):
        # Enforce the per-org unique-email rule with a friendly message rather
        # than letting it surface as a database IntegrityError.
        email = self.cleaned_data.get("email", "")
        if email:
            dupes = Member.objects.filter(
                organization=self.organization, email__iexact=email
            )
            if self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                raise forms.ValidationError(
                    "Another member in this organization already uses that email."
                )
        return email

    def save(self, commit=True):
        member = super().save(commit=False)
        member.organization = self.organization
        if commit:
            member.save()
        return member


class TeamMemberForm(forms.Form):
    """Owner/Admin creates a new login for their organization and assigns it a
    role. Sets a starting password directly (no email round-trip); the member
    can change it later. The view attaches them to the org via UserOrgMembership."""

    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": _INPUT}),
    )
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": _INPUT}),
    )
    username = forms.CharField(
        max_length=150,
        help_text="What they'll sign in with.",
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. amina"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": _INPUT}),
    )
    role = forms.ChoiceField(
        choices=ASSIGNABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={"class": _INPUT}),
    )
    password1 = forms.CharField(
        label="Temporary password",
        widget=forms.PasswordInput(attrs={"class": _INPUT}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": _INPUT}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords don't match.")
            else:
                try:
                    validate_password(p1)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned


class TeamRoleForm(forms.ModelForm):
    """Edit an existing team member's role and active state. The owner's
    membership is protected — the view never renders this form for it."""

    class Meta:
        model = UserOrgMembership
        fields = ["role", "is_active"]
        widgets = {
            "role": forms.Select(attrs={"class": _INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = ASSIGNABLE_ROLE_CHOICES


# A curated set of common timezones. Kept short and human-friendly rather than
# pulling in the full IANA list, which is overkill for this audience.
TIMEZONE_CHOICES = [
    ("UTC", "UTC"),
    ("Europe/London", "London (GMT/BST)"),
    ("Europe/Paris", "Central Europe (Paris, Berlin)"),
    ("America/New_York", "US Eastern (New York)"),
    ("America/Chicago", "US Central (Chicago)"),
    ("America/Los_Angeles", "US Pacific (Los Angeles)"),
    ("America/Toronto", "Toronto"),
    ("Asia/Karachi", "Pakistan (Karachi)"),
    ("Asia/Kolkata", "India (Kolkata)"),
    ("Asia/Dhaka", "Bangladesh (Dhaka)"),
    ("Asia/Dubai", "Gulf (Dubai)"),
    ("Australia/Sydney", "Sydney"),
]

# Maps a preference "type" to a builder returning (field, is_checkbox). Keeping
# this here means the form supports any preference the registry declares.
_PREF_FIELD_BUILDERS = {
    "bool": lambda spec: forms.BooleanField(
        required=False,
        label=spec["label"],
        help_text=spec.get("help", ""),
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 "
                "text-slate-900 focus:ring-slate-500"
            }
        ),
    ),
    "text": lambda spec: forms.CharField(
        required=False,
        label=spec["label"],
        help_text=spec.get("help", ""),
        widget=forms.TextInput(attrs={"class": _INPUT}),
    ),
    "choice": lambda spec: forms.ChoiceField(
        required=False,
        label=spec["label"],
        help_text=spec.get("help", ""),
        choices=spec["choices"],
        widget=forms.Select(attrs={"class": _INPUT}),
    ),
}

# Preference form fields are namespaced so they can't collide with model fields.
PREF_PREFIX = "pref_"


class OrganizationSettingsForm(forms.ModelForm):
    """Edit an organization's own profile, locale, and customisable preferences.

    The fixed columns (name, contact, locale) are plain ModelForm fields; every
    customisable option is built dynamically from core.preferences.ORG_PREFERENCES
    and round-tripped through the Organization.preferences JSON field, so adding a
    new setting never touches this form."""

    class Meta:
        model = Organization
        fields = [
            "name",
            "faith_tradition",
            "email",
            "phone",
            "address",
            "timezone",
            "currency",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT}),
            "faith_tradition": forms.Select(attrs={"class": _INPUT}),
            "email": forms.EmailInput(attrs={"class": _INPUT}),
            "phone": forms.TextInput(attrs={"class": _INPUT}),
            "address": forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "timezone": forms.Select(attrs={"class": _INPUT}, choices=TIMEZONE_CHOICES),
            "currency": forms.Select(attrs={"class": _INPUT}, choices=CURRENCY_CHOICES),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.preferences or {}
        for spec in ORG_PREFERENCES:
            builder = _PREF_FIELD_BUILDERS[spec["type"]]
            field = builder(spec)
            field.initial = current.get(spec["key"], spec["default"])
            self.fields[PREF_PREFIX + spec["key"]] = field

    def pref_fields_by_group(self):
        """Yield (group, [bound fields]) in registry order for the template."""
        from .preferences import PREFERENCE_GROUP_ORDER

        grouped = {}
        for spec in ORG_PREFERENCES:
            grouped.setdefault(spec["group"], []).append(
                self[PREF_PREFIX + spec["key"]]
            )
        ordered = [g for g in PREFERENCE_GROUP_ORDER if g in grouped]
        ordered += [g for g in grouped if g not in PREFERENCE_GROUP_ORDER]
        return [(g, grouped[g]) for g in ordered]

    def save(self, commit=True):
        org = super().save(commit=False)
        prefs = dict(org.preferences or {})
        for spec in ORG_PREFERENCES:
            prefs[spec["key"]] = self.cleaned_data[PREF_PREFIX + spec["key"]]
        org.preferences = prefs
        if commit:
            org.save()
        return org
