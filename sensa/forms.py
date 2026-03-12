from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import DailyEntry, JengaApiSettings, Shop, UserProfile

User = get_user_model()


class ShopForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ["name", "location", "active"]


class DailyEntryForm(forms.ModelForm):
    mobile_money_received = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=14,
        label="Mobile Money",
        help_text="Optional. Enter any two of Credit, Cash, and Mobile. The third is auto-calculated.",
    )

    class Meta:
        model = DailyEntry
        fields = [
            "shop",
            "entry_date",
            "stock_added",
            "expenses",
            "sales_value",
            "debts",
            "closing_stock",
            "cash_received",
            "notes",
        ]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "debts": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Optional if cash and mobile are provided"}),
            "cash_received": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Optional if credit and mobile are provided"}),
            "sales_value": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if (
            not self.is_bound
            and not getattr(self.instance, "pk", None)
            and not self.initial.get("entry_date")
        ):
            self.fields["entry_date"].initial = timezone.localdate()

        if user and hasattr(user, "profile") and not user.profile.is_admin:
            self.fields["shop"].queryset = user.profile.assigned_shops.filter(active=True)

        # Allow system-assisted calculation for any one of debt/cash/mobile.
        self.fields["debts"].required = False
        self.fields["cash_received"].required = False

        if getattr(self.instance, "pk", None) and not self.is_bound:
            self.fields["mobile_money_received"].initial = self.instance.mobile_money_received

    def clean(self):
        cleaned_data = super().clean()
        sales_value = cleaned_data.get("sales_value")
        debts = cleaned_data.get("debts")
        cash_received = cleaned_data.get("cash_received")
        mobile_money = cleaned_data.get("mobile_money_received")

        if sales_value is None:
            return cleaned_data

        provided_count = sum(v is not None for v in [debts, cash_received, mobile_money])
        if provided_count < 2:
            raise forms.ValidationError(
                "Enter at least two payment values among Credit, Cash, and Mobile so the third can be calculated."
            )

        if debts is None:
            debts = sales_value - (cash_received or Decimal("0.00")) - (mobile_money or Decimal("0.00"))
        elif cash_received is None:
            cash_received = sales_value - debts - (mobile_money or Decimal("0.00"))
        elif mobile_money is None:
            mobile_money = sales_value - debts - cash_received

        if debts < Decimal("0.00"):
            self.add_error("debts", "Calculated credit sales cannot be negative. Check values entered.")
        if cash_received < Decimal("0.00"):
            self.add_error("cash_received", "Calculated cash received cannot be negative. Check values entered.")
        if mobile_money < Decimal("0.00"):
            self.add_error("mobile_money_received", "Calculated mobile money cannot be negative. Check values entered.")

        reconciliation_total = debts + cash_received + mobile_money
        if reconciliation_total != sales_value:
            raise forms.ValidationError(
                "Credit + Cash + Mobile must exactly equal Total Sales."
            )

        cleaned_data["debts"] = debts
        cleaned_data["cash_received"] = cash_received
        cleaned_data["mobile_money_received"] = mobile_money

        return cleaned_data


class JengaApiSettingsForm(forms.ModelForm):
    class Meta:
        model = JengaApiSettings
        fields = [
            "provider_name",
            "account_reference",
            "balance_endpoint",
            "balance_http_method",
            "balance_field_path",
            "api_token",
            "auth_endpoint",
            "client_id",
            "client_secret",
            "api_key",
            "grant_type",
            "scope",
        ]
        widgets = {
            "api_token": forms.PasswordInput(render_value=True),
            "client_secret": forms.PasswordInput(render_value=True),
        }

    def clean(self):
        cleaned_data = super().clean()
        api_token = (cleaned_data.get("api_token") or "").strip()
        auth_endpoint = (cleaned_data.get("auth_endpoint") or "").strip()
        client_id = (cleaned_data.get("client_id") or "").strip()
        client_secret = (cleaned_data.get("client_secret") or "").strip()
        balance_endpoint = (cleaned_data.get("balance_endpoint") or "").strip()
        account_reference = (cleaned_data.get("account_reference") or "").strip()

        if not account_reference:
            self.add_error("account_reference", "Receiving account reference is required.")

        if not balance_endpoint:
            self.add_error("balance_endpoint", "Balance endpoint is required.")

        if not api_token and not (auth_endpoint and client_id and client_secret):
            raise forms.ValidationError(
                "Provide either a static API token or the auth endpoint, client ID, and client secret."
            )

        return cleaned_data


