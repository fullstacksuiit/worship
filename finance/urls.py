from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("finance/", views.overview, name="overview"),
    path("finance/expenses/new/", views.expense_create, name="expense_create"),
    path("finance/income/new/", views.income_create, name="income_create"),
    path("finance/ledger/", views.transactions, name="transactions"),
    path("finance/ledger/export.csv", views.transactions_export, name="transactions_export"),
    path("finance/categories/", views.categories, name="categories"),
    path("finance/budgets/", views.budgets, name="budgets"),
    path("finance/pledges/", views.pledges, name="pledges"),
]
