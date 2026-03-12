from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .forms import (
    AdminBootstrapForm,
    DailyEntryForm,
    JengaApiSettingsForm,
    PhoneLoginForm,
    ReportFilterForm,
    ShopForm,
    UserManagementForm,
    UserRoleUpdateForm,
)
from .models import BankBalanceSnapshot, DailyEntry, JengaApiSettings, Shop, UserProfile
from .services import fetch_jenga_equity_balance

User = get_user_model()


class UserLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = PhoneLoginForm

    def form_invalid(self, form):
        messages.error(self.request, "Invalid phone/username or password.")
        return super().form_invalid(form)

    def get_success_url(self):
        return self.get_redirect_url() or "/"


def _resolve_profile(user):
    if not user.is_authenticated:
        return None

    default_role = UserProfile.ADMIN if (user.is_superuser or user.is_staff) else UserProfile.VENDOR
    profile, created = UserProfile.objects.get_or_create(user=user, defaults={"role": default_role})

    # Keep privileged Django accounts aligned with admin role.
    if (user.is_superuser or user.is_staff) and profile.role != UserProfile.ADMIN:
        profile.role = UserProfile.ADMIN
        profile.save(update_fields=["role"])

    # Existing profiles without role should still behave safely.
    if created and not profile.role:
        profile.role = default_role
        profile.save(update_fields=["role"])

    return profile


def _is_admin(user):
    profile = _resolve_profile(user)
    return bool(profile and profile.is_admin)


def _is_vendor(user):
    profile = _resolve_profile(user)
    return bool(profile and not profile.is_admin)


def bootstrap_admin(request):
    if UserProfile.objects.filter(role=UserProfile.ADMIN, user__is_active=True).exists():
        messages.info(request, "Admin account already exists. Please login.")
        return redirect("login")

    if request.method == "POST":
        form = AdminBootstrapForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Admin account created. Login using username or phone number and password.",
            )
            return redirect("login")
    else:
        form = AdminBootstrapForm()

    return render(request, "sensa/setup_admin.html", {"form": form})


@login_required
def dashboard_redirect(request):
    if _is_admin(request.user):
        return redirect("admin_dashboard")
    return redirect("vendor_dashboard")


@login_required
@user_passes_test(_is_admin)
def admin_dashboard(request):
    shops = Shop.objects.filter(active=True)
    today = timezone.localdate()
    todays_entries = DailyEntry.objects.filter(entry_date=today)
    latest_balance = BankBalanceSnapshot.objects.first()

    context = {
        "shops_count": shops.count(),
        "entries_today": todays_entries.count(),
        "latest_balance": latest_balance,
        "recent_entries": DailyEntry.objects.select_related("shop", "submitted_by")[:10],
    }
    return render(request, "sensa/admin_dashboard.html", context)


@login_required
@user_passes_test(_is_vendor)
def vendor_dashboard(request):
    today = timezone.localdate()
    shops = request.user.profile.assigned_shops.filter(active=True)
    entries = DailyEntry.objects.filter(shop__in=shops).select_related("shop")
    todays = entries.filter(entry_date=today)

    context = {
        "assigned_shops": shops,
        "todays_entries": todays,
        "latest_entry": entries.first(),
    }
    return render(request, "sensa/vendor_dashboard.html", context)


