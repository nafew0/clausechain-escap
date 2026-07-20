from django.urls import path

from .admin_views import (
    AdminBkashPaymentSearchView,
    AdminBkashRefundView,
    AdminDashboardView,
    AdminGateView,
    AdminPaymentsExportView,
    AdminPaymentsView,
    AdminSendPasswordResetView,
    AdminSettingsTestAIView,
    AdminSettingsView,
    AdminUserDetailView,
    AdminUsersView,
)

app_name = "admin_api"

urlpatterns = [
    path("_gate/", AdminGateView.as_view(), name="gate"),
    path("dashboard/", AdminDashboardView.as_view(), name="dashboard"),
    path("users/", AdminUsersView.as_view(), name="users"),
    path("users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="user-detail"),
    path(
        "users/<uuid:user_id>/send-password-reset/",
        AdminSendPasswordResetView.as_view(),
        name="user-send-password-reset",
    ),
    path("payments/", AdminPaymentsView.as_view(), name="payments"),
    path("payments/export/", AdminPaymentsExportView.as_view(), name="payments-export"),
    path(
        "payments/bkash/search/",
        AdminBkashPaymentSearchView.as_view(),
        name="payments-bkash-search",
    ),
    path(
        "payments/bkash/<str:payment_id>/refund/",
        AdminBkashRefundView.as_view(),
        name="payments-bkash-refund",
    ),
    path("settings/", AdminSettingsView.as_view(), name="settings"),
    path("settings/test-ai/", AdminSettingsTestAIView.as_view(), name="settings-test-ai"),
]
