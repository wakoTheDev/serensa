from collections import OrderedDict
from datetime import timedelta
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
    PhoneLoginForm,
    ReportFilterForm,
    ShopForm,
    UserManagementForm,
    UserRoleUpdateForm,
)
from .models import BankBalanceSnapshot, DailyEntry, Shop, UserProfile
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
        else:
            form = DailyEntryForm(user=user, initial=initial)

    context = {
        "form": form,
        "is_edit_mode": bool(edit_entry),
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


def _build_report_dataset(query_data):
    form = ReportFilterForm(query_data or None)
    entries = DailyEntry.objects.select_related("shop", "submitted_by")

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
        start = entries.order_by("entry_date").values_list("entry_date", flat=True).first() or today
        end = today
        selected_shop = None
        filter_mode = "historical"

    entries = entries.filter(entry_date__range=(start, end)).order_by("entry_date", "shop__name")
    if selected_shop:
        entries = entries.filter(shop=selected_shop)

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

    if chart_shop:
        shop_entries = DailyEntry.objects.filter(
            shop=chart_shop,
            entry_date__range=(start, end),
        ).order_by("entry_date")
    else:
        shop_entries = DailyEntry.objects.none()

    totals = entries.aggregate(
        opening_stock=Sum("opening_stock"),
        stock_added=Sum("stock_added"),
        expenses=Sum("expenses"),
        sales_value=Sum("sales_value"),
        debts=Sum("debts"),
        closing_stock=Sum("closing_stock"),
        cash_received=Sum("cash_received"),
    )

    opening = totals["opening_stock"] or Decimal("0.00")
    added = totals["stock_added"] or Decimal("0.00")
    expenses = totals["expenses"] or Decimal("0.00")
    closing = totals["closing_stock"] or Decimal("0.00")
    total_sales = totals["sales_value"] or Decimal("0.00")

    stock_consumed = opening + added - closing
    profit_or_loss = total_sales - stock_consumed - expenses
    net_profit = profit_or_loss if profit_or_loss > Decimal("0.00") else Decimal("0.00")
    net_loss = abs(profit_or_loss) if profit_or_loss < Decimal("0.00") else Decimal("0.00")

    # Shop-specific historical trend (progressive/cumulative).
    shop_daily_points = OrderedDict()
    cursor = start
    while cursor <= end:
        shop_daily_points[cursor.isoformat()] = {
            "sales": Decimal("0.00"),
            "expenses": Decimal("0.00"),
            "debts": Decimal("0.00"),
            "profit": Decimal("0.00"),
        }
        cursor += timedelta(days=1)

    for entry in shop_entries:
        key = entry.entry_date.isoformat()
        if key not in shop_daily_points:
            shop_daily_points[key] = {
                "sales": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "debts": Decimal("0.00"),
                "profit": Decimal("0.00"),
            }
        shop_daily_points[key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_daily_points[key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_daily_points[key]["debts"] += entry.debts or Decimal("0.00")
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

    # Shop-specific same-day bar snapshot.
    bar_date = selected_date if filter_mode == "period" else end
    if filter_mode == "historical":
        bar_date = today

    shop_day_entries = DailyEntry.objects.none()
    if chart_shop:
        shop_day_entries = DailyEntry.objects.filter(shop=chart_shop, entry_date=bar_date)

    day_sales = Decimal("0.00")
    day_expenses = Decimal("0.00")
    day_debts = Decimal("0.00")
    day_cash = Decimal("0.00")
    day_profit = Decimal("0.00")

    for entry in shop_day_entries:
        day_sales += entry.sales_value or Decimal("0.00")
        day_expenses += entry.expenses or Decimal("0.00")
        day_debts += entry.debts or Decimal("0.00")
        day_cash += entry.cash_received or Decimal("0.00")
        day_profit += entry.profit_or_loss or Decimal("0.00")

    # All-shops cumulative trend across selected range.
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

    # Per-shop comparison across selected range.
    shop_compare = OrderedDict()
    for entry in entries:
        key = entry.shop.name
        if key not in shop_compare:
            shop_compare[key] = {
                "sales": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "debts": Decimal("0.00"),
                "profit": Decimal("0.00"),
            }
        shop_compare[key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_compare[key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_compare[key]["debts"] += entry.debts or Decimal("0.00")
        shop_compare[key]["profit"] += entry.profit_or_loss or Decimal("0.00")

    chart_payload = {
        "shopName": chart_shop.name if chart_shop else "No Shop",
        "shopBarDate": str(bar_date),
        "shopBarLabels": ["Sales", "Expenses", "Debts", "Cash", "Profit/Loss"],
        "shopBarValues": [
            float(day_sales),
            float(day_expenses),
            float(day_debts),
            float(day_cash),
            float(day_profit),
        ],
        "trendLabels": list(shop_daily_points.keys()),
        "trendSales": progressive_shop_sales,
        "trendExpenses": progressive_shop_expenses,
        "trendProfit": progressive_shop_profit,
        "allCumulativeLabels": list(all_daily_points.keys()),
        "allCumulativeSales": cumulative_sales,
        "allCumulativeExpenses": cumulative_expenses,
        "allCumulativeDebts": cumulative_debts,
        "allCumulativeProfit": cumulative_profit,
        "shopCompareLabels": list(shop_compare.keys()),
        "shopCompareSales": [float(v["sales"]) for v in shop_compare.values()],
        "shopCompareExpenses": [float(v["expenses"]) for v in shop_compare.values()],
        "shopCompareDebts": [float(v["debts"]) for v in shop_compare.values()],
        "shopCompareProfit": [float(v["profit"]) for v in shop_compare.values()],
        "generalPieLabels": ["Sales", "Expenses", "Debts", "Net Profit", "Net Loss"],
        "generalPieValues": [
            float(total_sales),
            float(expenses),
            float(totals["debts"] or Decimal("0.00")),
            float(net_profit),
            float(net_loss),
        ],
    }

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
        "profit_or_loss": profit_or_loss,
        "chart_payload": chart_payload,
    }


@login_required
@user_passes_test(_is_admin)
def report_view(request):
    dataset = _build_report_dataset(request.GET)
    balance = BankBalanceSnapshot.objects.first()
    context = {**dataset, "balance": balance}
    return render(request, "sensa/report_view.html", context)


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
    sheet.append(["Stock Consumed", float(dataset["stock_consumed"])])
    sheet.append(["Expenses", float(dataset["totals"]["expenses"] or Decimal("0.00"))])
    sheet.append(["Profit/Loss", float(dataset["profit_or_loss"])])
    sheet.append([])
    sheet.append([
        "Date",
        "Shop",
        "Opening",
        "Added",
        "Expenses",
        "Sales",
        "Debts",
        "Closing",
        "Cash",
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
    pdf.drawString(40, y, f"Stock Consumed: {dataset['stock_consumed']}")
    y -= 14
    pdf.drawString(40, y, f"Expenses: {dataset['totals']['expenses'] or Decimal('0.00')}")
    y -= 14
    pdf.drawString(40, y, f"Profit/Loss: {dataset['profit_or_loss']}")
    y -= 24

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Date")
    pdf.drawString(100, y, "Shop")
    pdf.drawString(205, y, "Open")
    pdf.drawString(250, y, "Added")
    pdf.drawString(300, y, "Exp")
    pdf.drawString(340, y, "Sales")
    pdf.drawString(390, y, "Debt")
    pdf.drawString(435, y, "Close")
    pdf.drawString(480, y, "Cash")
    pdf.drawString(525, y, "P/L")
    y -= 14

    pdf.setFont("Helvetica", 8)
    for entry in entries:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Date")
            pdf.drawString(100, y, "Shop")
            pdf.drawString(205, y, "Open")
            pdf.drawString(250, y, "Added")
            pdf.drawString(300, y, "Exp")
            pdf.drawString(340, y, "Sales")
            pdf.drawString(390, y, "Debt")
            pdf.drawString(435, y, "Close")
            pdf.drawString(480, y, "Cash")
            pdf.drawString(525, y, "P/L")
            y -= 14
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(entry.entry_date))
        pdf.drawString(100, y, entry.shop.name[:18])
        pdf.drawRightString(245, y, f"{entry.opening_stock}")
        pdf.drawRightString(292, y, f"{entry.stock_added}")
        pdf.drawRightString(340, y, f"{entry.expenses}")
        pdf.drawRightString(388, y, f"{entry.sales_value}")
        pdf.drawRightString(433, y, f"{entry.debts}")
        pdf.drawRightString(478, y, f"{entry.closing_stock}")
        pdf.drawRightString(523, y, f"{entry.cash_received}")
        pdf.drawRightString(570, y, f"{entry.profit_or_loss}")
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
