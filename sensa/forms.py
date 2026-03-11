from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import DailyEntry, Shop, UserProfile


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
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    assigned_shops = forms.ModelMultipleChoiceField(
        queryset=Shop.objects.filter(active=True), required=False
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data["password"]
        role = self.cleaned_data["role"]
        shops = self.cleaned_data["assigned_shops"]
        user.set_password(password)
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save()
            profile.assigned_shops.set(shops)
        return user


class UserRoleUpdateForm(forms.Form):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    assigned_shops = forms.ModelMultipleChoiceField(
        queryset=Shop.objects.filter(active=True), required=False
    )
    is_active = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        profile = kwargs.pop("profile")
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["role"].initial = profile.role
        self.fields["assigned_shops"].initial = profile.assigned_shops.all()
        self.fields["is_active"].initial = profile.user.is_active

    def save(self):
        self.profile.role = self.cleaned_data["role"]
        self.profile.save()
        self.profile.assigned_shops.set(self.cleaned_data["assigned_shops"])
        self.profile.user.is_active = self.cleaned_data["is_active"]
        self.profile.user.save()
        return self.profile
