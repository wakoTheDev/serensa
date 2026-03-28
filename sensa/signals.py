from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import IntegrityError

from .models import UserProfile


User = get_user_model()


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when a User is created.
    
    This signal ensures every user has a profile. When called during admin bootstrap,
    the profile will be updated afterwards by the form with the correct role/phone_number.
    """
    if created:
        # Check if profile already exists (defensive check for race conditions)
        if not UserProfile.objects.filter(user=instance).exists():
            try:
                UserProfile.objects.create(user=instance)
            except IntegrityError:
                # In rare cases of race conditions, the profile might have been created
                # by another process between the exists() check and create(). This is fine.
                pass
    else:
        # For user updates (not creation), ensure profile exists
        UserProfile.objects.get_or_create(user=instance)
