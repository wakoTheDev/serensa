from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User

from .models import UserProfile


class PhoneOrUsernameBackend(ModelBackend):
    """Allow authentication by username or by phone number stored on UserProfile."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_value = username or kwargs.get(User.USERNAME_FIELD)
        if not login_value or not password:
            return None

        user = None
        try:
            user = User.objects.get(username=login_value)
        except User.DoesNotExist:
            profile = UserProfile.objects.select_related("user").filter(phone_number=login_value).first()
            if profile:
                user = profile.user

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
