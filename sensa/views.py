import os
from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter, landscape
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
from .services import fetch_and_store_jenga_equity_balance

User = get_user_model()


def healthcheck(request):
    """Health check endpoint for deployment verification."""
    return JsonResponse({"status": "ok", "service": "serensa"}, status=200)


class UserLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = PhoneLoginForm

    def form_invalid(self, form):
        messages.error(self.request, "Invalid phone/username or password.")
        return super().form_invalid(form)

    def get_success_url(self):
        try:
            # Ensure profile exists and is properly configured before redirect
            _resolve_profile(self.request.user)
        except Exception as e:
            messages.error(self.request, f"Profile setup error: {str(e)}")
            return "/"
        
        return self.get_redirect_url() or "/"


def _resolve_profile(user):
    """Ensure user has a valid profile with proper role and configuration.
    
    This is defensive — even if the signal didn't create a profile (edge case),
    or if role isn't set, this ensures it's corrected before use.
    """
    if not user.is_authenticated:
        return None

    try:
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
    except Exception as e:
        # Log but don't fail — allow user to continue
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error resolving profile for user {user.id}: {str(e)}")
        return None


def _is_admin(user):
    profile = _resolve_profile(user)
    return bool(profile and profile.is_admin)


def _is_vendor(user):
    profile = _resolve_profile(user)
    return bool(profile and not profile.is_admin)


def _vendor_accessible_shops(user):
    if not hasattr(user, "profile"):
        return Shop.objects.none()
    return user.profile.accessible_shops().order_by("parent_shop__name", "name")


def _vendor_can_access_shop(user, shop):
    if not hasattr(user, "profile") or not shop:
        return False
    if shop.subshops.filter(active=True).exists():
        return False
    return user.profile.accessible_shops().filter(pk=shop.pk).exists()


