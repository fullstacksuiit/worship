from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import Plan
from billing.services import start_subscription
from core.models import Member, Organization, OrgRole, UserOrgMembership

from .models import (
    Category,
    CategoryKind,
    Donation,
    Fund,
    Pledge,
    Transaction,
)


def make_org(name="Test Org", slug="test-org", currency="GBP"):
    return Organization.objects.create(
        name=name, slug=slug, faith_tradition="islam", currency=currency
    )


class TransactionModelTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.expense_cat = Category.objects.create(
            organization=self.org, kind=CategoryKind.EXPENSE,
            code="utilities", name="Utilities",
        )
        self.income_cat = Category.objects.create(
            organization=self.org, kind=CategoryKind.INCOME,
            code="rental", name="Hall Rental",
        )

    def test_currency_defaults_from_org(self):
        txn = Transaction.objects.create(
            organization=self.org, category=self.expense_cat,
            amount=Decimal("50"), occurred_at=date(2026, 1, 1),
        )
        self.assertEqual(txn.currency, "GBP")

    def test_kind_inferred_from_category(self):
        txn = Transaction.objects.create(
            organization=self.org, category=self.income_cat,
            amount=Decimal("100"), occurred_at=date(2026, 1, 1),
        )
        self.assertEqual(txn.kind, CategoryKind.INCOME)

    def test_voucher_numbers_increment_per_org(self):
        t1 = Transaction.objects.create(
            organization=self.org, category=self.expense_cat,
            amount=Decimal("10"), occurred_at=date(2026, 1, 1),
        )
        t2 = Transaction.objects.create(
            organization=self.org, category=self.income_cat,
            amount=Decimal("20"), occurred_at=date(2026, 1, 2),
        )
        self.assertEqual(t1.voucher_number, 1)
        self.assertEqual(t2.voucher_number, 2)

    def test_voucher_numbers_independent_between_orgs(self):
        other = make_org(name="Other", slug="other")
        other_cat = Category.objects.create(
            organization=other, kind=CategoryKind.EXPENSE,
            code="utilities", name="Utilities",
        )
        Transaction.objects.create(
            organization=self.org, category=self.expense_cat,
            amount=Decimal("10"), occurred_at=date(2026, 1, 1),
        )
        t = Transaction.objects.create(
            organization=other, category=other_cat,
            amount=Decimal("99"), occurred_at=date(2026, 1, 1),
        )
        self.assertEqual(t.voucher_number, 1)

    def test_signed_amount(self):
        expense = Transaction.objects.create(
            organization=self.org, category=self.expense_cat,
            amount=Decimal("30"), occurred_at=date(2026, 1, 1),
        )
        income = Transaction.objects.create(
            organization=self.org, category=self.income_cat,
            amount=Decimal("40"), occurred_at=date(2026, 1, 1),
        )
        self.assertEqual(expense.signed_amount, Decimal("-30"))
        self.assertEqual(income.signed_amount, Decimal("40"))


class PledgeModelTests(TestCase):
    def test_fulfilled_amount_counts_only_matching_fund_and_year(self):
        org = make_org()
        member = Member.objects.create(organization=org, first_name="Sam")
        fund = Fund.objects.create(organization=org, code="zakat", name="Zakat")
        other_fund = Fund.objects.create(organization=org, code="gen", name="General")
        pledge = Pledge.objects.create(
            organization=org, member=member, fund=fund,
            year=2026, amount=Decimal("500"),
        )
        # Counts toward the pledge.
        Donation.objects.create(
            organization=org, fund=fund, donor=member,
            amount=Decimal("200"), received_at=date(2026, 3, 1),
        )
        # Wrong fund — ignored.
        Donation.objects.create(
            organization=org, fund=other_fund, donor=member,
            amount=Decimal("100"), received_at=date(2026, 3, 1),
        )
        # Wrong year — ignored.
        Donation.objects.create(
            organization=org, fund=fund, donor=member,
            amount=Decimal("100"), received_at=date(2025, 3, 1),
        )
        self.assertEqual(pledge.fulfilled_amount(), Decimal("200"))


class FinanceViewTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.user = User.objects.create_user("owner", password="pw")
        UserOrgMembership.objects.create(
            user=self.user, organization=self.org,
            role=OrgRole.OWNER, is_default=True,
        )
        # The finance views are gated behind a plan that includes the "finance"
        # feature, so the test org needs a subscription that unlocks it.
        plan = Plan.objects.create(
            code="finance-test", name="Finance Test", tier=1,
            features={"finance": True},
        )
        start_subscription(self.org, plan)
        self.expense_cat = Category.objects.create(
            organization=self.org, kind=CategoryKind.EXPENSE,
            code="utilities", name="Utilities",
        )
        self.client.force_login(self.user)

    def test_overview_combines_donations_and_transactions(self):
        fund = Fund.objects.create(organization=self.org, code="zakat", name="Zakat")
        Donation.objects.create(
            organization=self.org, fund=fund,
            amount=Decimal("300"), received_at=date(2026, 2, 1),
        )
        Transaction.objects.create(
            organization=self.org, category=self.expense_cat,
            amount=Decimal("120"), occurred_at=date(2026, 2, 2),
        )
        resp = self.client.get(reverse("donations:overview") + "?year=2026")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_income"], Decimal("300"))
        self.assertEqual(resp.context["expense_total"], Decimal("120"))
        self.assertEqual(resp.context["net"], Decimal("180"))

    def test_expense_create_assigns_recorder_and_voucher(self):
        resp = self.client.post(
            reverse("donations:expense_create"),
            {
                "category": self.expense_cat.pk,
                "party": "City Power Co",
                "amount": "75.50",
                "method": "bank",
                "occurred_at": "2026-01-15",
                "reference": "INV-9",
                "note": "",
            },
        )
        self.assertRedirects(resp, reverse("donations:transactions"))
        txn = Transaction.objects.get(organization=self.org)
        self.assertEqual(txn.recorded_by, self.user)
        self.assertEqual(txn.kind, CategoryKind.EXPENSE)
        self.assertEqual(txn.voucher_number, 1)

    def test_ledger_does_not_leak_other_orgs(self):
        other = make_org(name="Other", slug="other")
        other_cat = Category.objects.create(
            organization=other, kind=CategoryKind.EXPENSE,
            code="utilities", name="Utilities",
        )
        Transaction.objects.create(
            organization=other, category=other_cat,
            amount=Decimal("999"), occurred_at=date(2026, 1, 1),
        )
        resp = self.client.get(reverse("donations:transactions"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context["transactions"]), [])

    def test_budgets_and_pledges_pages_render(self):
        self.assertEqual(self.client.get(reverse("donations:budgets")).status_code, 200)
        self.assertEqual(self.client.get(reverse("donations:pledges")).status_code, 200)
        self.assertEqual(self.client.get(reverse("donations:categories")).status_code, 200)

    def test_add_category_via_post(self):
        resp = self.client.post(
            reverse("donations:categories"),
            {"kind": "income", "name": "Donations Box", "description": ""},
        )
        self.assertRedirects(resp, reverse("donations:categories"))
        self.assertTrue(
            Category.objects.filter(
                organization=self.org, kind="income", name="Donations Box"
            ).exists()
        )
