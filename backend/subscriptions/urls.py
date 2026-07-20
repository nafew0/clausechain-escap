from django.urls import path

from .bkash_views import (
    BkashCheckoutView,
    BkashPaymentStatusView,
    bkash_callback_view,
    bkash_webhook_view,
)
from .views import CurrentSubscriptionView, PlanListView, SubscriptionUsageView
from .views import SubscriptionCancelView
from .stripe_views import (
    StripeCheckoutView,
    StripeConfigView,
    StripeCheckoutSessionStatusView,
    StripeCustomerPortalView,
    stripe_webhook_view,
)


app_name = "subscriptions"

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path(
        "subscription/", CurrentSubscriptionView.as_view(), name="subscription-detail"
    ),
    path(
        "subscription/usage/",
        SubscriptionUsageView.as_view(),
        name="subscription-usage",
    ),
    path(
        "subscription/cancel/",
        SubscriptionCancelView.as_view(),
        name="subscription-cancel",
    ),
    path("payments/stripe/config/", StripeConfigView.as_view(), name="stripe-config"),
    path(
        "payments/stripe/create-checkout/",
        StripeCheckoutView.as_view(),
        name="stripe-create-checkout",
    ),
    path(
        "payments/stripe/customer-portal/",
        StripeCustomerPortalView.as_view(),
        name="stripe-customer-portal",
    ),
    path(
        "payments/stripe/session-status/<str:session_id>/",
        StripeCheckoutSessionStatusView.as_view(),
        name="stripe-session-status",
    ),
    path("payments/stripe/webhook/", stripe_webhook_view, name="stripe-webhook"),
    path("payments/bkash/create/", BkashCheckoutView.as_view(), name="bkash-create"),
    path("payments/bkash/callback/", bkash_callback_view, name="bkash-callback"),
    path("payments/bkash/webhook/", bkash_webhook_view, name="bkash-webhook"),
    path(
        "payments/bkash/status/<str:payment_id>/",
        BkashPaymentStatusView.as_view(),
        name="bkash-status",
    ),
]
