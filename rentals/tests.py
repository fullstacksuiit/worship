from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import Plan
from billing.services import start_subscription
from core.models import Organization, OrgRole, UserOrgMembership
from donations.models import Category, CategoryKind, Transaction

from .models import SHOP_RENT_CATEGORY_CODE, RentPayment, Shop


def make_org(name="Test Org", slug="test-org", currency="GBP"):
    return Organization.objects.create(
        name=name, slug=slug, faith_tradition="islam", currency=currency
    )


class ShopModelTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def test_currency_defaults_from_org(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
        )
        self.assertEqual(shop.currency, "GBP")

    def test_months_due_inclusive_of_start_month(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
        )
        # Jan, Feb, Mar -> 3 months due by mid-March.
        self.assertEqual(shop.months_due(as_of=date(2026, 3, 15)), 3)

    def test_months_due_zero_before_start(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 6, 1),
        )
        self.assertEqual(shop.months_due(as_of=date(2026, 1, 1)), 0)

    def test_inactive_shop_accrues_no_rent(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
            is_active=False,
        )
        self.assertEqual(shop.months_due(as_of=date(2026, 3, 1)), 0)
        self.assertEqual(shop.expected_to_date(as_of=date(2026, 3, 1)), Decimal("0"))

    def test_balance_reflects_payments(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
        )
        RentPayment.objects.create(
            organization=self.org, shop=shop, period_year=2026, period_month=1,
            amount=Decimal("100"), paid_on=date(2026, 1, 5),
        )
        # 3 months due (300), one month paid (100) -> 200 outstanding.
        self.assertEqual(shop.balance(as_of=date(2026, 3, 1)), Decimal("200"))

    def test_opening_balance_adds_to_outstanding(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
            opening_balance=Decimal("50"),
        )
        # 3 months due (300) + 50 carried in, nothing paid -> 350 owed.
        self.assertEqual(shop.balance(as_of=date(2026, 3, 1)), Decimal("350"))

    def test_negative_opening_balance_is_a_credit(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
            opening_balance=Decimal("-30"),
        )
        # 1 month due (100) less a 30 credit carried in -> 70 owed.
        self.assertEqual(shop.balance(as_of=date(2026, 1, 15)), Decimal("70"))

    def test_ledger_runs_a_balance(self):
        shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
            opening_balance=Decimal("50"),
        )
        RentPayment.objects.create(
            organization=self.org, shop=shop, period_year=2026, period_month=1,
            amount=Decimal("120"), paid_on=date(2026, 1, 10),
        )
        entries = shop.ledger(as_of=date(2026, 2, 15))
        # Opening (50), Jan rent (100), Jan payment (120), Feb rent (100).
        self.assertEqual([e["kind"] for e in entries],
                         ["opening", "charge", "payment", "charge"])
        # Running balance after each: 50, 150, 30, 130.
        self.assertEqual([e["running"] for e in entries],
                         [Decimal("50"), Decimal("150"), Decimal("30"), Decimal("130")])
        # And it ties out to balance().
        self.assertEqual(entries[-1]["running"], shop.balance(as_of=date(2026, 2, 15)))


class RentPaymentModelTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
        )

    def test_receipt_numbers_increment_per_org(self):
        p1 = RentPayment.objects.create(
            organization=self.org, shop=self.shop, period_year=2026,
            period_month=1, amount=Decimal("100"), paid_on=date(2026, 1, 5),
        )
        p2 = RentPayment.objects.create(
            organization=self.org, shop=self.shop, period_year=2026,
            period_month=2, amount=Decimal("100"), paid_on=date(2026, 2, 5),
        )
        self.assertEqual(p1.receipt_number, 1)
        self.assertEqual(p2.receipt_number, 2)

    def test_receipt_numbers_independent_between_orgs(self):
        other = make_org(name="Other", slug="other")
        other_shop = Shop.objects.create(
            organization=other, name="Kiosk", shopkeeper_name="Sam",
            monthly_rent=Decimal("50"), start_date=date(2026, 1, 1),
        )
        RentPayment.objects.create(
            organization=self.org, shop=self.shop, period_year=2026,
            period_month=1, amount=Decimal("100"), paid_on=date(2026, 1, 5),
        )
        p = RentPayment.objects.create(
            organization=other, shop=other_shop, period_year=2026,
            period_month=1, amount=Decimal("50"), paid_on=date(2026, 1, 5),
        )
        self.assertEqual(p.receipt_number, 1)


class RentalsViewTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.user = User.objects.create_user("owner", password="pw")
        UserOrgMembership.objects.create(
            user=self.user, organization=self.org,
            role=OrgRole.OWNER, is_default=True,
        )
        plan = Plan.objects.create(
            code="rentals-test", name="Rentals Test", tier=1,
            features={"rentals": True},
        )
        start_subscription(self.org, plan)
        self.shop = Shop.objects.create(
            organization=self.org, name="Shop 1", shopkeeper_name="Ali",
            monthly_rent=Decimal("100"), start_date=date(2026, 1, 1),
        )
        self.client.force_login(self.user)

    def test_overview_renders(self):
        resp = self.client.get(reverse("rentals:overview"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["shop_count"], 1)

    def test_payment_create_posts_finance_income(self):
        resp = self.client.post(
            reverse("rentals:payment_create", args=[self.shop.pk]),
            {
                "period_month": "1",
                "period_year": "2026",
                "amount": "100",
                "method": "cash",
                "paid_on": "2026-01-05",
                "reference": "",
                "note": "",
            },
        )
        self.assertRedirects(resp, reverse("rentals:shop_detail", args=[self.shop.pk]))
        payment = RentPayment.objects.get(organization=self.org)
        self.assertEqual(payment.recorded_by, self.user)
        self.assertEqual(payment.receipt_number, 1)
        # A mirroring finance income entry was created and linked.
        self.assertIsNotNone(payment.transaction)
        txn = payment.transaction
        self.assertEqual(txn.kind, CategoryKind.INCOME)
        self.assertEqual(txn.amount, Decimal("100"))
        self.assertEqual(txn.category.code, SHOP_RENT_CATEGORY_CODE)
        # And the Shop Rent category exists for the org now.
        self.assertTrue(
            Category.objects.filter(
                organization=self.org, code=SHOP_RENT_CATEGORY_CODE
            ).exists()
        )

    def test_payment_new_picks_shop_and_posts_finance(self):
        # The standalone "Record rent" form chooses the shop from a dropdown
        # rather than the URL, then posts the same receipt + finance entry.
        resp = self.client.post(
            reverse("rentals:payment_new"),
            {
                "shop": str(self.shop.pk),
                "period_month": "1",
                "period_year": "2026",
                "amount": "100",
                "method": "cash",
                "paid_on": "2026-01-05",
                "reference": "",
                "note": "",
            },
        )
        self.assertRedirects(resp, reverse("rentals:shop_detail", args=[self.shop.pk]))
        payment = RentPayment.objects.get(organization=self.org)
        self.assertEqual(payment.shop, self.shop)
        self.assertEqual(payment.recorded_by, self.user)
        self.assertIsNotNone(payment.transaction)
        self.assertEqual(payment.transaction.amount, Decimal("100"))

    def test_payment_new_form_only_offers_own_active_shops(self):
        # Inactive shops and other orgs' shops are not selectable here.
        Shop.objects.create(
            organization=self.org, name="Closed", shopkeeper_name="Gone",
            monthly_rent=Decimal("80"), start_date=date(2026, 1, 1), is_active=False,
        )
        other = make_org(name="Other", slug="other")
        Shop.objects.create(
            organization=other, name="Kiosk", shopkeeper_name="Sam",
            monthly_rent=Decimal("50"), start_date=date(2026, 1, 1),
        )
        resp = self.client.get(reverse("rentals:payment_new"))
        self.assertEqual(resp.status_code, 200)
        shop_field = resp.context["form"].fields["shop"]
        self.assertEqual(list(shop_field.queryset), [self.shop])

    def test_gate_redirects_without_feature(self):
        # An org whose plan lacks "rentals" is bounced to the pricing page.
        other = make_org(name="Free Org", slug="free-org")
        user = User.objects.create_user("free", password="pw")
        UserOrgMembership.objects.create(
            user=user, organization=other, role=OrgRole.OWNER, is_default=True
        )
        plan = Plan.objects.create(
            code="free-test", name="Free Test", tier=0, features={"rentals": False}
        )
        start_subscription(other, plan)
        self.client.force_login(user)
        resp = self.client.get(reverse("rentals:overview"))
        self.assertRedirects(resp, reverse("billing:plans"))

    def test_ledger_renders(self):
        RentPayment.objects.create(
            organization=self.org, shop=self.shop, period_year=2026,
            period_month=1, amount=Decimal("100"), paid_on=date(2026, 1, 5),
        )
        resp = self.client.get(reverse("rentals:shop_ledger", args=[self.shop.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["balance"], self.shop.balance())

    def test_detail_does_not_leak_other_orgs(self):
        other = make_org(name="Other", slug="other")
        other_shop = Shop.objects.create(
            organization=other, name="Kiosk", shopkeeper_name="Sam",
            monthly_rent=Decimal("50"), start_date=date(2026, 1, 1),
        )
        resp = self.client.get(
            reverse("rentals:shop_detail", args=[other_shop.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def _record_payment(self, amount="100", month="1"):
        """Post a rent receipt through the view so it gets its mirroring finance
        entry, then return the created RentPayment."""
        self.client.post(
            reverse("rentals:payment_create", args=[self.shop.pk]),
            {
                "period_month": month, "period_year": "2026", "amount": amount,
                "method": "cash", "paid_on": "2026-01-05", "reference": "", "note": "",
            },
        )
        return RentPayment.objects.get(shop=self.shop, period_month=int(month))

    def test_shop_delete_removes_shop_and_reverses_finance(self):
        payment = self._record_payment()
        txn_id = payment.transaction_id
        resp = self.client.post(reverse("rentals:shop_delete", args=[self.shop.pk]))
        self.assertRedirects(resp, reverse("rentals:overview"))
        self.assertFalse(Shop.objects.filter(pk=self.shop.pk).exists())
        # Cascade removed the receipt and we reversed its finance income entry.
        self.assertFalse(RentPayment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=txn_id).exists())

    def test_shop_delete_get_shows_confirmation(self):
        resp = self.client.get(reverse("rentals:shop_delete", args=[self.shop.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Shop.objects.filter(pk=self.shop.pk).exists())

    def test_payment_edit_syncs_finance_entry(self):
        payment = self._record_payment(amount="100")
        resp = self.client.post(
            reverse("rentals:payment_edit", args=[payment.pk]),
            {
                "period_month": "2", "period_year": "2026", "amount": "175",
                "method": "bank", "paid_on": "2026-02-09", "reference": "TXN9", "note": "",
            },
        )
        self.assertRedirects(resp, reverse("rentals:shop_detail", args=[self.shop.pk]))
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("175"))
        self.assertEqual(payment.period_month, 2)
        # The mirroring finance entry moved in lock-step (same row, new figures).
        txn = payment.transaction
        self.assertEqual(txn.amount, Decimal("175"))
        self.assertEqual(txn.occurred_at, date(2026, 2, 9))
        self.assertEqual(Transaction.objects.filter(organization=self.org).count(), 1)

    def test_payment_delete_voids_and_reverses_finance(self):
        payment = self._record_payment()
        txn_id = payment.transaction_id
        resp = self.client.post(reverse("rentals:payment_delete", args=[payment.pk]))
        self.assertRedirects(resp, reverse("rentals:shop_detail", args=[self.shop.pk]))
        self.assertFalse(RentPayment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=txn_id).exists())
        # The shop itself is untouched.
        self.assertTrue(Shop.objects.filter(pk=self.shop.pk).exists())

    def test_payment_edit_does_not_leak_other_orgs(self):
        other = make_org(name="Other", slug="other")
        other_shop = Shop.objects.create(
            organization=other, name="Kiosk", shopkeeper_name="Sam",
            monthly_rent=Decimal("50"), start_date=date(2026, 1, 1),
        )
        other_payment = RentPayment.objects.create(
            organization=other, shop=other_shop, period_year=2026,
            period_month=1, amount=Decimal("50"), paid_on=date(2026, 1, 5),
        )
        resp = self.client.get(
            reverse("rentals:payment_edit", args=[other_payment.pk])
        )
        self.assertEqual(resp.status_code, 404)