@login_required
def entry_create_or_update(request):
    today = timezone.localdate()
    user = request.user
    selected_shop_id = request.GET.get("shop")

    if not (_is_admin(user) or _is_vendor(user)):
        return HttpResponseForbidden("Not authorized.")

    edit_entry = None
    opening_stock_value = Decimal("0.00")

    if request.method == "POST":
        shop_id = request.POST.get("shop")
        entry_date = request.POST.get("entry_date")
        if shop_id and entry_date:
            edit_entry = DailyEntry.objects.filter(shop_id=shop_id, entry_date=entry_date).first()

        form = DailyEntryForm(request.POST, user=user, instance=edit_entry)
        if form.is_valid():
            shop = form.cleaned_data["shop"]
            if _is_vendor(user) and not user.profile.assigned_shops.filter(pk=shop.pk).exists():
                return HttpResponseForbidden("You can only submit data to your assigned shops.")

            entry = form.save(commit=False)
            is_update = bool(entry.pk)
            entry.opening_stock = _derive_opening_stock(shop, entry.entry_date, current_entry=edit_entry)
            opening_stock_value = entry.opening_stock

            if entry.entry_date == today or _is_admin(user):
                entry.submitted_by = user
                entry.save()
                messages.success(
                    request,
                    "Entry updated successfully." if is_update else "Entry created successfully.",
                )
                return redirect(f"{request.path}?shop={entry.shop_id}")

            messages.error(request, "Vendors can only update entries for the same day.")
            return redirect(f"{request.path}?shop={shop.pk}")

        messages.error(request, "Entry was not saved. Please correct the form errors and try again.")
        bound_shop = form.data.get("shop")
        bound_date = form.data.get("entry_date")
        if bound_shop and bound_date:
            shop = Shop.objects.filter(pk=bound_shop).first()
            try:
                parsed_date = datetime.strptime(bound_date, "%Y-%m-%d").date()
            except ValueError:
                parsed_date = today
            opening_stock_value = _derive_opening_stock(shop, parsed_date, current_entry=edit_entry)
    else:
        initial = {"entry_date": today}

        if _is_vendor(user):
            assigned_shops = user.profile.assigned_shops.filter(active=True).order_by("name")
            if selected_shop_id:
                selected_shop = assigned_shops.filter(pk=selected_shop_id).first()
            else:
                selected_shop = assigned_shops.first()
            if selected_shop:
                initial["shop"] = selected_shop
                edit_entry = DailyEntry.objects.filter(shop=selected_shop, entry_date=today).first()

        elif _is_admin(user) and selected_shop_id:
            selected_shop = Shop.objects.filter(pk=selected_shop_id).first()
            if selected_shop:
                initial["shop"] = selected_shop
                edit_entry = DailyEntry.objects.filter(shop=selected_shop, entry_date=today).first()

        if edit_entry:
            form = DailyEntryForm(user=user, instance=edit_entry)
            opening_stock_value = _derive_opening_stock(edit_entry.shop, edit_entry.entry_date, current_entry=edit_entry)
        else:
            form = DailyEntryForm(user=user, initial=initial)
            preview_shop = initial.get("shop")
            preview_date = initial.get("entry_date", today)
            opening_stock_value = _derive_opening_stock(preview_shop, preview_date)

    context = {
        "form": form,
        "is_edit_mode": bool(edit_entry),
        "opening_stock_value": opening_stock_value,
        "form_title": "Update Shop Values" if edit_entry else "Feed Shop Values",
        "form_subtitle": (
            "Editing today's saved entry. Update the fields and submit changes."
            if edit_entry
            else "Create today's entry for the selected shop."
        ),
        "submit_label": "Update Entry" if edit_entry else "Save Entry",
    }
    return render(request, "sensa/entry_form.html", context)


@login_required
@user_passes_test(_is_admin)
def shop_list(request):
    shops = Shop.objects.all().order_by("name")
    return render(request, "sensa/shop_list.html", {"shops": shops})


@login_required
@user_passes_test(_is_admin)
def shop_create(request):
    if request.method == "POST":
        form = ShopForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Shop created.")
            return redirect("shop_list")
    else:
        form = ShopForm()

    return render(request, "sensa/shop_form.html", {"form": form, "title": "Create Shop"})


