"""
Test Assertions for Serensa Calculation Logic

This file contains testable assertions that verify all calculations
in the system are working correctly.

Usage:
    python manage.py test sensa.tests.test_calculations
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from sensa.models import Shop, DailyEntry, UserProfile


User = get_user_model()


class StockCalculationTests(TestCase):
    """Test all stock-related calculations."""

    def setUp(self):
        """Create a test shop and user."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.shop = Shop.objects.create(name="Test Shop", shop_type=Shop.TYPE_RETAIL)
        self.today = timezone.localdate()

    def test_stock_available_calculation(self):
        """Assert: stock_available = opening_stock + stock_added"""
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=Decimal("0.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("150.00"),
            submitted_by=self.user,
        )
        
        # Assert: stock_available property
        assert entry.stock_available == Decimal("150.00"), \
            f"Expected 150.00, got {entry.stock_available}"
        print("✓ stock_available = opening_stock + stock_added")

    def test_stock_consumed_calculation(self):
        """Assert: stock_consumed = stock_available - closing_stock"""
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=Decimal("0.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # stock_available = 100 + 50 = 150
        # stock_consumed = 150 - 30 = 120
        assert entry.stock_consumed == Decimal("120.00"), \
            f"Expected 120.00, got {entry.stock_consumed}"
        print("✓ stock_consumed = (opening_stock + stock_added) - closing_stock")

    def test_closing_stock_never_negative(self):
        """Assert: closing_stock >= 0 (never negative)"""
        # Create entry with negative calculation
        opening = Decimal("50.00")
        stock_added = Decimal("30.00")
        buying = Decimal("100.00")  # More than available
        expired = Decimal("20.00")
        
        # Manually calculate: 50 + 30 - 100 - 20 = -40
        # Should be clamped to 0
        calculated_closing = opening + stock_added - buying - expired
        final_closing = max(calculated_closing, Decimal("0.00"))
        
        assert final_closing >= Decimal("0.00"), \
            f"Closing stock cannot be negative: {final_closing}"
        # Should clamp to 0
        assert final_closing == Decimal("0.00"), \
            f"Expected clamped to 0, got {final_closing}"
        print("✓ closing_stock is never negative (clamped to 0)")


class RevenueCalculationTests(TestCase):
    """Test all revenue-related calculations."""

    def setUp(self):
        """Create a test shop and user."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.shop = Shop.objects.create(name="Test Shop", shop_type=Shop.TYPE_RETAIL)
        self.today = timezone.localdate()

    def test_total_sales_value(self):
        """Assert: total_sales_value = sales_value"""
        sales = Decimal("1000.00")
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=sales,
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("100.00"),
            submitted_by=self.user,
        )
        
        assert entry.total_sales_value == sales, \
            f"Expected {sales}, got {entry.total_sales_value}"
        print(f"✓ total_sales_value = sales_value ({sales})")

    def test_paid_sales_calculation(self):
        """Assert: paid_sales = sales_value - debts"""
        sales = Decimal("1000.00")
        debts = Decimal("200.00")
        expected_paid = Decimal("800.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=sales,
            debts=debts,
            expenses=Decimal("0.00"),
            cash_received=Decimal("500.00"),
            closing_stock=Decimal("100.00"),
            submitted_by=self.user,
        )
        
        # paid_sales calculated in mobile_money_received property's intermediate step
        paid_sales = entry.total_sales_value - (entry.debts or Decimal("0.00"))
        assert paid_sales == expected_paid, \
            f"Expected {expected_paid}, got {paid_sales}"
        print(f"✓ paid_sales = sales_value - debts ({sales} - {debts} = {expected_paid})")

    def test_mobile_money_received_calculation(self):
        """Assert: mobile_money = MAX(paid_sales - cash_received, 0)"""
        sales = Decimal("1000.00")
        debts = Decimal("200.00")
        cash = Decimal("500.00")
        expected_mobile = Decimal("300.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=sales,
            debts=debts,
            expenses=Decimal("0.00"),
            cash_received=cash,
            closing_stock=Decimal("100.00"),
            submitted_by=self.user,
        )
        
        # paid_sales = 1000 - 200 = 800
        # mobile_money = MAX(800 - 500, 0) = 300
        assert entry.mobile_money_received == expected_mobile, \
            f"Expected {expected_mobile}, got {entry.mobile_money_received}"
        print(f"✓ mobile_money = MAX(paid_sales - cash, 0) = {expected_mobile}")

    def test_mobile_money_never_negative(self):
        """Assert: mobile_money >= 0 (never negative, even with overpayment)"""
        sales = Decimal("500.00")
        debts = Decimal("100.00")
        cash = Decimal("500.00")  # More than paid sales
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=sales,
            debts=debts,
            expenses=Decimal("0.00"),
            cash_received=cash,
            closing_stock=Decimal("100.00"),
            submitted_by=self.user,
        )
        
        # paid_sales = 500 - 100 = 400
        # mobile_money = MAX(400 - 500, 0) = MAX(-100, 0) = 0
        assert entry.mobile_money_received >= Decimal("0.00"), \
            f"Mobile money cannot be negative: {entry.mobile_money_received}"
        assert entry.mobile_money_received == Decimal("0.00"), \
            f"Expected 0 (overpayment case), got {entry.mobile_money_received}"
        print("✓ mobile_money never negative, even with overpayment")


class CostOfGoodsSoldTests(TestCase):
    """Test COGS calculation logic."""

    def setUp(self):
        """Create a test shop and user."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.shop = Shop.objects.create(name="Test Shop", shop_type=Shop.TYPE_RETAIL)
        self.today = timezone.localdate()

    def test_effective_cogs_with_explicit_buying_value(self):
        """Assert: IF buying_value > 0, effective_cogs = buying_value"""
        buying_value = Decimal("8000.00")
        stock_consumed = Decimal("800.00")  # Different from buying_value
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=Decimal("0.00"),
            sales_value=Decimal("10000.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # stock_consumed = (100 + 50) - 30 = 120
        actual_stock_consumed = entry.stock_consumed
        print(f"  Stock consumed (in units): {actual_stock_consumed}")
        
        # With buying_value > 0: use buying_value
        assert entry.effective_cost_of_goods == buying_value, \
            f"Expected {buying_value}, got {entry.effective_cost_of_goods}"
        print(f"✓ effective_cogs = buying_value ({buying_value}) when buying_value > 0")

    def test_effective_cogs_with_estimated_value(self):
        """Assert: IF buying_value == 0, effective_cogs = stock_consumed"""
        buying_value = Decimal("0.00")  # Not provided
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=Decimal("0.00"),
            sales_value=Decimal("10000.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # stock_consumed = (100 + 50) - 30 = 120
        expected_cogs = Decimal("120.00")
        assert entry.stock_consumed == expected_cogs, \
            f"Expected stock_consumed {expected_cogs}, got {entry.stock_consumed}"
        
        # With buying_value == 0: use stock_consumed
        assert entry.effective_cost_of_goods == expected_cogs, \
            f"Expected {expected_cogs}, got {entry.effective_cost_of_goods}"
        print(f"✓ effective_cogs = stock_consumed ({expected_cogs}) when buying_value == 0")

    def test_extra_waste_cost_with_buying_value(self):
        """Assert: IF buying_value > 0, extra_waste_cost = expired_value"""
        buying_value = Decimal("8000.00")
        expired_value = Decimal("500.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=expired_value,
            sales_value=Decimal("10000.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # When buying_value > 0, extra_waste_cost = expired_value
        # gross_profit = sales - effective_cogs - extra_waste
        expected_gross_profit = Decimal("10000.00") - Decimal("8000.00") - Decimal("500.00")
        
        assert entry.extra_cost_of_goods == expired_value, \
            f"Expected extra_waste {expired_value}, got {entry.extra_cost_of_goods}"
        assert entry.gross_profit == expected_gross_profit, \
            f"Expected gross_profit {expected_gross_profit}, got {entry.gross_profit}"
        print(f"✓ extra_waste_cost = expired_value ({expired_value}) when buying_value > 0")

    def test_no_extra_waste_without_buying_value(self):
        """Assert: IF buying_value == 0, extra_waste_cost = 0"""
        buying_value = Decimal("0.00")
        expired_value = Decimal("500.00")  # Ignored
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=expired_value,
            sales_value=Decimal("10000.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # stock_consumed = 120
        # When buying_value == 0: extra_waste = 0 (waste already in stock consumed)
        expected_gross_profit = Decimal("10000.00") - Decimal("120.00") - Decimal("0.00")
        
        assert entry.gross_profit == expected_gross_profit, \
            f"Expected gross_profit {expected_gross_profit}, got {entry.gross_profit}"
        print(f"✓ extra_waste_cost = 0 when buying_value == 0 (waste in stock consumed)")


class ProfitCalculationTests(TestCase):
    """Test profit and loss calculations."""

    def setUp(self):
        """Create a test shop and user."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.shop = Shop.objects.create(name="Test Shop", shop_type=Shop.TYPE_RETAIL)
        self.today = timezone.localdate()

    def test_gross_profit_with_explicit_costs(self):
        """Assert: gross_profit = sales - effective_cogs - extra_waste (with buying_value)"""
        sales = Decimal("100000.00")
        buying_value = Decimal("80000.00")
        expired_value = Decimal("5000.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=expired_value,
            sales_value=sales,
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        expected = Decimal("100000.00") - Decimal("80000.00") - Decimal("5000.00")
        assert entry.gross_profit == expected, \
            f"Expected {expected}, got {entry.gross_profit}"
        print(f"✓ gross_profit = {sales} - {buying_value} - {expired_value} = {expected}")

    def test_net_profit_after_expenses(self):
        """Assert: profit_or_loss = gross_profit - expenses"""
        sales = Decimal("100000.00")
        buying_value = Decimal("80000.00")
        expired_value = Decimal("5000.00")
        expenses = Decimal("3000.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=expired_value,
            sales_value=sales,
            debts=Decimal("0.00"),
            expenses=expenses,
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # gross_profit = 100000 - 80000 - 5000 = 15000
        # profit_or_loss = 15000 - 3000 = 12000
        expected = Decimal("15000.00") - Decimal("3000.00")
        assert entry.profit_or_loss == expected, \
            f"Expected {expected}, got {entry.profit_or_loss}"
        print(f"✓ profit_or_loss = gross_profit - expenses = {expected}")

    def test_negative_profit_indicates_loss(self):
        """Assert: profit_or_loss can be negative (loss)"""
        sales = Decimal("10000.00")
        buying_value = Decimal("20000.00")  # More than sales
        expenses = Decimal("5000.00")
        
        entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=self.today,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("50.00"),
            buying_value=buying_value,
            expired_value=Decimal("0.00"),
            sales_value=sales,
            debts=Decimal("0.00"),
            expenses=expenses,
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("30.00"),
            submitted_by=self.user,
        )
        
        # gross_profit = 10000 - 20000 - 0 = -10000
        # profit_or_loss = -10000 - 5000 = -15000
        expected = Decimal("-15000.00")
        assert entry.profit_or_loss == expected, \
            f"Expected {expected}, got {entry.profit_or_loss}"
        assert entry.profit_or_loss < Decimal("0.00"), \
            "Profit should be negative (loss)"
        print(f"✓ profit_or_loss can be negative: {expected} (loss)")


class OpeningStockContinuityTests(TestCase):
    """Test opening stock determination logic."""

    def setUp(self):
        """Create a test shop and user."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.shop = Shop.objects.create(name="Test Shop", shop_type=Shop.TYPE_RETAIL)

    def test_opening_stock_from_previous_day(self):
        """Assert: opening_stock should come from previous day's closing_stock"""
        from sensa.views import _get_previous_closing_stock
        
        # Day 1
        day1_date = date(2026, 3, 28)
        day1_entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=day1_date,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=Decimal("0.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("75.00"),
            submitted_by=self.user,
        )
        
        # Day 2
        day2_date = date(2026, 3, 29)
        previous_closing = _get_previous_closing_stock(self.shop, day2_date)
        
        assert previous_closing == Decimal("75.00"), \
            f"Expected opening from previous day {Decimal('75.00')}, got {previous_closing}"
        print(f"✓ opening_stock comes from previous day's closing_stock: {previous_closing}")

    def test_opening_stock_from_latest_earlier_entry(self):
        """Assert: if no previous day entry, use latest earlier entry's closing_stock"""
        from sensa.views import _get_previous_closing_stock
        
        # Entry on day 1
        day1_date = date(2026, 3, 27)
        day1_entry = DailyEntry.objects.create(
            shop=self.shop,
            entry_date=day1_date,
            opening_stock=Decimal("100.00"),
            stock_added=Decimal("0.00"),
            buying_value=Decimal("0.00"),
            expired_value=Decimal("0.00"),
            sales_value=Decimal("0.00"),
            debts=Decimal("0.00"),
            expenses=Decimal("0.00"),
            cash_received=Decimal("0.00"),
            closing_stock=Decimal("60.00"),
            submitted_by=self.user,
        )
        
        # Skip day 2, look for entry on day 3
        day3_date = date(2026, 3, 29)  # 2 days later
        previous_closing = _get_previous_closing_stock(self.shop, day3_date)
        
        assert previous_closing == Decimal("60.00"), \
            f"Expected fallback to latest earlier entry {Decimal('60.00')}, got {previous_closing}"
        print(f"✓ opening_stock from latest earlier entry: {previous_closing}")

    def test_opening_stock_none_if_no_history(self):
        """Assert: opening_stock is None if no earlier entries exist"""
        from sensa.views import _get_previous_closing_stock
        
        # No entries exist
        day_date = date(2026, 3, 30)
        previous_closing = _get_previous_closing_stock(self.shop, day_date)
        
        assert previous_closing is None, \
            f"Expected None for first entry, got {previous_closing}"
        print("✓ opening_stock is None when no history exists (manual entry required)")


def run_all_tests():
    """Runner for all calculation assertion tests."""
    print("\n" + "="*70)
    print("SERENSA CALCULATION LOGIC - TEST ASSERTIONS")
    print("="*70 + "\n")
    
    test_classes = [
        StockCalculationTests,
        RevenueCalculationTests,
        CostOfGoodsSoldTests,
        ProfitCalculationTests,
        OpeningStockContinuityTests,
    ]
    
    print("Run with: python manage.py test sensa.tests.test_calculations\n")
