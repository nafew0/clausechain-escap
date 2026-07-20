"""
Subscription app tests.

Add your tests here. The LicenseService, Plan, and UserSubscription models
are tested via integration — create a real PostgreSQL test database.
"""
from django.test import TestCase


class SubscriptionsSmoke(TestCase):
    """Verify the subscriptions app can be imported without errors."""

    def test_models_importable(self):
        from subscriptions.models import BkashTransaction, Plan, SubscriptionEvent, UserSubscription  # noqa: F401

    def test_services_importable(self):
        from subscriptions.services import LicenseService  # noqa: F401

    def test_admin_services_importable(self):
        from subscriptions.admin_services import AdminPaymentsService  # noqa: F401
