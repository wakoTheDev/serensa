from django.contrib import admin
from django.urls import include, path

from sensa.views import UserLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", UserLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("sensa.urls")),
]
