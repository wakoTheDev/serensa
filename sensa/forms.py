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
        fields = ["name", "shop_type", "parent_shop", "location", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent_shop"].queryset = Shop.objects.filter(
            active=True,
            parent_shop__isnull=True,
        ).order_by("name")
        self.fields["parent_shop"].required = False
        self.fields["parent_shop"].help_text = (
            "Leave blank for a parent enterprise. Select a parent to create a subshop."
        )

        if self.instance and self.instance.pk:
            self.fields["parent_shop"].queryset = self.fields["parent_shop"].queryset.exclude(
                pk=self.instance.pk
            )

    def clean_parent_shop(self):
        parent_shop = self.cleaned_data.get("parent_shop")
        if parent_shop and parent_shop.parent_shop_id:
            raise forms.ValidationError("You can only attach a subshop to a parent enterprise.")

        if (
            parent_shop
            and self.instance
            and self.instance.pk
            and self.instance.subshops.exists()
        ):
            raise forms.ValidationError(
                "A parent enterprise with subshops cannot be moved under another parent."
            )
        return parent_shop


class DailyEntryForm(forms.ModelForm):
    class Meta:
        model = DailyEntry
        fields = [
            "shop",
            "entry_date",
            "opening_stock",
            "stock_added",
            "expenses",
            "sales_value",
            "debts",
            "closing_stock",
        ]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "sales_value": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        require_opening_stock = kwargs.pop("require_opening_stock", False)
        calculated_opening_stock = kwargs.pop("calculated_opening_stock", Decimal("0.00"))
        super().__init__(*args, **kwargs)

        base_shop_queryset = Shop.objects.filter(active=True).exclude(subshops__active=True).distinct()
        self.fields["shop"].queryset = base_shop_queryset.order_by("parent_shop__name", "name")

        if (
            not self.is_bound
            and not getattr(self.instance, "pk", None)
            and not self.initial.get("entry_date")
        ):
            self.fields["entry_date"].initial = timezone.localdate()

        if user and hasattr(user, "profile") and not user.profile.is_admin:
            self.fields["shop"].queryset = user.profile.accessible_shops().order_by(
                "parent_shop__name", "name"
            )

        self.fields["shop"].label_from_instance = self._shop_label

        self.fields["sales_value"].label = "Sales"
        self.fields["debts"].label = "Debts"
        self.fields["stock_added"].label = "Added Stock"
        self.fields["opening_stock"].label = "Existing Stock"
        self.fields["closing_stock"].label = "Closing Stock"
        self.fields["expenses"].label = "Expenses"
        self.fields["shop"].help_text = (
            "Data is captured per operational shop. If an enterprise has subshops, submit to each subshop."
        )

        if require_opening_stock:
            self.fields["opening_stock"].required = True
            self.fields["opening_stock"].disabled = False
        else:
            self.fields["opening_stock"].required = False
            self.fields["opening_stock"].initial = calculated_opening_stock
            self.fields["opening_stock"].disabled = True

    @staticmethod
    def _shop_label(shop):
        if shop.parent_shop_id:
            return f"{shop.parent_shop.name} / {shop.name}"
        return shop.name

    def clean(self):
        cleaned_data = super().clean()
        shop = cleaned_data.get("shop")
        sales_value = cleaned_data.get("sales_value")
        debts = cleaned_data.get("debts")

        if shop and shop.subshops.filter(active=True).exists():
            self.add_error(
                "shop",
                "This is a parent enterprise. Submit entries to its subshops instead.",
            )

        if sales_value is None or debts is None:
            return cleaned_data

        if debts > sales_value:
            self.add_error("debts", "Debts cannot be greater than sales.")

        return cleaned_data

    def save(self, commit=True):
        entry = super().save(commit=False)
        sales_value = self.cleaned_data.get("sales_value") or Decimal("0.00")
        debts = self.cleaned_data.get("debts") or Decimal("0.00")
        entry.cash_received = sales_value - debts

        if commit:
            entry.save()
        return entry


class JengaApiSettingsForm(forms.ModelForm):
    class Meta:
        model = JengaApiSettings
        fields = ["account_reference"]
        labels = {
            "account_reference": "Receiving Account Number / Reference",
        }
        help_texts = {
            "account_reference": "Enter the bank account or till reference where funds are received.",
        }

    def clean(self):
        cleaned_data = super().clean()
        account_reference = (cleaned_data.get("account_reference") or "").strip()

        if not account_reference:
            self.add_error("account_reference", "Receiving account reference is required.")

        cleaned_data["account_reference"] = account_reference

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
    shop = forms.ModelChoiceField(
        queryset=Shop.objects.filter(active=True).order_by("parent_shop__name", "name"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["date"].initial = timezone.localdate()
        self.fields["shop"].label_from_instance = DailyEntryForm._shop_label

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
        queryset=Shop.objects.filter(active=True, parent_shop__isnull=True), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_shops"].help_text = (
            "Assign parent enterprises. If a parent has subshops, vendors will submit entries to those child shops (not the parent)."
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

        assigned_shops = cleaned_data.get("assigned_shops") or []
        if any(shop.parent_shop_id for shop in assigned_shops):
            self.add_error("assigned_shops", "Assign users to parent shops only.")
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
        queryset=Shop.objects.filter(active=True, parent_shop__isnull=True), required=False
    )
    is_active = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        profile = kwargs.pop("profile")
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["role"].initial = profile.role
        self.fields["phone_number"].initial = profile.phone_number
        self.fields["assigned_shops"].initial = profile.assigned_shops.all()
        self.fields["assigned_shops"].help_text = (
            "Assign parent enterprises. If a parent has subshops, vendors will submit entries to those child shops (not the parent)."
        )
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

        assigned_shops = cleaned_data.get("assigned_shops") or []
        if any(shop.parent_shop_id for shop in assigned_shops):
            self.add_error("assigned_shops", "Assign users to parent shops only.")
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
