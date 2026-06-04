from django.conf import settings
from django.db import models


class FaithTradition(models.TextChoices):
    """The faith traditions this platform serves, and the name each uses
    for its place of worship."""

    ISLAM = "islam", "Mosque (Islam)"
    HINDUISM = "hinduism", "Mandir (Hinduism)"
    CHRISTIANITY = "christianity", "Church (Christianity)"
    SIKHISM = "sikhism", "Gurudwara (Sikhism)"


class Organization(models.Model):
    """A single worship place. This is the tenant: every other record in the
    system belongs to exactly one Organization and is isolated from the rest."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    faith_tradition = models.CharField(
        max_length=20, choices=FaithTradition.choices
    )

    # Contact / locale
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    # ISO 4217 currency code used for donations, e.g. USD, GBP, INR, PKR.
    currency = models.CharField(max_length=3, default="USD")

    is_active = models.BooleanField(default=True)

    # Customisable settings the org can change for itself, stored as a flat
    # key→value map so new options can be added (see core.preferences) without a
    # migration. Read through `pref()` so defaults are applied consistently.
    preferences = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def pref(self, key):
        """Return a customisable setting's value, falling back to the registry
        default when the org hasn't set it."""
        from .preferences import preference_default

        value = (self.preferences or {}).get(key)
        if value in (None, ""):
            return preference_default(key)
        return value

    def __str__(self):
        return self.name


class TenantScopedModel(models.Model):
    """Abstract base for any record owned by an Organization. Inherit from this
    instead of models.Model so tenant isolation stays consistent across apps."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Member(TenantScopedModel):
    """A person associated with an organization — congregant, donor, or both.
    Donations may reference a Member, or stand alone for walk-in/anonymous gifts."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            # Same email can't appear twice within one organization (when given).
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=~models.Q(email=""),
                name="unique_member_email_per_org",
            ),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name or f"Member #{self.pk}"


class OrgRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Administrator"
    TREASURER = "treasurer", "Treasurer"
    STAFF = "staff", "Staff"


class UserOrgMembership(models.Model):
    """Links a login (User) to an Organization with a role. This is how the app
    knows which tenant a signed-in user belongs to; a user may belong to more
    than one organization and switch between them."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20, choices=OrgRole.choices, default=OrgRole.STAFF
    )
    is_default = models.BooleanField(
        default=False,
        help_text="The org this user lands on at login when they have several.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="unique_user_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"
