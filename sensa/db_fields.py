from django.conf import settings
from django.db import models

if settings.DATABASES["default"]["ENGINE"] == "django_mongodb_backend":
    from django_mongodb_backend.fields import ObjectIdAutoField as BaseAutoField
else:
    BaseAutoField = models.BigAutoField


class SerensaAutoField(BaseAutoField):
    pass