from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Shop(models.Model):
    name = models.CharField(max_length=120, unique=True)
    location = models.CharField(max_length=180, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ADMIN = "admin"
    VENDOR = "vendor"
    ROLE_CHOICES = [(ADMIN, "Admin"), (VENDOR, "Vendor")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=VENDOR)
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    assigned_shops = models.ManyToManyField(Shop, blank=True, related_name="vendors")

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.ADMIN or self.user.is_superuser


class DailyEntry(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="entries")
    entry_date = models.DateField(default=timezone.localdate)
    opening_stock = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    stock_added = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    expenses = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    debts = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Value sold on credit.",
    )
    closing_stock = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    cash_received = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Cash received from buyers.",
    )
    notes = models.TextField(blank=True)
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["shop", "entry_date"], name="unique_shop_entry_date")
        ]

    def __str__(self):
        return f"{self.shop.name} - {self.entry_date}"

    @property
    def stock_available(self):
        return (self.opening_stock or Decimal("0.00")) + (self.stock_added or Decimal("0.00"))

    @property
    def stock_consumed(self):
        return self.stock_available - (self.closing_stock or Decimal("0.00"))

    @property
    def total_sales_value(self):
        return (self.cash_received or Decimal("0.00")) + (self.debts or Decimal("0.00"))

    @property
    def profit_or_loss(self):
        # Value-based P/L: sales minus stock consumed and expenses.
        return self.total_sales_value - self.stock_consumed - (self.expenses or Decimal("0.00"))


class BankBalanceSnapshot(models.Model):
    fetched_at = models.DateTimeField(auto_now_add=True)
    provider = models.CharField(max_length=50, default="Jenga")
    account_reference = models.CharField(max_length=100, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2)
    raw_response = models.TextField(blank=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.provider} @ {self.fetched_at:%Y-%m-%d %H:%M}"
