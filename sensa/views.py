from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
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

    if not (_is_admin(user) or _is_vendor(user)):
        return HttpResponseForbidden("Not authorized.")

    if request.method == "POST":
        form = DailyEntryForm(request.POST, user=user)
        if form.is_valid():
            shop = form.cleaned_data["shop"]
            if _is_vendor(user) and not user.profile.assigned_shops.filter(pk=shop.pk).exists():
                return HttpResponseForbidden("You can only submit data to your assigned shops.")

            entry, _ = DailyEntry.objects.get_or_create(
                shop=shop,
                entry_date=form.cleaned_data["entry_date"],
                defaults={
                    "opening_stock": form.cleaned_data["opening_stock"],
                    "stock_added": form.cleaned_data["stock_added"],
                    "expenses": form.cleaned_data["expenses"],
                    "debts": form.cleaned_data["debts"],
                    "closing_stock": form.cleaned_data["closing_stock"],
                    "cash_received": form.cleaned_data["cash_received"],
                    "notes": form.cleaned_data["notes"],
                    "submitted_by": user,
                },
            )

            if entry.entry_date == today or _is_admin(user):
                entry.opening_stock = form.cleaned_data["opening_stock"]
                entry.stock_added = form.cleaned_data["stock_added"]
                entry.expenses = form.cleaned_data["expenses"]
                entry.debts = form.cleaned_data["debts"]
                entry.closing_stock = form.cleaned_data["closing_stock"]
                entry.cash_received = form.cleaned_data["cash_received"]
                entry.notes = form.cleaned_data["notes"]
                entry.submitted_by = user
                entry.save()
                messages.success(request, "Entry saved successfully.")
            else:
                messages.error(request, "Vendors can only update entries for the same day.")

            if _is_admin(user):
                return redirect("admin_dashboard")
            return redirect("vendor_dashboard")
    else:
        initial = {"entry_date": today}
        form = DailyEntryForm(user=user, initial=initial)

    return render(request, "sensa/entry_form.html", {"form": form})


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

    if form.is_valid():
        period = form.cleaned_data["period"]
        selected_shop = form.cleaned_data.get("shop")
        selected_date = form.cleaned_data.get("date")
    else:
        period = "daily"
        selected_shop = None
        selected_date = timezone.localdate()

    start, end = _date_range(period, selected_date)
    entries = entries.filter(entry_date__range=(start, end))
    if selected_shop:
        entries = entries.filter(shop=selected_shop)

    totals = entries.aggregate(
        opening_stock=Sum("opening_stock"),
        stock_added=Sum("stock_added"),
        expenses=Sum("expenses"),
        debts=Sum("debts"),
        closing_stock=Sum("closing_stock"),
        cash_received=Sum("cash_received"),
    )

    opening = totals["opening_stock"] or Decimal("0.00")
    added = totals["stock_added"] or Decimal("0.00")
    expenses = totals["expenses"] or Decimal("0.00")
    debts = totals["debts"] or Decimal("0.00")
    closing = totals["closing_stock"] or Decimal("0.00")
    cash = totals["cash_received"] or Decimal("0.00")

    stock_consumed = opening + added - closing
    total_sales = cash + debts
    profit_or_loss = total_sales - stock_consumed - expenses

    chart_payload = {
        "labels": ["Sales", "Stock Consumed", "Expenses", "Profit/Loss"],
        "values": [float(total_sales), float(stock_consumed), float(expenses), float(profit_or_loss)],
    }

    return {
        "form": form,
        "entries": entries,
        "start": start,
        "end": end,
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
    pdf.drawString(345, y, "Debt")
    pdf.drawString(395, y, "Close")
    pdf.drawString(445, y, "Cash")
    pdf.drawString(495, y, "P/L")
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
            pdf.drawString(345, y, "Debt")
            pdf.drawString(395, y, "Close")
            pdf.drawString(445, y, "Cash")
            pdf.drawString(495, y, "P/L")
            y -= 14
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(entry.entry_date))
        pdf.drawString(100, y, entry.shop.name[:18])
        pdf.drawRightString(245, y, f"{entry.opening_stock}")
        pdf.drawRightString(292, y, f"{entry.stock_added}")
        pdf.drawRightString(340, y, f"{entry.expenses}")
        pdf.drawRightString(390, y, f"{entry.debts}")
        pdf.drawRightString(440, y, f"{entry.closing_stock}")
        pdf.drawRightString(488, y, f"{entry.cash_received}")
        pdf.drawRightString(545, y, f"{entry.profit_or_loss}")
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
