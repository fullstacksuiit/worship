from django.conf import settings
from django.db import models


class FaithTradition(models.TextChoices):
    """The faith traditions this platform serves, and the name each uses
    for its place of worship."""

    ISLAM = "islam", "Mosque (Islam)"
    HINDUISM = "hinduism", "Mandir (Hinduism)"
    CHRISTIANITY = "christianity", "Church (Christianity)"
    SIKHISM = "sikhism", "Gurudwara (Sikhism)"
    BUDDHISM = "buddhism", "Temple (Buddhism)"
    JUDAISM = "judaism", "Synagogue (Judaism)"
    JAINISM = "jainism", "Derasar (Jainism)"
    BAHAI = "bahai", "Bahá'í House of Worship"


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


# Suggested membership levels (congregation/committee standing) to seed for each
# faith. Each entry is (code, name) and is listed in rank order — "General" is the
# everyday member every tradition shares; the rest are common leadership/office
# titles. These are starting points an org can rename, reorder, or disable; the
# model imposes no faith-specific rules.
DEFAULT_MEMBERSHIP_LEVELS = {
    FaithTradition.ISLAM: [
        ("general", "General"),
        ("sadar", "Sadar (President)"),
        ("imam", "Imam"),
        ("mutawalli", "Mutawalli (Trustee)"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.HINDUISM: [
        ("general", "General"),
        ("pradhan", "Pradhan (President)"),
        ("pujari", "Pujari (Priest)"),
        ("trustee", "Trustee"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.CHRISTIANITY: [
        ("general", "General"),
        ("pastor", "Pastor"),
        ("elder", "Elder"),
        ("deacon", "Deacon"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.SIKHISM: [
        ("general", "General"),
        ("pradhan", "Pradhan (President)"),
        ("granthi", "Granthi"),
        ("sevadar", "Sevadar"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.BUDDHISM: [
        ("general", "General"),
        ("abbot", "Abbot"),
        ("bhikkhu", "Bhikkhu (Monk)"),
        ("lay_leader", "Lay Leader"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.JUDAISM: [
        ("general", "General"),
        ("president", "President"),
        ("rabbi", "Rabbi"),
        ("cantor", "Cantor"),
        ("gabbai", "Gabbai"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.JAINISM: [
        ("general", "General"),
        ("president", "President"),
        ("pujari", "Pujari (Priest)"),
        ("trustee", "Trustee"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
    FaithTradition.BAHAI: [
        ("general", "General"),
        ("chair", "Assembly Chair"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
    ],
}


class MembershipLevel(TenantScopedModel):
    """A member's standing within the organization (e.g. General, Sadar, Pastor).
    The titles vary by faith — see DEFAULT_MEMBERSHIP_LEVELS — and each org keeps
    and edits its own set. `order` gives them a sensible rank for display."""

    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_membership_level_code_per_org",
            ),
        ]

    def __str__(self):
        return self.name


class Member(TenantScopedModel):
    """A person associated with an organization — congregant, donor, or both.
    Donations may reference a Member, or stand alone for walk-in/anonymous gifts."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    # Standing within the org (faith-aware). Optional, and kept if the level is
    # later deleted would orphan it — so SET_NULL rather than CASCADE.
    level = models.ForeignKey(
        MembershipLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
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
    """A login's role within one organization — what they're allowed to do.
    Owner is the org's main superuser (created at signup); the rest are team
    members the Owner/Admins add. See core.permissions for the capability each
    role grants."""

    OWNER = "owner", "Owner"
    ADMIN = "admin", "Administrator"
    TREASURER = "treasurer", "Treasurer"
    ACCOUNTANT = "accountant", "Accountant"
    STAFF = "staff", "General Member"


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
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivated members keep their history but lose access to "
        "this organization until reactivated.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="unique_user_per_org",
            ),
        ]

    @property
    def role_label(self):
        return OrgRole(self.role).label

    @property
    def is_owner(self):
        return self.role == OrgRole.OWNER

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"