@login_required
@user_passes_test(_is_admin)
def shop_edit(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    if request.method == "POST":
        form = ShopForm(request.POST, instance=shop)
        if form.is_valid():
            form.save()
            messages.success(request, "Shop updated.")
            return redirect("shop_list")
    else:
        form = ShopForm(instance=shop)

    return render(request, "sensa/shop_form.html", {"form": form, "title": "Edit Shop"})


@login_required
@user_passes_test(_is_admin)
def shop_delete(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    if request.method == "POST":
        shop.delete()
        messages.success(request, "Shop deleted.")
        return redirect("shop_list")
    return render(request, "sensa/confirm_delete.html", {"item": shop, "kind": "shop"})


def _date_range(period, selected_date):
    date_val = selected_date or timezone.localdate()
    if period == "weekly":
        start = date_val - timedelta(days=date_val.weekday())
        end = start + timedelta(days=6)
    elif period == "monthly":
        start = date_val.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - timedelta(days=1)
    else:
        start = end = date_val
    return start, end


def _derive_opening_stock(shop, entry_date, current_entry=None):
    if not shop or not entry_date:
        return Decimal("0.00")

    entries = DailyEntry.objects.filter(shop=shop)
    if current_entry and current_entry.pk:
        entries = entries.exclude(pk=current_entry.pk)

    previous_day_entry = entries.filter(entry_date=entry_date - timedelta(days=1)).first()
    if previous_day_entry:
        return previous_day_entry.closing_stock or Decimal("0.00")

    latest_previous_entry = entries.filter(entry_date__lt=entry_date).order_by("-entry_date", "-updated_at").first()
    if latest_previous_entry:
        return latest_previous_entry.closing_stock or Decimal("0.00")

    return Decimal("0.00")


def _calculate_stock_metrics(entries):
    per_shop = OrderedDict()

    for entry in entries:
        state = per_shop.setdefault(
            entry.shop_id,
            {
                "opening": entry.opening_stock or Decimal("0.00"),
                "first_date": entry.entry_date,
                "closing": entry.closing_stock or Decimal("0.00"),
                "last_date": entry.entry_date,
                "added": Decimal("0.00"),
            },
        )
        if entry.entry_date < state["first_date"]:
            state["first_date"] = entry.entry_date
            state["opening"] = entry.opening_stock or Decimal("0.00")
        if entry.entry_date > state["last_date"]:
            state["last_date"] = entry.entry_date
            state["closing"] = entry.closing_stock or Decimal("0.00")
        state["added"] += entry.stock_added or Decimal("0.00")

    opening_total = sum((state["opening"] for state in per_shop.values()), Decimal("0.00"))
    added_total = sum((state["added"] for state in per_shop.values()), Decimal("0.00"))
    closing_total = sum((state["closing"] for state in per_shop.values()), Decimal("0.00"))

    return {
        "opening_stock": opening_total,
        "stock_added": added_total,
        "closing_stock": closing_total,
        "stock_consumed": opening_total + added_total - closing_total,
    }


def _build_balance_metrics(start, end):
    current_tz = timezone.get_current_timezone()
    start_marker = timezone.make_aware(datetime.combine(start, time.min), current_tz)
    end_marker = timezone.make_aware(datetime.combine(end, time.max), current_tz)

    opening_snapshot = (
        BankBalanceSnapshot.objects.filter(fetched_at__lt=start_marker)
        .order_by("-fetched_at")
        .first()
    )
    closing_snapshot = (
        BankBalanceSnapshot.objects.filter(fetched_at__lte=end_marker)
        .order_by("-fetched_at")
        .first()
    )

    opening_balance = opening_snapshot.balance if opening_snapshot else Decimal("0.00")
    closing_balance = closing_snapshot.balance if closing_snapshot else Decimal("0.00")
    has_delta = bool(closing_snapshot and closing_snapshot.fetched_at >= start_marker and opening_snapshot)

    return {
        "opening_snapshot": opening_snapshot,
        "closing_snapshot": closing_snapshot,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "bank_received": closing_balance - opening_balance if has_delta else Decimal("0.00"),
        "has_delta": has_delta,
        "latest_balance": BankBalanceSnapshot.objects.order_by("-fetched_at").first(),
    }


def _build_report_dataset(query_data):
    form = ReportFilterForm(query_data or None)
    entries_qs = DailyEntry.objects.select_related("shop", "submitted_by")

    today = timezone.localdate()
    if form.is_bound and form.is_valid():
        period = form.cleaned_data.get("period") or "daily"
        selected_date = form.cleaned_data.get("date") or today
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")

        if start_date or end_date:
            start = start_date or end_date
            end = end_date or start_date
            filter_mode = "date_range"
        else:
            start, end = _date_range(period, selected_date)
            filter_mode = "period"
        selected_shop = form.cleaned_data.get("shop")
    else:
        period = "historical"
        selected_date = today
        start = entries_qs.order_by("entry_date").values_list("entry_date", flat=True).first() or today
        end = today
        selected_shop = None
        filter_mode = "historical"

    entries_qs = entries_qs.filter(entry_date__range=(start, end)).order_by("entry_date", "shop__name")
    if selected_shop:
        entries_qs = entries_qs.filter(shop=selected_shop)

    entries = list(entries_qs)

    shops_in_scope = Shop.objects.filter(active=True)
    if selected_shop:
        chart_shop = selected_shop
    else:
        chart_shop = (
            shops_in_scope.filter(entries__entry_date__range=(start, end))
            .distinct()
            .order_by("name")
            .first()
        )

    shop_entries = [entry for entry in entries if chart_shop and entry.shop_id == chart_shop.id]

    stock_metrics = _calculate_stock_metrics(entries)
    total_sales = sum((entry.sales_value or Decimal("0.00") for entry in entries), Decimal("0.00"))
    total_expenses = sum((entry.expenses or Decimal("0.00") for entry in entries), Decimal("0.00"))
    total_debts = sum((entry.debts or Decimal("0.00") for entry in entries), Decimal("0.00"))
    total_cash = sum((entry.cash_received or Decimal("0.00") for entry in entries), Decimal("0.00"))
    total_mobile_money = sum((entry.mobile_money_received for entry in entries), Decimal("0.00"))
    paid_sales_total = total_sales - total_debts
    stock_consumed = stock_metrics["stock_consumed"]
    profit_or_loss = total_sales - stock_consumed - total_expenses
    net_profit = profit_or_loss if profit_or_loss > Decimal("0.00") else Decimal("0.00")
    net_loss = abs(profit_or_loss) if profit_or_loss < Decimal("0.00") else Decimal("0.00")
    balance_metrics = _build_balance_metrics(start, end)

    totals = {
        "opening_stock": stock_metrics["opening_stock"],
        "stock_added": stock_metrics["stock_added"],
        "expenses": total_expenses,
        "sales_value": total_sales,
        "debts": total_debts,
        "closing_stock": stock_metrics["closing_stock"],
        "cash_received": total_cash,
        "mobile_money": total_mobile_money,
        "paid_sales": paid_sales_total,
    }

    shop_daily_points = OrderedDict()
    cursor = start
    while cursor <= end:
        shop_daily_points[cursor.isoformat()] = {
            "sales": Decimal("0.00"),
            "expenses": Decimal("0.00"),
            "debts": Decimal("0.00"),
            "mobile": Decimal("0.00"),
            "profit": Decimal("0.00"),
        }
        cursor += timedelta(days=1)

    for entry in shop_entries:
        key = entry.entry_date.isoformat()
        shop_daily_points[key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_daily_points[key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_daily_points[key]["debts"] += entry.debts or Decimal("0.00")
        shop_daily_points[key]["mobile"] += entry.mobile_money_received
        shop_daily_points[key]["profit"] += entry.profit_or_loss or Decimal("0.00")

    progressive_shop_sales = []
    progressive_shop_expenses = []
    progressive_shop_profit = []
    running_sales = Decimal("0.00")
    running_expenses = Decimal("0.00")
    running_profit = Decimal("0.00")

    for point in shop_daily_points.values():
        running_sales += point["sales"]
        running_expenses += point["expenses"]
        running_profit += point["profit"]
        progressive_shop_sales.append(float(running_sales))
        progressive_shop_expenses.append(float(running_expenses))
        progressive_shop_profit.append(float(running_profit))

    shop_stock_metrics = _calculate_stock_metrics(shop_entries)
    shop_sales_total = sum((entry.sales_value or Decimal("0.00") for entry in shop_entries), Decimal("0.00"))
    shop_expenses_total = sum((entry.expenses or Decimal("0.00") for entry in shop_entries), Decimal("0.00"))
    shop_debts_total = sum((entry.debts or Decimal("0.00") for entry in shop_entries), Decimal("0.00"))
    shop_cash_total = sum((entry.cash_received or Decimal("0.00") for entry in shop_entries), Decimal("0.00"))
    shop_mobile_total = sum((entry.mobile_money_received for entry in shop_entries), Decimal("0.00"))
    shop_profit_total = shop_sales_total - shop_stock_metrics["stock_consumed"] - shop_expenses_total
    shop_net_profit = shop_profit_total if shop_profit_total > Decimal("0.00") else Decimal("0.00")
    shop_net_loss = abs(shop_profit_total) if shop_profit_total < Decimal("0.00") else Decimal("0.00")

    bar_date = selected_date if filter_mode == "period" else end
    if filter_mode == "historical":
        bar_date = today

    shop_day_entries = [entry for entry in shop_entries if entry.entry_date == bar_date]
    day_sales = sum((entry.sales_value or Decimal("0.00") for entry in shop_day_entries), Decimal("0.00"))
    day_expenses = sum((entry.expenses or Decimal("0.00") for entry in shop_day_entries), Decimal("0.00"))
    day_debts = sum((entry.debts or Decimal("0.00") for entry in shop_day_entries), Decimal("0.00"))
    day_cash = sum((entry.cash_received or Decimal("0.00") for entry in shop_day_entries), Decimal("0.00"))
    day_mobile = sum((entry.mobile_money_received for entry in shop_day_entries), Decimal("0.00"))
    day_profit = sum((entry.profit_or_loss or Decimal("0.00") for entry in shop_day_entries), Decimal("0.00"))

    all_daily_points = OrderedDict()
    cursor = start
    while cursor <= end:
        all_daily_points[cursor.isoformat()] = {
            "sales": Decimal("0.00"),
            "expenses": Decimal("0.00"),
            "debts": Decimal("0.00"),
            "profit": Decimal("0.00"),
        }
        cursor += timedelta(days=1)

    for entry in entries:
        key = entry.entry_date.isoformat()
        all_daily_points[key]["sales"] += entry.sales_value or Decimal("0.00")
        all_daily_points[key]["expenses"] += entry.expenses or Decimal("0.00")
        all_daily_points[key]["debts"] += entry.debts or Decimal("0.00")
        all_daily_points[key]["profit"] += entry.profit_or_loss or Decimal("0.00")

    cumulative_sales = []
    cumulative_expenses = []
    cumulative_debts = []
    cumulative_profit = []
    running_sales_all = Decimal("0.00")
    running_expenses_all = Decimal("0.00")
    running_debts_all = Decimal("0.00")
    running_profit_all = Decimal("0.00")

    for point in all_daily_points.values():
        running_sales_all += point["sales"]
        running_expenses_all += point["expenses"]
        running_debts_all += point["debts"]
        running_profit_all += point["profit"]
        cumulative_sales.append(float(running_sales_all))
        cumulative_expenses.append(float(running_expenses_all))
        cumulative_debts.append(float(running_debts_all))
        cumulative_profit.append(float(running_profit_all))

    shop_compare = OrderedDict()
    shop_daily_data = OrderedDict()

    for entry in entries:
        shop_key = entry.shop.name
        if shop_key not in shop_compare:
            shop_compare[shop_key] = {
                "sales": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "debts": Decimal("0.00"),
                "mobile": Decimal("0.00"),
                "profit": Decimal("0.00"),
            }
            shop_daily_data[shop_key] = OrderedDict()
            cursor = start
            while cursor <= end:
                shop_daily_data[shop_key][cursor.isoformat()] = {
                    "sales": Decimal("0.00"),
                    "expenses": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                }
                cursor += timedelta(days=1)

        shop_compare[shop_key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_compare[shop_key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_compare[shop_key]["debts"] += entry.debts or Decimal("0.00")
        shop_compare[shop_key]["mobile"] += entry.mobile_money_received
        shop_compare[shop_key]["profit"] += entry.profit_or_loss or Decimal("0.00")

        entry_key = entry.entry_date.isoformat()
        shop_daily_data[shop_key][entry_key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_daily_data[shop_key][entry_key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_daily_data[shop_key][entry_key]["profit"] += entry.profit_or_loss or Decimal("0.00")

    chart_payload = {
        "shopName": chart_shop.name if chart_shop else "No Shop",
        "shopBarDate": str(bar_date),
        "shopBarLabels": ["Sales", "Expenses", "Credit", "Cash", "Mobile", "Profit/Loss"],
        "shopBarValues": [
            float(day_sales),
            float(day_expenses),
            float(day_debts),
            float(day_cash),
            float(day_mobile),
            float(day_profit),
        ],
        "trendLabels": list(shop_daily_points.keys()),
        "trendSales": progressive_shop_sales,
        "trendExpenses": progressive_shop_expenses,
        "trendProfit": progressive_shop_profit,
        "shopPieLabels": ["Sales", "Expenses", "Credit", "Cash", "Mobile", "Net Profit", "Net Loss"],
        "shopPieValues": [
            float(shop_sales_total),
            float(shop_expenses_total),
            float(shop_debts_total),
            float(shop_cash_total),
            float(shop_mobile_total),
            float(shop_net_profit),
            float(shop_net_loss),
        ],
        "allCumulativeLabels": list(all_daily_points.keys()),
        "allCumulativeSales": cumulative_sales,
        "allCumulativeExpenses": cumulative_expenses,
        "allCumulativeDebts": cumulative_debts,
        "allCumulativeProfit": cumulative_profit,
        "shopCompareLabels": list(shop_compare.keys()),
        "shopCompareSales": [float(v["sales"]) for v in shop_compare.values()],
        "shopCompareExpenses": [float(v["expenses"]) for v in shop_compare.values()],
        "shopCompareDebts": [float(v["debts"]) for v in shop_compare.values()],
        "shopCompareMobile": [float(v["mobile"]) for v in shop_compare.values()],
        "shopCompareProfit": [float(v["profit"]) for v in shop_compare.values()],
        "generalPieLabels": ["Sales", "Expenses", "Credit", "Cash", "Mobile", "Net Profit", "Net Loss"],
        "generalPieValues": [
            float(total_sales),
            float(total_expenses),
            float(total_debts),
            float(total_cash),
            float(total_mobile_money),
            float(net_profit),
            float(net_loss),
        ],
    }

    chart_cards = []

    if any(value != 0.0 for value in chart_payload["shopBarValues"]):
        chart_cards.append(
            {
                "category": "Shop",
                "title": f"{chart_payload['shopName']} Day Snapshot ({chart_payload['shopBarDate']})",
                "chartType": "bar",
                "labels": chart_payload["shopBarLabels"],
                "datasets": [
                    {
                        "label": f"{chart_payload['shopName']} ({chart_payload['shopBarDate']})",
                        "data": chart_payload["shopBarValues"],
                        "backgroundColor": [
                            "rgba(15, 118, 110, 0.75)",
                            "rgba(180, 83, 9, 0.75)",
                            "rgba(190, 24, 93, 0.75)",
                            "rgba(30, 64, 175, 0.75)",
                            "rgba(124, 58, 237, 0.75)",
                            "rgba(22, 101, 52, 0.75)",
                        ],
                        "borderRadius": 8,
                    }
                ],
            }
        )

    if chart_payload["trendLabels"]:
        chart_cards.append(
            {
                "category": "Shop",
                "title": f"{chart_payload['shopName']} Historical Trend",
                "chartType": "line",
                "labels": chart_payload["trendLabels"],
                "datasets": [
                    {
                        "label": "Sales",
                        "data": chart_payload["trendSales"],
                        "borderColor": "#0f766e",
                        "backgroundColor": "rgba(15, 118, 110, 0.08)",
                        "tension": 0.45,
                        "fill": True,
                    },
                    {
                        "label": "Expenses",
                        "data": chart_payload["trendExpenses"],
                        "borderColor": "#b45309",
                        "backgroundColor": "rgba(180, 83, 9, 0.08)",
                        "tension": 0.45,
                        "fill": True,
                    },
                    {
                        "label": "Profit/Loss",
                        "data": chart_payload["trendProfit"],
                        "borderColor": "#1d4ed8",
                        "backgroundColor": "rgba(29, 78, 216, 0.08)",
                        "tension": 0.45,
                        "fill": True,
                    },
                ],
            }
        )

    if any(value != 0.0 for value in chart_payload["shopPieValues"]):
        chart_cards.append(
            {
                "category": "Shop",
                "title": f"{chart_payload['shopName']} Cumulative Distribution",
                "chartType": "pie",
                "labels": chart_payload["shopPieLabels"],
                "datasets": [
                    {
                        "label": chart_payload["shopName"],
                        "data": chart_payload["shopPieValues"],
                        "backgroundColor": [
                            "rgba(15, 118, 110, 0.8)",
                            "rgba(180, 83, 9, 0.8)",
                            "rgba(190, 24, 93, 0.8)",
                            "rgba(29, 78, 216, 0.8)",
                            "rgba(124, 58, 237, 0.8)",
                            "rgba(22, 163, 74, 0.8)",
                            "rgba(127, 29, 29, 0.8)",
                        ],
                    }
                ],
            }
        )

    if chart_payload["allCumulativeLabels"]:
        chart_cards.append(
            {
                "category": "General",
                "title": "All Shops Cumulative Trend",
                "chartType": "line",
                "labels": chart_payload["allCumulativeLabels"],
                "datasets": [
                    {
                        "label": "Cumulative Sales",
                        "data": chart_payload["allCumulativeSales"],
                        "borderColor": "#0f766e",
                        "backgroundColor": "rgba(15, 118, 110, 0.08)",
                        "tension": 0.4,
                        "fill": True,
                    },
                    {
                        "label": "Cumulative Credit",
                        "data": chart_payload["allCumulativeDebts"],
                        "borderColor": "#be123c",
                        "backgroundColor": "rgba(190, 18, 60, 0.08)",
                        "tension": 0.4,
                        "fill": True,
                    },
                    {
                        "label": "Cumulative Profit/Loss",
                        "data": chart_payload["allCumulativeProfit"],
                        "borderColor": "#1d4ed8",
                        "backgroundColor": "rgba(29, 78, 216, 0.08)",
                        "tension": 0.4,
                        "fill": True,
                    },
                ],
            }
        )

    if chart_payload["shopCompareLabels"]:
        chart_cards.append(
            {
                "category": "General",
                "title": "Per-Shop Comparison",
                "chartType": "bar",
                "labels": chart_payload["shopCompareLabels"],
                "datasets": [
                    {
                        "label": "Sales",
                        "data": chart_payload["shopCompareSales"],
                        "backgroundColor": "rgba(15, 118, 110, 0.75)",
                    },
                    {
                        "label": "Credit Sales",
                        "data": chart_payload["shopCompareDebts"],
                        "backgroundColor": "rgba(190, 24, 93, 0.75)",
                    },
                    {
                        "label": "Mobile Money",
                        "data": chart_payload["shopCompareMobile"],
                        "backgroundColor": "rgba(124, 58, 237, 0.75)",
                    },
                    {
                        "label": "Profit/Loss",
                        "data": chart_payload["shopCompareProfit"],
                        "backgroundColor": "rgba(29, 78, 216, 0.75)",
                    },
                ],
            }
        )

    for shop_name in sorted(shop_daily_data.keys()):
        daily_points = shop_daily_data[shop_name]
        progressive_sales = []
        progressive_expenses = []
        progressive_profit = []
        running_sales = Decimal("0.00")
        running_expenses = Decimal("0.00")
        running_profit = Decimal("0.00")

        for point in daily_points.values():
            running_sales += point["sales"]
            running_expenses += point["expenses"]
            running_profit += point["profit"]
            progressive_sales.append(float(running_sales))
            progressive_expenses.append(float(running_expenses))
            progressive_profit.append(float(running_profit))

        if any(val != 0.0 for val in progressive_sales + progressive_expenses + progressive_profit):
            chart_cards.append(
                {
                    "category": "Shop",
                    "title": f"{shop_name} Trend ({start} to {end})",
                    "chartType": "line",
                    "labels": list(daily_points.keys()),
                    "datasets": [
                        {
                            "label": "Sales",
                            "data": progressive_sales,
                            "borderColor": "#0f766e",
                            "backgroundColor": "rgba(15, 118, 110, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                        {
                            "label": "Expenses",
                            "data": progressive_expenses,
                            "borderColor": "#b45309",
                            "backgroundColor": "rgba(180, 83, 9, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                        {
                            "label": "Profit/Loss",
                            "data": progressive_profit,
                            "borderColor": "#1d4ed8",
                            "backgroundColor": "rgba(29, 78, 216, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                    ],
                }
            )

    if any(value != 0.0 for value in chart_payload["generalPieValues"]):
        chart_cards.append(
            {
                "category": "General",
                "title": "General Distribution (All Shops)",
                "chartType": "pie",
                "labels": chart_payload["generalPieLabels"],
                "datasets": [
                    {
                        "label": "All Shops",
                        "data": chart_payload["generalPieValues"],
                        "backgroundColor": [
                            "rgba(15, 118, 110, 0.8)",
                            "rgba(180, 83, 9, 0.8)",
                            "rgba(190, 24, 93, 0.8)",
                            "rgba(29, 78, 216, 0.8)",
                            "rgba(124, 58, 237, 0.8)",
                            "rgba(22, 163, 74, 0.8)",
                            "rgba(127, 29, 29, 0.8)",
                        ],
                    }
                ],
            }
        )

    chart_payload["chartCards"] = chart_cards

    return {
        "form": form,
        "entries": entries,
        "start": start,
        "end": end,
        "period": period,
        "selected_date": selected_date,
        "filter_mode": filter_mode,
        "shop_chart_title": f"{chart_payload['shopName']} Historical Trend",
        "shop_bar_title": f"{chart_payload['shopName']} Day Snapshot ({chart_payload['shopBarDate']})",
        "totals": totals,
        "stock_consumed": stock_consumed,
        "total_sales": total_sales,
        "paid_sales_total": paid_sales_total,
        "mobile_money_total": total_mobile_money,
        "bank_opening_balance": balance_metrics["opening_balance"],
        "bank_closing_balance": balance_metrics["closing_balance"],
        "bank_received": balance_metrics["bank_received"],
        "bank_has_delta": balance_metrics["has_delta"],
        "balance": balance_metrics["closing_snapshot"] or balance_metrics["latest_balance"],
        "profit_or_loss": profit_or_loss,
        "chart_payload": chart_payload,
        "chart_cards_count": len(chart_cards),
    }


@login_required
@user_passes_test(_is_admin)
def report_view(request):
    dataset = _build_report_dataset(request.GET)
    return render(request, "sensa/report_view.html", dataset)


@login_required
@user_passes_test(_is_admin)
def jenga_settings_view(request):
    settings_obj = JengaApiSettings.objects.order_by("-updated_at", "-id").first()

    if request.method == "POST":
        form = JengaApiSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Jenga account settings saved.")
            return redirect("jenga_settings")
    else:
        form = JengaApiSettingsForm(instance=settings_obj)

    return render(
        request,
        "sensa/jenga_settings.html",
        {
            "form": form,
            "settings_obj": settings_obj,
        },
    )


@login_required
@user_passes_test(_is_admin)
def export_report_excel(request):
    dataset = _build_report_dataset(request.GET)
    entries = dataset["entries"]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sensa Report"

    sheet.append(["Sensa Report"])
    sheet.append(["Period", f"{dataset['start']} to {dataset['end']}"])
    sheet.append([])
    sheet.append(["Total Sales", float(dataset["total_sales"])])
    sheet.append(["Paid Sales", float(dataset["paid_sales_total"])])
    sheet.append(["Cash Received", float(dataset["totals"]["cash_received"])])
    sheet.append(["Mobile Money", float(dataset["mobile_money_total"])])
    sheet.append(["Credit Sales", float(dataset["totals"]["debts"])])
    sheet.append(["Stock Consumed", float(dataset["stock_consumed"])])
    sheet.append(["Expenses", float(dataset["totals"]["expenses"] or Decimal("0.00"))])
    sheet.append(["Bank Opening Balance", float(dataset["bank_opening_balance"])])
    sheet.append(["Bank Closing Balance", float(dataset["bank_closing_balance"])])
    sheet.append(["Bank Received", float(dataset["bank_received"])])
    sheet.append(["Profit/Loss", float(dataset["profit_or_loss"])])
    sheet.append([])
    sheet.append([
        "Date",
        "Shop",
        "Opening",
        "Added",
        "Expenses",
        "Sales",
        "Credit",
        "Closing",
        "Cash",
        "Mobile",
        "P/L",
    ])

    for entry in entries:
        sheet.append(
            [
                str(entry.entry_date),
                entry.shop.name,
                float(entry.opening_stock),
                float(entry.stock_added),
                float(entry.expenses),
                float(entry.sales_value),
                float(entry.debts),
                float(entry.closing_stock),
                float(entry.cash_received),
                float(entry.mobile_money_received),
                float(entry.profit_or_loss),
            ]
        )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f"attachment; filename=sensa-report-{dataset['start']}-to-{dataset['end']}.xlsx"
    )
    return response


@login_required
@user_passes_test(_is_admin)
def export_report_pdf(request):
    dataset = _build_report_dataset(request.GET)
    entries = dataset["entries"]

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    width, height = letter

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Sensa Value Report")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Period: {dataset['start']} to {dataset['end']}")
    y -= 18
    pdf.drawString(40, y, f"Total Sales: {dataset['total_sales']}")
    y -= 14
    pdf.drawString(40, y, f"Paid Sales: {dataset['paid_sales_total']}")
    y -= 14
    pdf.drawString(40, y, f"Cash Received: {dataset['totals']['cash_received']}")
    y -= 14
    pdf.drawString(40, y, f"Mobile Money: {dataset['mobile_money_total']}")
    y -= 14
    pdf.drawString(40, y, f"Stock Consumed: {dataset['stock_consumed']}")
    y -= 14
    pdf.drawString(40, y, f"Expenses: {dataset['totals']['expenses'] or Decimal('0.00')}")
    y -= 14
    pdf.drawString(40, y, f"Bank Received: {dataset['bank_received']}")
    y -= 14
    pdf.drawString(40, y, f"Profit/Loss: {dataset['profit_or_loss']}")
    y -= 24

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Date")
    pdf.drawString(92, y, "Shop")
    pdf.drawString(176, y, "Open")
    pdf.drawString(222, y, "Added")
    pdf.drawString(270, y, "Exp")
    pdf.drawString(316, y, "Sales")
    pdf.drawString(365, y, "Credit")
    pdf.drawString(414, y, "Close")
    pdf.drawString(458, y, "Cash")
    pdf.drawString(502, y, "Mobile")
    pdf.drawString(555, y, "P/L")
    y -= 14

    pdf.setFont("Helvetica", 8)
    for entry in entries:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Date")
            pdf.drawString(92, y, "Shop")
            pdf.drawString(176, y, "Open")
            pdf.drawString(222, y, "Added")
            pdf.drawString(270, y, "Exp")
            pdf.drawString(316, y, "Sales")
            pdf.drawString(365, y, "Credit")
            pdf.drawString(414, y, "Close")
            pdf.drawString(458, y, "Cash")
            pdf.drawString(502, y, "Mobile")
            pdf.drawString(555, y, "P/L")
            y -= 14
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(entry.entry_date))
        pdf.drawString(92, y, entry.shop.name[:14])
        pdf.drawRightString(214, y, f"{entry.opening_stock}")
        pdf.drawRightString(260, y, f"{entry.stock_added}")
        pdf.drawRightString(306, y, f"{entry.expenses}")
        pdf.drawRightString(355, y, f"{entry.sales_value}")
        pdf.drawRightString(404, y, f"{entry.debts}")
        pdf.drawRightString(449, y, f"{entry.closing_stock}")
        pdf.drawRightString(496, y, f"{entry.cash_received}")
        pdf.drawRightString(548, y, f"{entry.mobile_money_received}")
        pdf.drawRightString(602, y, f"{entry.profit_or_loss}")
        y -= 12

    pdf.save()
    output.seek(0)

    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f"attachment; filename=sensa-report-{dataset['start']}-to-{dataset['end']}.pdf"
    )
    return response


@login_required
@user_passes_test(_is_admin)
def fetch_balance(request):
    try:
        result = fetch_jenga_equity_balance()
        if result["ok"]:
            BankBalanceSnapshot.objects.create(
                provider=result["provider"],
                account_reference=result["account_reference"],
                balance=result["balance"],
                raw_response=result["raw"],
            )
            messages.success(request, f"Balance fetched: {result['balance']}")
    except Exception as exc:  # pylint: disable=broad-except
        messages.error(request, f"Failed to fetch balance: {exc}")

    return redirect("report_view")


@login_required
@user_passes_test(_is_admin)
def user_list(request):
    users = User.objects.select_related("profile").all().order_by("username")
    return render(request, "sensa/user_list.html", {"users": users})


@login_required
@user_passes_test(_is_admin)
def user_create(request):
    if request.method == "POST":
        form = UserManagementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User created successfully.")
            return redirect("user_list")
    else:
        form = UserManagementForm()

    return render(request, "sensa/user_form.html", {"form": form, "title": "Add User/Vendor"})


@login_required
@user_passes_test(_is_admin)
def user_edit_role(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    profile = target_user.profile

    if request.method == "POST":
        form = UserRoleUpdateForm(request.POST, profile=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "User updated.")
            return redirect("user_list")
    else:
        form = UserRoleUpdateForm(profile=profile)

    return render(
        request,
        "sensa/user_form.html",
        {
            "form": form,
            "title": f"Update {target_user.username}",
            "target_user": target_user,
        },
    )


@login_required
@user_passes_test(_is_admin)
def vendor_remove(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        target_user.is_active = False
        target_user.save()
        messages.success(request, "Vendor removed (deactivated).")
        return redirect("user_list")
    return render(request, "sensa/confirm_delete.html", {"item": target_user, "kind": "user"})
