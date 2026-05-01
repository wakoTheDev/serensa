from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    pass


class Shop(models.Model):
    TYPE_RESTAURANT = "restaurant"
    TYPE_RETAIL = "retail"
    TYPE_BAR = "bar"
    TYPE_ROOMS = "rooms"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_RESTAURANT, "Restaurant"),
        (TYPE_RETAIL, "Retail"),
        (TYPE_BAR, "Bar"),
        (TYPE_ROOMS, "Rooms"),
        (TYPE_OTHER, "Other"),
    ]

    name = models.CharField(max_length=120)
    shop_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_RETAIL)
    parent_shop = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subshops",
    )
    location = models.CharField(max_length=180, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(parent_shop__isnull=True),
                name="unique_parent_shop_name",
            ),
            models.UniqueConstraint(
                fields=["parent_shop", "name"],
                condition=Q(parent_shop__isnull=False),
                name="unique_subshop_name_per_parent",
            ),
        ]

    def __str__(self):
        if self.parent_shop_id:
            return f"{self.parent_shop.name} / {self.name}"
        return self.name

    @property
    def is_subshop(self):
        return bool(self.parent_shop_id)


class UserProfile(models.Model):
    ADMIN = "admin"
    VENDOR = "vendor"
    ROLE_CHOICES = [(ADMIN, "Admin"), (VENDOR, "Vendor")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=VENDOR)
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    assigned_shops = models.ManyToManyField(Shop, blank=True, related_name="vendors")

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.ADMIN or self.user.is_superuser

    def accessible_shops(self):
        assigned_ids = list(self.assigned_shops.values_list("id", flat=True))
        if not assigned_ids:
            return Shop.objects.none()

        # Mongo-friendly single queryset:
        # 1) include active children of assigned parents
        # 2) include directly assigned active shops that do not have active children
        return (
            Shop.objects.filter(active=True)
            .filter(Q(parent_shop_id__in=assigned_ids) | Q(id__in=assigned_ids))
            .exclude(id__in=Shop.objects.filter(id__in=assigned_ids, subshops__active=True))
            .distinct()
        )


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
    buying_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=Decimal("0.00"),
        help_text="Cost price value of goods sold for the day.",
    )
    expired_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=Decimal("0.00"),
        help_text="Cost value of expired or wasted goods for the day.",
    )
    expenses = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    sales_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total value sold for the day.",
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
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
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
        return self.sales_value or Decimal("0.00")

    @property
    def effective_cost_of_goods(self):
        buying_value = self.buying_value or Decimal("0.00")
        if buying_value > Decimal("0.00"):
            return buying_value
        return self.stock_consumed

    @property
    def gross_profit(self):
        expired_value = self.expired_value or Decimal("0.00")
        extra_waste_cost = expired_value if (self.buying_value or Decimal("0.00")) > Decimal("0.00") else Decimal("0.00")
        return self.total_sales_value - self.effective_cost_of_goods - extra_waste_cost

    @property
    def mobile_money_received(self):
        paid_sales = self.total_sales_value - (self.debts or Decimal("0.00"))
        mobile_money = paid_sales - (self.cash_received or Decimal("0.00"))
        return mobile_money if mobile_money > Decimal("0.00") else Decimal("0.00")

    @property
    def profit_or_loss(self):
        # Net margin after cost of goods, expired stock (when tracked), and operating expenses.
        return self.gross_profit - (self.expenses or Decimal("0.00"))


class JengaApiSettings(models.Model):
    provider_name = models.CharField(max_length=50, default="Jenga")
    account_reference = models.CharField(max_length=100, unique=True)
    balance_field_path = models.CharField(max_length=255, default="balance")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return f"{self.provider_name} - {self.account_reference}"

    @property
    def is_configured(self):
        return bool(self.account_reference)


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




@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)