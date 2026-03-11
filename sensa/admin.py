from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import BankBalanceSnapshot, DailyEntry, Shop, UserProfile

User = get_user_model()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    pass


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "active", "created_at")
    search_fields = ("name", "location")
    list_filter = ("active",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_number")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "phone_number")


@admin.register(DailyEntry)
class DailyEntryAdmin(admin.ModelAdmin):
    list_display = (
        "shop",
        "entry_date",
        "opening_stock",
        "stock_added",
        "expenses",
        "debts",
        "closing_stock",
        "cash_received",
        "submitted_by",
    )
    list_filter = ("entry_date", "shop")
    search_fields = ("shop__name", "submitted_by__username")


@admin.register(BankBalanceSnapshot)
class BankBalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("provider", "account_reference", "balance", "fetched_at")
    list_filter = ("provider",)