def bootstrap_admin(request):
    if UserProfile.objects.filter(role=UserProfile.ADMIN, user__is_active=True).exists():
        messages.info(request, "Admin account already exists. Please login.")
        return redirect("login")

    if request.method == "POST":
        form = AdminBootstrapForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(
                    request,
                    "Admin account created. Login using username or phone number and password.",
                )
                return redirect("login")
            except Exception as e:
                messages.error(request, f"Error creating admin account: {str(e)}")
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Admin bootstrap error: {str(e)}", exc_info=True)
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
    shops = _vendor_accessible_shops(request.user)
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
    manual_opening_required = False

    if request.method == "POST":
        shop_id = request.POST.get("shop")
        entry_date = request.POST.get("entry_date")
        posted_shop = None
        posted_entry_date = None
        if shop_id and entry_date:
            edit_entry = DailyEntry.objects.filter(shop_id=shop_id, entry_date=entry_date).first()
            posted_shop = Shop.objects.filter(pk=shop_id).first()
            try:
                posted_entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
            except ValueError:
                posted_entry_date = None

        previous_closing = _get_previous_closing_stock(
            posted_shop,
            posted_entry_date,
            current_entry=edit_entry,
        )
        manual_opening_required = previous_closing is None
        opening_stock_value = (
            previous_closing
            if previous_closing is not None
            else (edit_entry.opening_stock if edit_entry else Decimal("0.00"))
        )

        form = DailyEntryForm(
            request.POST,
            user=user,
            instance=edit_entry,
            require_opening_stock=manual_opening_required,
            calculated_opening_stock=opening_stock_value,
        )
        if form.is_valid():
            shop = form.cleaned_data["shop"]
            if _is_vendor(user) and not _vendor_can_access_shop(user, shop):
                return HttpResponseForbidden("You can only submit data to your assigned shops.")

            entry = form.save(commit=False)
            is_update = bool(entry.pk)
            previous_closing = _get_previous_closing_stock(shop, entry.entry_date, current_entry=edit_entry)
            manual_opening_required = previous_closing is None
            if manual_opening_required:
                entry.opening_stock = form.cleaned_data["opening_stock"]
            else:
                entry.opening_stock = previous_closing
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
            previous_closing = _get_previous_closing_stock(shop, parsed_date, current_entry=edit_entry)
            manual_opening_required = previous_closing is None
            opening_stock_value = (
                previous_closing
                if previous_closing is not None
                else (edit_entry.opening_stock if edit_entry else Decimal("0.00"))
            )
    else:
        initial = {"entry_date": today}

        if _is_vendor(user):
            accessible_shops = _vendor_accessible_shops(user)
            if selected_shop_id:
                selected_shop = accessible_shops.filter(pk=selected_shop_id).first()
            else:
                selected_shop = accessible_shops.first()
            if selected_shop:
                initial["shop"] = selected_shop
                edit_entry = DailyEntry.objects.filter(shop=selected_shop, entry_date=today).first()

        elif _is_admin(user) and selected_shop_id:
            selected_shop = Shop.objects.filter(pk=selected_shop_id).first()
            if selected_shop:
                initial["shop"] = selected_shop
                edit_entry = DailyEntry.objects.filter(shop=selected_shop, entry_date=today).first()

        if edit_entry:
            previous_closing = _get_previous_closing_stock(
                edit_entry.shop,
                edit_entry.entry_date,
                current_entry=edit_entry,
            )
            manual_opening_required = previous_closing is None
            opening_stock_value = (
                previous_closing if previous_closing is not None else edit_entry.opening_stock
            )
            form = DailyEntryForm(
                user=user,
                instance=edit_entry,
                require_opening_stock=manual_opening_required,
                calculated_opening_stock=opening_stock_value,
            )
        else:
            preview_shop = initial.get("shop")
            preview_date = initial.get("entry_date", today)
            previous_closing = _get_previous_closing_stock(preview_shop, preview_date)
            manual_opening_required = previous_closing is None
            opening_stock_value = previous_closing if previous_closing is not None else Decimal("0.00")
            form = DailyEntryForm(
                user=user,
                initial=initial,
                require_opening_stock=manual_opening_required,
                calculated_opening_stock=opening_stock_value,
            )

    context = {
        "form": form,
        "is_edit_mode": bool(edit_entry),
        "opening_stock_value": opening_stock_value,
        "manual_opening_required": manual_opening_required,
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
def entry_admin_edit(request, entry_id):
    entry = get_object_or_404(DailyEntry, pk=entry_id)
    previous_closing = _get_previous_closing_stock(entry.shop, entry.entry_date, current_entry=entry)
    manual_opening_required = previous_closing is None
    opening_stock_value = previous_closing if previous_closing is not None else entry.opening_stock

    if request.method == "POST":
        form = DailyEntryForm(
            request.POST,
            user=request.user,
            instance=entry,
            require_opening_stock=manual_opening_required,
            calculated_opening_stock=opening_stock_value,
        )
        if form.is_valid():
            updated = form.save(commit=False)
            previous_closing = _get_previous_closing_stock(
                updated.shop,
                updated.entry_date,
                current_entry=entry,
            )
            if previous_closing is None:
                updated.opening_stock = form.cleaned_data["opening_stock"]
            else:
                updated.opening_stock = previous_closing
            updated.submitted_by = request.user
            updated.save()
            messages.success(request, "Entry updated successfully.")
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(next_url or "report_view")
    else:
        form = DailyEntryForm(
            user=request.user,
            instance=entry,
            require_opening_stock=manual_opening_required,
            calculated_opening_stock=opening_stock_value,
        )

    context = {
        "form": form,
        "is_edit_mode": True,
        "opening_stock_value": opening_stock_value,
        "manual_opening_required": manual_opening_required,
        "form_title": "Admin Update Entry",
        "form_subtitle": "Edit an existing submitted entry.",
        "submit_label": "Update Entry",
        "next_url": request.GET.get("next") or request.POST.get("next") or "",
    }
    return render(request, "sensa/entry_form.html", context)


@login_required
@user_passes_test(_is_admin)
def entry_admin_delete(request, entry_id):
    entry = get_object_or_404(DailyEntry, pk=entry_id)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "Entry deleted.")
        next_url = request.POST.get("next") or request.GET.get("next")
        return redirect(next_url or "report_view")

    return render(
        request,
        "sensa/confirm_delete.html",
        {
            "item": entry,
            "kind": "entry",
            "next_url": request.GET.get("next") or "",
        },
    )


@login_required
@user_passes_test(_is_admin)
def shop_list(request):
    shops = Shop.objects.select_related("parent_shop").all().order_by("parent_shop__name", "name")
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


def _get_previous_closing_stock(shop, entry_date, current_entry=None):
    if not shop or not entry_date:
        return None

    entries = DailyEntry.objects.filter(shop=shop)
    if current_entry and current_entry.pk:
        entries = entries.exclude(pk=current_entry.pk)

    previous_day_entry = entries.filter(entry_date=entry_date - timedelta(days=1)).first()
    if previous_day_entry:
        return previous_day_entry.closing_stock or Decimal("0.00")

    latest_previous_entry = entries.filter(entry_date__lt=entry_date).order_by("-entry_date", "-updated_at").first()
    if latest_previous_entry:
        return latest_previous_entry.closing_stock or Decimal("0.00")

    return None


