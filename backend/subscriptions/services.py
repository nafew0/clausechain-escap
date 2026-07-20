from dataclasses import dataclass
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from accounts.models import SiteSettings

from .models import Plan, SubscriptionEvent, UserSubscription


@dataclass(frozen=True)
class LimitCheckResult:
    allowed: bool
    message: str = ""


class LicenseService:
    FREE_PLAN_SLUG = "free"
    PAID_ACTIVE_STATUSES = {
        UserSubscription.Status.ACTIVE,
        UserSubscription.Status.TRIALING,
        UserSubscription.Status.PAST_DUE,
    }
    BKASH_RENEWAL_WINDOW_DAYS = 7
    BKASH_REMINDER_WINDOW_DAYS = 3
    BKASH_GRACE_PERIOD_DAYS = 3

    @classmethod
    def serialize_subscription_state(cls, subscription):
        return {
            "plan_id": str(subscription.plan_id) if subscription.plan_id else "",
            "plan_name": subscription.plan.name if subscription.plan_id else "",
            "status": subscription.status,
            "payment_provider": subscription.payment_provider,
            "billing_cycle": subscription.billing_cycle,
            "current_period_start": (
                subscription.current_period_start.isoformat()
                if subscription.current_period_start
                else None
            ),
            "current_period_end": (
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    @classmethod
    def record_subscription_event(
        cls,
        subscription,
        event_type,
        *,
        metadata=None,
    ):
        SubscriptionEvent.objects.create(
            subscription=subscription,
            user=subscription.user,
            event_type=event_type,
            plan=subscription.plan,
            status=subscription.status,
            payment_provider=subscription.payment_provider,
            billing_cycle=subscription.billing_cycle,
            metadata=metadata or {},
        )

    @classmethod
    def get_free_plan(cls):
        free_plan = Plan.objects.filter(slug=cls.FREE_PLAN_SLUG).first()
        if not free_plan:
            raise ImproperlyConfigured("Default Free plan is missing.")
        return free_plan

    @classmethod
    def get_user_subscription(cls, user, *, for_update=False):
        queryset = UserSubscription.objects.select_related("plan")
        if for_update:
            queryset = queryset.select_for_update()

        subscription = queryset.filter(user=user).first()
        if subscription:
            return subscription

        free_plan = cls.get_free_plan()
        subscription, _ = UserSubscription.objects.get_or_create(
            user=user,
            defaults={
                "plan": free_plan,
                "status": UserSubscription.Status.ACTIVE,
                "billing_cycle": UserSubscription.BillingCycle.MONTHLY,
                "payment_provider": UserSubscription.PaymentProvider.NONE,
            },
        )
        if for_update:
            subscription = (
                UserSubscription.objects.select_related("plan")
                .select_for_update()
                .get(pk=subscription.pk)
            )
        return subscription

    @classmethod
    def get_user_plan(cls, user, *, for_update=False):
        return cls.get_user_subscription(user, for_update=for_update).plan

    @classmethod
    def get_usage_snapshot(cls, user):
        """
        Returns usage metrics for the user's current plan.
        Override or extend `get_item_count(user)` in your app to return real item counts.
        """
        plan = cls.get_user_plan(user)
        used_items = cls.get_item_count(user)
        return {
            "items": {
                "used": used_items,
                "limit": plan.max_items,
                "unlimited": plan.max_items == 0,
            },
            "plan": {
                "name": plan.name,
                "slug": plan.slug,
                "tier": plan.tier,
            },
        }

    @classmethod
    def get_item_count(cls, user):
        """
        Return the number of main-entity items owned by the user.
        Override this in your app:
            from subscriptions.services import LicenseService
            LicenseService.get_item_count = lambda cls, user: MyModel.objects.filter(user=user).count()
        """
        return 0

    @classmethod
    def check_can_create_item(cls, user, *, for_update=False):
        """Check if the user is within their plan's max_items limit."""
        plan = cls.get_user_plan(user, for_update=for_update)
        if plan.max_items == 0:
            return LimitCheckResult(True)

        item_count = cls.get_item_count(user)
        if item_count >= plan.max_items:
            return LimitCheckResult(
                False,
                f"You've reached the maximum of {plan.max_items} items on the {plan.name} plan. Upgrade to create more.",
            )

        return LimitCheckResult(True)

    @classmethod
    def get_logged_in_users_only_default(cls):
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        return site_settings.logged_in_users_only_default

    @classmethod
    def is_paid_plan(cls, plan):
        return bool(plan and plan.slug != cls.FREE_PLAN_SLUG)

    @classmethod
    def is_subscription_paid_and_active(cls, subscription):
        return (
            cls.is_paid_plan(subscription.plan)
            and subscription.status in cls.PAID_ACTIVE_STATUSES
        )

    @classmethod
    def get_bkash_amount_for_plan(cls, plan, billing_cycle):
        if billing_cycle == UserSubscription.BillingCycle.YEARLY:
            return Decimal(plan.bkash_price_yearly or 0)
        return Decimal(plan.bkash_price_monthly or 0)

    @classmethod
    def calculate_period_end(cls, start_at, billing_cycle):
        if billing_cycle == UserSubscription.BillingCycle.YEARLY:
            return start_at + relativedelta(years=1)
        return start_at + relativedelta(months=1)

    @classmethod
    def is_within_bkash_renewal_window(cls, subscription, *, reference_time=None):
        reference_time = reference_time or timezone.now()
        if not subscription.current_period_end:
            return True
        return subscription.current_period_end <= reference_time + relativedelta(
            days=cls.BKASH_RENEWAL_WINDOW_DAYS
        )

    @classmethod
    def validate_bkash_checkout_request(cls, subscription, plan, billing_cycle):
        if not plan.is_active:
            return LimitCheckResult(False, "This plan is no longer available.")
        if plan.slug == cls.FREE_PLAN_SLUG:
            return LimitCheckResult(
                False, "The Free plan does not require bKash checkout."
            )

        amount = cls.get_bkash_amount_for_plan(plan, billing_cycle)
        if amount <= 0:
            return LimitCheckResult(
                False,
                f"The BDT price for the {plan.name} {billing_cycle} plan is not configured yet.",
            )

        if not cls.is_subscription_paid_and_active(subscription):
            return LimitCheckResult(True)

        if subscription.payment_provider == UserSubscription.PaymentProvider.STRIPE:
            return LimitCheckResult(
                False,
                "Your account already has an active Stripe subscription. Use Manage Billing to change plans or wait for it to end before switching to bKash.",
            )

        if subscription.payment_provider == UserSubscription.PaymentProvider.BKASH:
            same_plan = subscription.plan_id == plan.id
            same_cycle = subscription.billing_cycle == billing_cycle
            if same_plan and same_cycle:
                if cls.is_within_bkash_renewal_window(subscription):
                    return LimitCheckResult(True)
                return LimitCheckResult(
                    False,
                    f"bKash renewal becomes available within {cls.BKASH_RENEWAL_WINDOW_DAYS} days of your renewal date.",
                )

            return LimitCheckResult(
                False,
                "Your current bKash plan stays active until the end of the billing term. Change plans after it expires or renew the same plan now.",
            )

        return LimitCheckResult(
            False,
            "Your account already has an active paid plan. Update it in billing or Django admin before creating a new bKash checkout session.",
        )

    @classmethod
    def activate_bkash_subscription(
        cls,
        subscription,
        *,
        plan,
        billing_cycle,
        activated_at=None,
        event_metadata=None,
    ):
        activated_at = activated_at or timezone.now()
        next_period_start = activated_at

        if (
            subscription.payment_provider == UserSubscription.PaymentProvider.BKASH
            and subscription.plan_id == plan.id
            and subscription.billing_cycle == billing_cycle
            and subscription.current_period_end
            and subscription.current_period_end > activated_at
        ):
            next_period_start = subscription.current_period_end

        subscription.plan = plan
        subscription.status = UserSubscription.Status.ACTIVE
        subscription.payment_provider = UserSubscription.PaymentProvider.BKASH
        subscription.billing_cycle = billing_cycle
        subscription.current_period_start = activated_at
        subscription.current_period_end = cls.calculate_period_end(
            next_period_start,
            billing_cycle,
        )
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None
        subscription.save(
            update_fields=[
                "plan",
                "status",
                "payment_provider",
                "billing_cycle",
                "current_period_start",
                "current_period_end",
                "cancel_at_period_end",
                "cancel_requested_at",
                "updated_at",
            ]
        )
        cls.record_subscription_event(
            subscription,
            SubscriptionEvent.EventType.BKASH_ACTIVATED,
            metadata=event_metadata or {},
        )
        return subscription

    @classmethod
    def cancel_bkash_subscription_at_period_end(cls, subscription):
        subscription.cancel_at_period_end = True
        subscription.cancel_requested_at = timezone.now()
        subscription.save(
            update_fields=[
                "cancel_at_period_end",
                "cancel_requested_at",
                "updated_at",
            ]
        )
        cls.record_subscription_event(
            subscription,
            SubscriptionEvent.EventType.BKASH_CANCEL_REQUESTED,
            metadata={"cancel_requested_at": subscription.cancel_requested_at.isoformat()},
        )
        return subscription

    @classmethod
    def downgrade_to_free(
        cls,
        subscription,
        *,
        status=UserSubscription.Status.CANCELLED,
        event_type=SubscriptionEvent.EventType.BKASH_DOWNGRADED,
        event_metadata=None,
    ):
        free_plan = cls.get_free_plan()
        subscription.plan = free_plan
        subscription.status = status
        subscription.payment_provider = UserSubscription.PaymentProvider.NONE
        subscription.billing_cycle = UserSubscription.BillingCycle.MONTHLY
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None
        subscription.current_period_start = None
        subscription.current_period_end = None
        subscription.save(
            update_fields=[
                "plan",
                "status",
                "payment_provider",
                "billing_cycle",
                "cancel_at_period_end",
                "cancel_requested_at",
                "current_period_start",
                "current_period_end",
                "updated_at",
            ]
        )
        cls.record_subscription_event(
            subscription,
            event_type,
            metadata=event_metadata or {},
        )
        return subscription
