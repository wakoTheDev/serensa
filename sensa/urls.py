from django.urls import path

from . import views

urlpatterns = [
    path("setup-admin/", views.bootstrap_admin, name="setup_admin"),
    path("", views.dashboard_redirect, name="dashboard"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("vendor-dashboard/", views.vendor_dashboard, name="vendor_dashboard"),
    path("entries/new/", views.entry_create_or_update, name="entry_create_or_update"),
    path("shops/", views.shop_list, name="shop_list"),
    path("shops/new/", views.shop_create, name="shop_create"),
    path("shops/<str:pk>/edit/", views.shop_edit, name="shop_edit"),
    path("shops/<str:pk>/delete/", views.shop_delete, name="shop_delete"),
    path("reports/", views.report_view, name="report_view"),
    path("reports/fetch-balance/", views.fetch_balance, name="fetch_balance"),
    path("reports/export/excel/", views.export_report_excel, name="export_report_excel"),
    path("reports/export/pdf/", views.export_report_pdf, name="export_report_pdf"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<str:user_id>/edit/", views.user_edit_role, name="user_edit_role"),
    path("users/<str:user_id>/remove-vendor/", views.vendor_remove, name="vendor_remove"),
]