class ReportFilterForm(forms.Form):
    PERIOD_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    period = forms.ChoiceField(choices=PERIOD_CHOICES, initial="daily", required=False)
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="Anchor Date",
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="Start Date",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="End Date",
    )
    shop = forms.ModelChoiceField(queryset=Shop.objects.filter(active=True), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["date"].initial = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after start date.")
        return cleaned_data


class UserManagementForm(forms.ModelForm):
    phone_number = forms.CharField(required=False)
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    assigned_shops = forms.ModelMultipleChoiceField(
        queryset=Shop.objects.filter(active=True), required=False
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        password = cleaned_data.get("password", "")
        phone_number = (cleaned_data.get("phone_number") or "").strip()

        if role == UserProfile.ADMIN:
            if not phone_number:
                self.add_error("phone_number", "Phone number is required for admin accounts.")
            elif not phone_number.isdigit():
                self.add_error("phone_number", "Phone number must contain numbers only.")
            if password and not password.isdigit():
                self.add_error("password", "Admin password must contain numbers only.")

            existing_profile = UserProfile.objects.filter(phone_number=phone_number).first()
            if existing_profile:
                self.add_error("phone_number", "This phone number is already in use.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data["password"]
        role = self.cleaned_data["role"]
        phone_number = (self.cleaned_data.get("phone_number") or "").strip()
        shops = self.cleaned_data["assigned_shops"]

        if role == UserProfile.ADMIN:
            user.username = phone_number
            user.is_staff = True

        user.set_password(password)
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.phone_number = phone_number
            profile.save()
            profile.assigned_shops.set(shops)
        return user


class UserRoleUpdateForm(forms.Form):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    phone_number = forms.CharField(required=False)
    assigned_shops = forms.ModelMultipleChoiceField(
        queryset=Shop.objects.filter(active=True), required=False
    )
    is_active = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        profile = kwargs.pop("profile")
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["role"].initial = profile.role
        self.fields["phone_number"].initial = profile.phone_number
        self.fields["assigned_shops"].initial = profile.assigned_shops.all()
        self.fields["is_active"].initial = profile.user.is_active

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        phone_number = (cleaned_data.get("phone_number") or "").strip()

        if role == UserProfile.ADMIN:
            if not phone_number:
                self.add_error("phone_number", "Phone number is required for admin accounts.")
            elif not phone_number.isdigit():
                self.add_error("phone_number", "Phone number must contain numbers only.")
            else:
                existing_profile = (
                    UserProfile.objects.exclude(pk=self.profile.pk)
                    .filter(phone_number=phone_number)
                    .first()
                )
                if existing_profile:
                    self.add_error("phone_number", "This phone number is already in use.")
        return cleaned_data

    def save(self):
        self.profile.role = self.cleaned_data["role"]
        self.profile.phone_number = (self.cleaned_data.get("phone_number") or "").strip()
        self.profile.save()
        self.profile.assigned_shops.set(self.cleaned_data["assigned_shops"])
        self.profile.user.is_active = self.cleaned_data["is_active"]
        if self.profile.role == UserProfile.ADMIN:
            self.profile.user.username = self.profile.phone_number
            self.profile.user.is_staff = True
        self.profile.user.save()
        return self.profile


class AdminBootstrapForm(forms.Form):
    username = forms.CharField(max_length=150)
    phone_number = forms.CharField(
        max_length=20,
        validators=[RegexValidator(r"^\d{9,15}$", "Enter a valid phone number (9-15 digits).")],
        help_text="Numbers only (not alphanumeric), e.g. 254712345678",
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=4,
        help_text="Use numbers only for simplicity.",
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not password.isdigit():
            raise forms.ValidationError("Password must contain numbers only.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        username = (cleaned_data.get("username") or "").strip()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        phone_number = cleaned_data.get("phone_number")

        if username and User.objects.filter(username=username).exists():
            self.add_error("username", "This username is already in use.")

        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")

        if phone_number and UserProfile.objects.filter(phone_number=phone_number).exists():
            self.add_error("phone_number", "This phone number is already in use.")

        return cleaned_data

    def save(self):
        username = self.cleaned_data["username"].strip()
        phone_number = self.cleaned_data["phone_number"]
        password = self.cleaned_data["password"]

        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=True,
            is_active=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = UserProfile.ADMIN
        profile.phone_number = phone_number
        profile.save()
        return user


class PhoneLoginForm(AuthenticationForm):
    username = forms.CharField(label="Phone Number or Username")