def _latest_entries_by_shop_day(entries):
    unique_by_shop_day = {}
    for entry in entries:
        key = (entry.shop_id, entry.entry_date)
        existing = unique_by_shop_day.get(key)
        if existing is None:
            unique_by_shop_day[key] = entry
            continue

        if entry.updated_at and existing.updated_at and entry.updated_at > existing.updated_at:
            unique_by_shop_day[key] = entry

    return sorted(
        unique_by_shop_day.values(),
        key=lambda item: (item.shop_id, item.entry_date, item.updated_at),
    )


def _calculate_stock_metrics(entries):
    # Keep one row per (shop, day) using the most recently updated entry.
    # This protects stock totals from accidental duplicate daily rows.
    normalized_entries = _latest_entries_by_shop_day(entries)

    per_shop = OrderedDict()
    for entry in normalized_entries:
        state = per_shop.setdefault(
            entry.shop_id,
            {
                "shop": entry.shop,
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
        elif entry.entry_date == state["last_date"]:
            state["closing"] = entry.closing_stock or Decimal("0.00")

        state["added"] += entry.stock_added or Decimal("0.00")

    opening_total = sum((state["opening"] for state in per_shop.values()), Decimal("0.00"))
    added_total = sum((state["added"] for state in per_shop.values()), Decimal("0.00"))
    closing_total = sum((state["closing"] for state in per_shop.values()), Decimal("0.00"))

    by_shop = []
    for state in per_shop.values():
        consumed = state["opening"] + state["added"] - state["closing"]
        by_shop.append(
            {
                "shop": state["shop"],
                "opening_stock": state["opening"],
                "stock_added": state["added"],
                "closing_stock": state["closing"],
                "stock_consumed": consumed,
                "first_date": state["first_date"],
                "last_date": state["last_date"],
            }
        )

    return {
        "opening_stock": opening_total,
        "stock_added": added_total,
        "closing_stock": closing_total,
        "stock_handled": opening_total + added_total,
        "stock_consumed": opening_total + added_total - closing_total,
        "by_shop": by_shop,
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
    show_charts = (query_data.get("show_charts") == "1") if query_data is not None else False

    today = timezone.localdate()
    if form.is_bound and form.is_valid():
        selected_date = form.cleaned_data.get("date") or today
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")

        month_anchor = end_date or start_date or selected_date
        period = "monthly"
        start, end = _date_range("monthly", month_anchor)
        filter_mode = "monthly"
        selected_shop = form.cleaned_data.get("shop")
    else:
        period = "monthly"
        selected_date = today
        start, end = _date_range("monthly", selected_date)
        selected_shop = None
        filter_mode = "monthly"

    entries_in_range_qs = entries_qs.filter(entry_date__range=(start, end)).order_by("entry_date", "shop__name")
    entries_qs = entries_in_range_qs
    if selected_shop:
        selected_shop_ids = [selected_shop.id]
        if selected_shop.parent_shop_id is None:
            selected_shop_ids.extend(
                list(
                    Shop.objects.filter(parent_shop=selected_shop, active=True).values_list(
                        "id", flat=True
                    )
                )
            )
        entries_qs = entries_qs.filter(shop_id__in=selected_shop_ids)

    # `entries` remain filter-aware for ledger/shop-specific sections,
    # while `general_entries` always represent all shops in the selected date window.
    entries = list(entries_qs)
    general_entries = list(entries_in_range_qs)
    normalized_entries = _latest_entries_by_shop_day(entries)
    normalized_general_entries = _latest_entries_by_shop_day(general_entries)

    stock_metrics = _calculate_stock_metrics(normalized_entries)
    total_sales = sum((entry.sales_value or Decimal("0.00") for entry in normalized_entries), Decimal("0.00"))
    total_expenses = sum((entry.expenses or Decimal("0.00") for entry in normalized_entries), Decimal("0.00"))
    total_debts = sum((entry.debts or Decimal("0.00") for entry in normalized_entries), Decimal("0.00"))
    total_cash = sum((entry.cash_received or Decimal("0.00") for entry in normalized_entries), Decimal("0.00"))
    total_mobile_money = sum((entry.mobile_money_received for entry in normalized_entries), Decimal("0.00"))
    paid_sales_total = total_sales - total_debts
    stock_consumed = stock_metrics["stock_consumed"]
    balance_metrics = _build_balance_metrics(start, end)

    totals = {
        "opening_stock": stock_metrics["opening_stock"],
        "stock_added": stock_metrics["stock_added"],
        "stock_handled": stock_metrics["stock_handled"],
        "expenses": total_expenses,
        "sales_value": total_sales,
        "debts": total_debts,
        "closing_stock": stock_metrics["closing_stock"],
        "cash_received": total_cash,
        "mobile_money": total_mobile_money,
        "paid_sales": paid_sales_total,
    }

    # Monthly profit uses monthly stock movement + sales volume + expense volume.
    monthly_start, monthly_end = _date_range("monthly", end)
    monthly_entries = _latest_entries_by_shop_day(
        list(
            DailyEntry.objects.select_related("shop").filter(
                entry_date__range=(monthly_start, monthly_end)
            )
        )
    )
    monthly_stock_metrics = _calculate_stock_metrics(monthly_entries)
    monthly_sales = sum((entry.sales_value or Decimal("0.00") for entry in monthly_entries), Decimal("0.00"))
    monthly_expenses = sum((entry.expenses or Decimal("0.00") for entry in monthly_entries), Decimal("0.00"))
    monthly_business_profit = monthly_sales - monthly_stock_metrics["stock_consumed"] - monthly_expenses

    monthly_sales_by_shop = {}
    monthly_expenses_by_shop = {}
    for entry in monthly_entries:
        monthly_sales_by_shop.setdefault(entry.shop_id, Decimal("0.00"))
        monthly_expenses_by_shop.setdefault(entry.shop_id, Decimal("0.00"))
        monthly_sales_by_shop[entry.shop_id] += entry.sales_value or Decimal("0.00")
        monthly_expenses_by_shop[entry.shop_id] += entry.expenses or Decimal("0.00")

    monthly_profit_by_shop = []
    for stock_row in monthly_stock_metrics["by_shop"]:
        shop_id = stock_row["shop"].id
        shop_sales = monthly_sales_by_shop.get(shop_id, Decimal("0.00"))
        shop_expenses = monthly_expenses_by_shop.get(shop_id, Decimal("0.00"))
        shop_profit = shop_sales - stock_row["stock_consumed"] - shop_expenses
        monthly_profit_by_shop.append(
            {
                "shop": stock_row["shop"],
                "sales": shop_sales,
                "expenses": shop_expenses,
                "stock_consumed": stock_row["stock_consumed"],
                "closing_stock": stock_row["closing_stock"],
                "profit": shop_profit,
            }
        )

    bar_date = end

    # --- Per-shop chart data built from `entries` (respects shop filter) ---
    shops_chart_data = OrderedDict()
    for entry in entries:
        shop_name = entry.shop.name
        if shop_name not in shops_chart_data:
            shops_chart_data[shop_name] = {"entries": [], "daily_points": OrderedDict()}
            cursor = start
            while cursor <= end:
                shops_chart_data[shop_name]["daily_points"][cursor.isoformat()] = {
                    "sales": Decimal("0.00"),
                    "expenses": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                }
                cursor += timedelta(days=1)
        shops_chart_data[shop_name]["entries"].append(entry)
        key = entry.entry_date.isoformat()
        shops_chart_data[shop_name]["daily_points"][key]["sales"] += entry.sales_value or Decimal("0.00")
        shops_chart_data[shop_name]["daily_points"][key]["expenses"] += entry.expenses or Decimal("0.00")
        shops_chart_data[shop_name]["daily_points"][key]["profit"] += entry.profit_or_loss or Decimal("0.00")

    # --- General cumulative data from `general_entries` (all shops, not shop-filtered) ---
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

    shop_compare = OrderedDict()

    for entry in normalized_general_entries:
        key = entry.entry_date.isoformat()
        all_daily_points[key]["sales"] += entry.sales_value or Decimal("0.00")
        all_daily_points[key]["expenses"] += entry.expenses or Decimal("0.00")
        all_daily_points[key]["debts"] += entry.debts or Decimal("0.00")
        all_daily_points[key]["profit"] += entry.profit_or_loss or Decimal("0.00")

        shop_key = entry.shop.name
        if shop_key not in shop_compare:
            shop_compare[shop_key] = {
                "sales": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "debts": Decimal("0.00"),
                "mobile": Decimal("0.00"),
                "profit": Decimal("0.00"),
            }
        shop_compare[shop_key]["sales"] += entry.sales_value or Decimal("0.00")
        shop_compare[shop_key]["expenses"] += entry.expenses or Decimal("0.00")
        shop_compare[shop_key]["debts"] += entry.debts or Decimal("0.00")
        shop_compare[shop_key]["mobile"] += entry.mobile_money_received
        shop_compare[shop_key]["profit"] += entry.profit_or_loss or Decimal("0.00")

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

    general_stock_metrics = _calculate_stock_metrics(normalized_general_entries)
    general_total_sales = sum((entry.sales_value or Decimal("0.00") for entry in normalized_general_entries), Decimal("0.00"))
    general_total_expenses = sum((entry.expenses or Decimal("0.00") for entry in normalized_general_entries), Decimal("0.00"))
    general_total_debts = sum((entry.debts or Decimal("0.00") for entry in normalized_general_entries), Decimal("0.00"))
    general_total_cash = sum((entry.cash_received or Decimal("0.00") for entry in normalized_general_entries), Decimal("0.00"))
    general_total_mobile = sum((entry.mobile_money_received for entry in normalized_general_entries), Decimal("0.00"))
    general_profit_or_loss = (
        general_total_sales - general_stock_metrics["stock_consumed"] - general_total_expenses
    )
    general_net_profit = (
        general_profit_or_loss if general_profit_or_loss > Decimal("0.00") else Decimal("0.00")
    )
    general_net_loss = (
        abs(general_profit_or_loss) if general_profit_or_loss < Decimal("0.00") else Decimal("0.00")
    )

    chart_payload = {
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
            float(general_total_sales),
            float(general_total_expenses),
            float(general_total_debts),
            float(general_total_cash),
            float(general_total_mobile),
            float(general_net_profit),
            float(general_net_loss),
        ],
    }

    chart_cards = []

    # --- Generate 3 chart cards for every shop that has data ---
    for shop_name, shop_data in shops_chart_data.items():
        s_entries = shop_data["entries"]
        daily_points = shop_data["daily_points"]
        date_labels = list(daily_points.keys())

        # Day Snapshot bar chart
        day_entries = [e for e in s_entries if e.entry_date == bar_date]
        if day_entries:
            d_sales = sum((e.sales_value or Decimal("0.00") for e in day_entries), Decimal("0.00"))
            d_expenses = sum((e.expenses or Decimal("0.00") for e in day_entries), Decimal("0.00"))
            d_debts = sum((e.debts or Decimal("0.00") for e in day_entries), Decimal("0.00"))
            d_cash = sum((e.cash_received or Decimal("0.00") for e in day_entries), Decimal("0.00"))
            d_mobile = sum((e.mobile_money_received for e in day_entries), Decimal("0.00"))
            d_profit = sum((e.profit_or_loss or Decimal("0.00") for e in day_entries), Decimal("0.00"))
            bar_values = [
                float(d_sales), float(d_expenses), float(d_debts),
                float(d_cash), float(d_mobile), float(d_profit),
            ]
            if any(v != 0.0 for v in bar_values):
                chart_cards.append(
                    {
                        "category": "Shop",
                        "title": f"{shop_name} Day Snapshot ({bar_date})",
                        "chartType": "bar",
                        "labels": ["Sales", "Expenses", "Credit", "Cash", "Mobile", "Profit/Loss"],
                        "datasets": [
                            {
                                "label": f"{shop_name} ({bar_date})",
                                "data": bar_values,
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

        # Cumulative Trend line chart
        prog_sales = []
        prog_expenses = []
        prog_profit = []
        r_sales = Decimal("0.00")
        r_expenses = Decimal("0.00")
        r_profit = Decimal("0.00")
        for point in daily_points.values():
            r_sales += point["sales"]
            r_expenses += point["expenses"]
            r_profit += point["profit"]
            prog_sales.append(float(r_sales))
            prog_expenses.append(float(r_expenses))
            prog_profit.append(float(r_profit))

        if any(v != 0.0 for v in prog_sales + prog_expenses + prog_profit):
            chart_cards.append(
                {
                    "category": "Shop",
                    "title": f"{shop_name} Cumulative Trend",
                    "chartType": "line",
                    "labels": date_labels,
                    "datasets": [
                        {
                            "label": "Sales",
                            "data": prog_sales,
                            "borderColor": "#0f766e",
                            "backgroundColor": "rgba(15, 118, 110, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                        {
                            "label": "Expenses",
                            "data": prog_expenses,
                            "borderColor": "#b45309",
                            "backgroundColor": "rgba(180, 83, 9, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                        {
                            "label": "Profit/Loss",
                            "data": prog_profit,
                            "borderColor": "#1d4ed8",
                            "backgroundColor": "rgba(29, 78, 216, 0.08)",
                            "tension": 0.45,
                            "fill": True,
                        },
                    ],
                }
            )

        # Cumulative Distribution pie chart
        s_stock = _calculate_stock_metrics(s_entries)
        s_sales = sum((e.sales_value or Decimal("0.00") for e in s_entries), Decimal("0.00"))
        s_expenses = sum((e.expenses or Decimal("0.00") for e in s_entries), Decimal("0.00"))
        s_debts = sum((e.debts or Decimal("0.00") for e in s_entries), Decimal("0.00"))
        s_cash = sum((e.cash_received or Decimal("0.00") for e in s_entries), Decimal("0.00"))
        s_mobile = sum((e.mobile_money_received for e in s_entries), Decimal("0.00"))
        s_profit_total = s_sales - s_stock["stock_consumed"] - s_expenses
        s_net_profit = s_profit_total if s_profit_total > Decimal("0.00") else Decimal("0.00")
        s_net_loss = abs(s_profit_total) if s_profit_total < Decimal("0.00") else Decimal("0.00")
        pie_values = [
            float(s_sales), float(s_expenses), float(s_debts),
            float(s_cash), float(s_mobile), float(s_net_profit), float(s_net_loss),
        ]
        if any(v != 0.0 for v in pie_values):
            chart_cards.append(
                {
                    "category": "Shop",
                    "title": f"{shop_name} Cumulative Distribution",
                    "chartType": "pie",
                    "labels": ["Sales", "Expenses", "Credit", "Cash", "Mobile", "Net Profit", "Net Loss"],
                    "datasets": [
                        {
                            "label": shop_name,
                            "data": pie_values,
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
        "selected_shop": selected_shop,
        "show_charts": show_charts,
        "start": start,
        "end": end,
        "period": period,
        "selected_date": selected_date,
        "filter_mode": filter_mode,
        "totals": totals,
        "stock_by_shop": stock_metrics["by_shop"],
        "stock_consumed": stock_consumed,
        "total_sales": total_sales,
        "paid_sales_total": paid_sales_total,
        "mobile_money_total": total_mobile_money,
        "bank_opening_balance": balance_metrics["opening_balance"],
        "bank_closing_balance": balance_metrics["closing_balance"],
        "bank_received": balance_metrics["bank_received"],
        "bank_has_delta": balance_metrics["has_delta"],
        "balance": balance_metrics["closing_snapshot"] or balance_metrics["latest_balance"],
        "monthly_profit_start": monthly_start,
        "monthly_profit_end": monthly_end,
        "monthly_business_profit": monthly_business_profit,
        "monthly_profit_by_shop": monthly_profit_by_shop,
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

    sheet.append(["Serensa Enterprise Report"])
    sheet.append(["Period", f"{dataset['start']} to {dataset['end']}"])
    sheet.append([])
    sheet.append(["Total Existing Stock", float(dataset["totals"]["opening_stock"])])
    sheet.append(["Total Added Stock", float(dataset["totals"]["stock_added"])])
    sheet.append(["Total Stock Handled", float(dataset["totals"]["stock_handled"])])
    sheet.append(["Total Closing Stock", float(dataset["totals"]["closing_stock"])])
    sheet.append(["Total Sales", float(dataset["total_sales"])])
    sheet.append(["Total Debts", float(dataset["totals"]["debts"])])
    sheet.append(["Total Expenses", float(dataset["totals"]["expenses"] or Decimal("0.00"))])
    sheet.append(["Monthly Profit", float(dataset["monthly_business_profit"])])
    sheet.append([])
    sheet.append([
        "Date",
        "Shop",
        "Type",
        "Existing Stock",
        "Added Stock",
        "Expenses",
        "Sales",
        "Debts",
        "Closing Stock",
    ])

    for entry in entries:
        sheet.append(
            [
                str(entry.entry_date),
                entry.shop.name,
                entry.shop.get_shop_type_display(),
                float(entry.opening_stock or Decimal("0.00")),
                float(entry.stock_added or Decimal("0.00")),
                float(entry.expenses or Decimal("0.00")),
                float(entry.sales_value or Decimal("0.00")),
                float(entry.debts or Decimal("0.00")),
                float(entry.closing_stock or Decimal("0.00")),
            ]
        )

    if entries:
        sheet.append(
            [
                "Totals",
                "",
                "",
                float(dataset["totals"]["opening_stock"]),
                float(dataset["totals"]["stock_added"]),
                float(dataset["totals"]["expenses"] or Decimal("0.00")),
                float(dataset["totals"]["sales_value"]),
                float(dataset["totals"]["debts"]),
                float(dataset["totals"]["closing_stock"]),
            ]
        )

    sheet.append([])
    sheet.append(["Monthly Profit Window", f"{dataset['monthly_profit_start']} to {dataset['monthly_profit_end']}"])
    sheet.append(["Business Monthly Profit", float(dataset["monthly_business_profit"])])
    sheet.append([])
    sheet.append(["Shop", "Type", "Sales Volume", "Expenses Volume", "Stock Consumed", "Closing Stock", "Profit"])
    monthly_rows = dataset["monthly_profit_by_shop"]
    for item in monthly_rows:
        sheet.append(
            [
                item["shop"].name,
                item["shop"].get_shop_type_display(),
                float(item["sales"]),
                float(item["expenses"]),
                float(item["stock_consumed"]),
                float(item["closing_stock"]),
                float(item["profit"]),
            ]
        )

    if monthly_rows:
        sheet.append(
            [
                "Grand Total",
                "",
                float(sum((item["sales"] for item in monthly_rows), Decimal("0.00"))),
                float(sum((item["expenses"] for item in monthly_rows), Decimal("0.00"))),
                float(sum((item["stock_consumed"] for item in monthly_rows), Decimal("0.00"))),
                float(sum((item["closing_stock"] for item in monthly_rows), Decimal("0.00"))),
                float(sum((item["profit"] for item in monthly_rows), Decimal("0.00"))),
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
    pdf = canvas.Canvas(output, pagesize=landscape(letter))
    width, height = landscape(letter)

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Serensa Enterprise Value Report")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Period: {dataset['start']} to {dataset['end']}")
    y -= 18
    pdf.drawString(40, y, f"Total Existing Stock: {dataset['totals']['opening_stock']}")
    y -= 14
    pdf.drawString(40, y, f"Total Added Stock: {dataset['totals']['stock_added']}")
    y -= 14
    pdf.drawString(40, y, f"Total Stock Handled: {dataset['totals']['stock_handled']}")
    y -= 14
    pdf.drawString(40, y, f"Total Closing Stock: {dataset['totals']['closing_stock']}")
    y -= 14
    pdf.drawString(40, y, f"Total Sales: {dataset['total_sales']}")
    y -= 14
    pdf.drawString(40, y, f"Total Debts: {dataset['totals']['debts']}")
    y -= 14
    pdf.drawString(40, y, f"Expenses: {dataset['totals']['expenses'] or Decimal('0.00')}")
    y -= 14
    pdf.drawString(
        40,
        y,
        f"Monthly Profit ({dataset['monthly_profit_start']} to {dataset['monthly_profit_end']}): {dataset['monthly_business_profit']}",
    )
    y -= 24

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Date")
    pdf.drawString(106, y, "Shop")
    pdf.drawString(220, y, "Type")
    pdf.drawString(286, y, "Exist")
    pdf.drawString(341, y, "Added")
    pdf.drawString(396, y, "Exp")
    pdf.drawString(451, y, "Sales")
    pdf.drawString(506, y, "Debts")
    pdf.drawString(561, y, "Close")
    y -= 14

    pdf.setFont("Helvetica", 8)
    for entry in entries:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Date")
            pdf.drawString(106, y, "Shop")
            pdf.drawString(220, y, "Type")
            pdf.drawString(286, y, "Exist")
            pdf.drawString(341, y, "Added")
            pdf.drawString(396, y, "Exp")
            pdf.drawString(451, y, "Sales")
            pdf.drawString(506, y, "Debts")
            pdf.drawString(561, y, "Close")
            y -= 14
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(entry.entry_date))
        pdf.drawString(106, y, entry.shop.name[:20])
        pdf.drawString(220, y, entry.shop.get_shop_type_display()[:10])
        pdf.drawRightString(334, y, f"{entry.opening_stock}")
        pdf.drawRightString(389, y, f"{entry.stock_added}")
        pdf.drawRightString(444, y, f"{entry.expenses}")
        pdf.drawRightString(499, y, f"{entry.sales_value}")
        pdf.drawRightString(554, y, f"{entry.debts}")
        pdf.drawRightString(609, y, f"{entry.closing_stock}")
        y -= 12

    if entries:
        if y < 52:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Date")
            pdf.drawString(106, y, "Shop")
            pdf.drawString(220, y, "Type")
            pdf.drawString(286, y, "Exist")
            pdf.drawString(341, y, "Added")
            pdf.drawString(396, y, "Exp")
            pdf.drawString(451, y, "Sales")
            pdf.drawString(506, y, "Debts")
            pdf.drawString(561, y, "Close")
            y -= 14

        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(40, y, "Totals")
        pdf.drawRightString(334, y, f"{dataset['totals']['opening_stock']}")
        pdf.drawRightString(389, y, f"{dataset['totals']['stock_added']}")
        pdf.drawRightString(444, y, f"{dataset['totals']['expenses'] or Decimal('0.00')}")
        pdf.drawRightString(499, y, f"{dataset['totals']['sales_value']}")
        pdf.drawRightString(554, y, f"{dataset['totals']['debts']}")
        pdf.drawRightString(609, y, f"{dataset['totals']['closing_stock']}")
        y -= 14

    if y < 120:
        pdf.showPage()
        y = height - 40

    y -= 8
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Monthly Profit by Shop")
    y -= 16
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Shop")
    pdf.drawString(190, y, "Type")
    pdf.drawString(270, y, "Sales")
    pdf.drawString(350, y, "Expenses")
    pdf.drawString(440, y, "Consumed")
    pdf.drawString(530, y, "Closing")
    pdf.drawString(620, y, "Profit")
    y -= 14
    pdf.setFont("Helvetica", 8)

    monthly_rows = dataset["monthly_profit_by_shop"]
    for item in monthly_rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Shop")
            pdf.drawString(190, y, "Type")
            pdf.drawString(270, y, "Sales")
            pdf.drawString(350, y, "Expenses")
            pdf.drawString(440, y, "Consumed")
            pdf.drawString(530, y, "Closing")
            pdf.drawString(620, y, "Profit")
            y -= 14
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, item["shop"].name[:24])
        pdf.drawString(190, y, item["shop"].get_shop_type_display()[:12])
        pdf.drawRightString(335, y, f"{item['sales']}")
        pdf.drawRightString(425, y, f"{item['expenses']}")
        pdf.drawRightString(515, y, f"{item['stock_consumed']}")
        pdf.drawRightString(605, y, f"{item['closing_stock']}")
        pdf.drawRightString(750, y, f"{item['profit']}")
        y -= 12

    if monthly_rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Shop")
            pdf.drawString(190, y, "Type")
            pdf.drawString(270, y, "Sales")
            pdf.drawString(350, y, "Expenses")
            pdf.drawString(440, y, "Consumed")
            pdf.drawString(530, y, "Closing")
            pdf.drawString(620, y, "Profit")
            y -= 14

        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(40, y, "Grand Total")
        pdf.drawRightString(335, y, f"{sum((item['sales'] for item in monthly_rows), Decimal('0.00'))}")
        pdf.drawRightString(425, y, f"{sum((item['expenses'] for item in monthly_rows), Decimal('0.00'))}")
        pdf.drawRightString(515, y, f"{sum((item['stock_consumed'] for item in monthly_rows), Decimal('0.00'))}")
        pdf.drawRightString(605, y, f"{sum((item['closing_stock'] for item in monthly_rows), Decimal('0.00'))}")
        pdf.drawRightString(750, y, f"{sum((item['profit'] for item in monthly_rows), Decimal('0.00'))}")
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
        result, _snapshot = fetch_and_store_jenga_equity_balance()
        if result["ok"]:
            messages.success(request, f"Balance fetched: {result['balance']}")
    except Exception as exc:  # pylint: disable=broad-except
        messages.error(request, f"Failed to fetch balance: {exc}")

    return redirect("report_view")


def cron_fetch_balance(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {cron_secret}":
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        result, snapshot = fetch_and_store_jenga_equity_balance()
        return JsonResponse(
            {
                "ok": result["ok"],
                "provider": snapshot.provider,
                "account_reference": snapshot.account_reference,
                "balance": str(snapshot.balance),
                "fetched_at": snapshot.fetched_at.isoformat(),
            },
            status=200,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


@login_required
@user_passes_test(_is_admin)
def user_list(request):
    users = (
        User.objects.select_related("profile")
        .all()
        .order_by("username")
    )
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
        target_user.delete()
        messages.success(request, "Vendor permanently deleted.")
        return redirect("user_list")
    return render(request, "sensa/confirm_delete.html", {"item": target_user, "kind": "user"})
