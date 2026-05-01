from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from sensa.forms import DailyEntryForm
from sensa.models import Shop, UserProfile


User = get_user_model()


class RoomShopDailyEntryFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="room-admin", password="pass")
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.role = UserProfile.ADMIN
        profile.save(update_fields=["role"])
        self.user = User.objects.get(pk=self.user.pk)
        self.shop = Shop.objects.create(name="Room Shop", shop_type=Shop.TYPE_ROOMS)

    def test_rooms_shop_defaults_stock_fields_to_zero(self):
        form = DailyEntryForm(
            data={
                "shop": self.shop.pk,
                "entry_date": "2026-05-01",
                "opening_stock": "10.00",
                "stock_added": "",
                "buying_value": "",
                "expired_value": "0.00",
                "expenses": "0.00",
                "sales_value": "100.00",
                "debts": "0.00",
                "closing_stock": "0.00",
            },
            user=self.user,
            require_opening_stock=False,
            calculated_opening_stock=Decimal("10.00"),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["stock_added"], Decimal("0.00"))
        self.assertEqual(form.cleaned_data["buying_value"], Decimal("0.00"))
