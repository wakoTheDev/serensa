from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import DailyEntry, Shop, UserProfile

User = get_user_model()


class ShopForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ["name", "location", "active"]


class DailyEntryForm(forms.ModelForm):
    class Meta:
        model = DailyEntry
        fields = [
            "shop",
            "entry_date",
            "opening_stock",
            "stock_added",
            "expenses",
            "debts",
            "closing_stock",
            "cash_received",
            "notes",
        ]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["entry_date"].initial = timezone.localdate()

        if user and hasattr(user, "profile") and not user.profile.is_admin:
            self.fields["shop"].queryset = user.profile.assigned_shops.filter(active=True)


class ReportFilterForm(forms.Form):
    PERIOD_CHOICES = [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]

    period = forms.ChoiceField(choices=PERIOD_CHOICES, initial="daily")
    shop = forms.ModelChoiceField(queryset=Shop.objects.filter(active=True), required=False)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)


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
