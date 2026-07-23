import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from .faiths import (
    FAITH_CHOICES, currency_symbol, default_categories, get_preset, get_script,
)
from .permissions import ROLE_CHOICES


class Organization(models.Model):
    """A single place of worship — one signed-up account.

    Every place that signs up gets a row here, and every other record in the app
    hangs off it, so two places never see each other's data. The chosen faith
    drives all faith-aware wording via `preset`, and its second language — Urdu
    in a masjid, Gurmukhi in a gurudwara — via `script`.
    """

    name = models.CharField(max_length=200)
    faith = models.CharField(max_length=20, choices=FAITH_CHOICES)
    city = models.CharField(max_length=120, blank=True)
    # Most traditions come with a language of their own, and the app shows it
    # beside the English wording. A place that would rather read one language
    # only turns this off — it's a preference, not something we decide for them.
    show_native = models.BooleanField(
        default=True,
        verbose_name="Show your language alongside English",
        help_text="Screens show both, so nobody has to read a language they don't.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def preset(self):
        """Faith-aware terminology + defaults for this place."""
        return get_preset(self.faith)

    @property
    def language(self):
        """This tradition's second language, whether or not it's switched on.

        Empty for a tradition that has none — that's what the settings screen
        checks before offering a switch there's nothing to switch.
        """
        return get_script(self.faith)

    @property
    def script(self):
        """The second language to actually render — empty when there's none to show.

        Templates lean on it being falsy: `{% if org.script %}` covers both
        "this tradition has no second language" and "this place turned it off".
        """
        return self.language if self.show_native else {}

    @property
    def native(self):
        """The tradition's words in its own script, keyed like `preset`.

        `{{ org.native.member_term }}` next to `{{ org.preset.member_term }}`;
        a missing key renders as nothing, which is exactly what we want when a
        tradition has no second language.
        """
        return self.script.get("terms", {})

    @property
    def icon(self):
        return self.preset.get("icon", "🏛️")

    @property
    def currency(self):
        return self.preset.get("currency", "INR")

    @property
    def currency_symbol(self):
        return currency_symbol(self.currency)


class Category(models.Model):
    """A label this place defines for itself — the buckets money and events are
    filed under.

    Every place names things its own way, so these are rows, not a fixed list in
    code. A new place is seeded with its tradition's vocabulary at setup, and
    from then on the list grows by simply typing a new word into any category
    box: there is no list to configure before you can record anything.
    """

    INCOME = "income"
    EXPENSE = "expense"
    EVENT = "event"
    PROPERTY = "property"
    SCOPE_CHOICES = [
        (INCOME, "Income"), (EXPENSE, "Expense"), (EVENT, "Event"),
        (PROPERTY, "Property"),
    ]
    SCOPE_ICONS = {INCOME: "💰", EXPENSE: "🧾", EVENT: "📅", PROPERTY: "🏛️"}
    # Where each kind of label is offered — said on the screen that lists them,
    # so nobody has to guess what an "Event" label is for.
    SCOPE_HELP = {
        INCOME: "Offered when you record income.",
        EXPENSE: "Offered when you record an expense.",
        EVENT: "Offered when you schedule an event.",
        PROPERTY: "Offered when you add something you rent out.",
    }

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="categories"
    )
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(
        default=True, help_text="Hidden from suggestions when off; past entries keep it."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            # One label per word per scope, however it happens to be typed.
            models.UniqueConstraint(
                "organization", "scope", Lower("name"), name="unique_category_name"
            )
        ]

    def __str__(self):
        return self.name

    @property
    def icon(self):
        return self.SCOPE_ICONS.get(self.scope, "🏷️")

    @property
    def in_use(self):
        """Is anything filed under this label?

        Reads the `usage` count when the row came from `with_usage()`, and asks
        the database when it didn't — so a plain `Category` answers too.
        """
        if hasattr(self, "usage"):
            return self.usage > 0
        return (
            self.transactions.exists() or self.events.exists() or self.properties.exists()
        )

    @classmethod
    def with_usage(cls, organization):
        """This place's labels, each carrying how many records are filed under it.

        It's the number that decides what can be done with a label: one nothing
        uses can simply go, while one in use can only be merged into another —
        the records have to keep a label either way.
        """
        return cls.objects.filter(organization=organization).annotate(
            usage=models.Count("transactions", distinct=True)
            + models.Count("events", distinct=True)
            + models.Count("properties", distinct=True)
        )

    @transaction.atomic
    def merge_into(self, other):
        """Fold this label into `other`: everything filed here moves across.

        The way to retire a word that's already in use. Nothing is left unfiled,
        and the word you stopped wanting stops being suggested. Returns how many
        records moved.
        """
        if other.pk == self.pk:
            raise ValueError("A label can't be merged into itself.")
        if other.organization_id != self.organization_id or other.scope != self.scope:
            raise ValueError("Labels only merge within one place, and one scope.")
        moved = (
            self.transactions.update(category=other)
            + self.events.update(category=other)
            + self.properties.update(category=other)
        )
        self.delete()
        return moved

    @classmethod
    def names(cls, organization, scope):
        """The labels already in use — what a category box suggests."""
        return list(
            cls.objects.filter(organization=organization, scope=scope, is_active=True)
            .values_list("name", flat=True)
        )

    @classmethod
    def resolve(cls, organization, scope, name):
        """Match what was typed to a label, creating it the first time it's used."""
        name = (name or "").strip()
        if not name:
            return None
        existing = cls.objects.filter(
            organization=organization, scope=scope, name__iexact=name
        ).first()
        if existing:
            return existing
        return cls.objects.create(organization=organization, scope=scope, name=name)

    @classmethod
    def seed(cls, organization):
        """Give a brand-new place its tradition's starting vocabulary."""
        cls.objects.bulk_create(
            [
                cls(organization=organization, scope=scope, name=name)
                for scope, names in default_categories(organization.faith).items()
                for name in names
            ],
            ignore_conflicts=True,
        )


class TeamMember(models.Model):
    """A staff member / volunteer who can log in, with a role that decides what
    they may change.

    This is also what ties a login to a place: every signed-in person has exactly
    one membership, and it is what `request.organization` is resolved from. The
    person who signed the place up is the `is_owner` admin and can't be removed.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_membership"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="team"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_owner = models.BooleanField(
        default=False, help_text="Signed this place up; always admin, can't be removed."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_owner", "user__first_name", "user__username"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Invitation(models.Model):
    """A one-use link that lets someone join a place and pick their own password.

    The alternative — an admin typing a password for them and reading it out — is
    still there; this is for when the person is not standing next to you. A link
    is dead once used or once it expires, so a forwarded message can't leak
    access forever.
    """

    VALID_FOR = timedelta(days=7)

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    label = models.CharField(
        max_length=200, blank=True, help_text="Who this link is for — a reminder for you."
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invitations_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invitation_used",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite to {self.organization} as {self.get_role_display()}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + self.VALID_FOR
        return super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self):
        return self.accepted_at is None and not self.is_expired

    @property
    def status(self):
        if self.accepted_at:
            return "accepted"
        return "expired" if self.is_expired else "pending"

    def get_join_path(self):
        from django.urls import reverse

        return reverse("core:join", args=[self.token])

    def accept(self, user):
        self.accepted_by = user
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_by", "accepted_at"])
