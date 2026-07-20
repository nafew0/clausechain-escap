import logging
from datetime import datetime, timezone as dt_timezone

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from .models import Plan, SubscriptionEvent, UserSubscription
from .services import LicenseService

logger = logging.getLogger(__name__)
User = get_user_model()


class StripeConfigurationError(Exception):
    pass


class StripeServiceError(Exception):
    pass


class StripeUserInputError(StripeServiceError):
    pass


class StripeCheckoutConflictError(StripeServiceError):
    def __init__(self, message, *, requires_customer_portal=False):
        super().__init__(message)
        self.requires_customer_portal = requires_customer_portal


class StripeWebhookSignatureError(StripeServiceError):
    pass


class StripeService:
    @classmethod
    def _configure(cls):
        stripe.api_key = settings.STRIPE_SECRET_KEY

    @classmethod
    def _require_configuration(cls, *, require_webhook=False):
        missing = []
        if not settings.STRIPE_SECRET_KEY:
            missing.append("STRIPE_SECRET_KEY")
        if not settings.PUBLIC_APP_URL:
            missing.append("PUBLIC_APP_URL")
        if require_webhook and not settings.STRIPE_WEBHOOK_SECRET:
            missing.append("STRIPE_WEBHOOK_SECRET")

        if missing:
            raise StripeConfigurationError(
                "Stripe payments are not fully configured. Missing: "
                + ", ".join(missing)
            )

        cls._configure()

    @classmethod
    def _build_app_url(cls, path):
        base_url = (settings.PUBLIC_APP_URL or "").rstrip("/")
        if not base_url:
            raise StripeConfigurationError("PUBLIC_APP_URL must be configured.")
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{base_url}{normalized_path}"

    @staticmethod
    def _value(data, key, default=None):
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)

    @classmethod
    def _metadata_value(cls, data, key, default=None):
        metadata = cls._value(data, "metadata", {}) or {}
        return cls._value(metadata, key, default)

    @classmethod
    def _timestamp_to_datetime(cls, timestamp):
        if not timestamp:
            return None
        return datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)

    @classmethod
    def _map_subscription_status(cls, stripe_status):
        normalized = (stripe_status or "").strip().lower()
        if normalized == "active":
            return UserSubscription.Status.ACTIVE
        if normalized == "trialing":
            return UserSubscription.Status.TRIALING
        if normalized in {"canceled", "cancelled", "paused"}:
            return UserSubscription.Status.CANCELLED
        return UserSubscription.Status.PAST_DUE

    @classmethod
    def _get_plan_for_price_id(cls, price_id):
        if not price_id:
            raise StripeConfigurationError("Stripe subscription is missing a price ID.")

        plan = Plan.objects.filter(
            Q(stripe_price_id_monthly=price_id) | Q(stripe_price_id_yearly=price_id)
        ).first()
        if not plan:
            raise StripeConfigurationError(
                "No reactdjango plan is mapped to the Stripe price."
            )

        if plan.stripe_price_id_yearly == price_id:
            billing_cycle = UserSubscription.BillingCycle.YEARLY
        else:
            billing_cycle = UserSubscription.BillingCycle.MONTHLY

        return plan, billing_cycle

    @classmethod
    def _get_price_id_for_plan(cls, plan, billing_cycle):
        if billing_cycle == UserSubscription.BillingCycle.YEARLY:
            price_id = plan.stripe_price_id_yearly
        else:
            price_id = plan.stripe_price_id_monthly

        if not price_id:
            raise StripeConfigurationError(
                f"Stripe price ID is not configured for the {plan.name} {billing_cycle} plan."
            )

        return price_id

    @classmethod
    def _extract_subscription_price_id(cls, stripe_subscription):
        items = cls._value(stripe_subscription, "items", {}) or {}
        data = cls._value(items, "data", []) or []
        if not data:
            raise StripeConfigurationError("Stripe subscription has no line items.")

        price = cls._value(data[0], "price", {}) or {}
        price_id = cls._value(price, "id")
        if not price_id:
            raise StripeConfigurationError(
                "Stripe subscription line item has no price ID."
            )
        return price_id

    @classmethod
    def _resolve_local_subscription(
        cls,
        *,
        stripe_customer_id=None,
        stripe_subscription_id=None,
        user=None,
        user_id=None,
    ):
        queryset = UserSubscription.objects.select_related("user", "plan")

        if stripe_subscription_id:
            local_subscription = queryset.filter(
                stripe_subscription_id=stripe_subscription_id
            ).first()
            if local_subscription:
                return local_subscription

        if stripe_customer_id:
            local_subscription = queryset.filter(
                stripe_customer_id=stripe_customer_id
            ).first()
            if local_subscription:
                return local_subscription

        resolved_user = user
        if resolved_user is None and user_id:
            resolved_user = User.objects.filter(pk=user_id, is_active=True).first()

        if resolved_user is not None:
            return LicenseService.get_user_subscription(resolved_user)

        raise StripeServiceError(
            "Unable to match the Stripe event to a local reactdjango subscription."
        )

    @classmethod
    def _ensure_customer(cls, user, subscription):
        if subscription.stripe_customer_id:
            try:
                stripe.Customer.modify(
                    subscription.stripe_customer_id,
                    email=user.email,
                    name=user.full_name or user.username,
                    metadata={"user_id": str(user.id)},
                )
            except stripe.error.StripeError as exc:
                raise StripeServiceError(
                    "Stripe could not update the existing customer record."
                ) from exc
            return subscription.stripe_customer_id

        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.full_name or user.username,
                metadata={"user_id": str(user.id)},
            )
        except stripe.error.StripeError as exc:
            raise StripeServiceError(
                "Stripe could not create a customer for this account."
            ) from exc

        subscription.stripe_customer_id = cls._value(customer, "id")
        subscription.save(update_fields=["stripe_customer_id", "updated_at"])
        return subscription.stripe_customer_id

    @classmethod
    def create_checkout_session(cls, user, plan, billing_cycle):
        cls._require_configuration(require_webhook=True)

        if not plan.is_active:
            raise StripeUserInputError("This plan is no longer available.")
        if plan.slug == LicenseService.FREE_PLAN_SLUG:
            raise StripeUserInputError(
                "The Free plan does not require Stripe checkout."
            )

        with transaction.atomic():
            subscription = LicenseService.get_user_subscription(user, for_update=True)
            if (
                subscription.plan_id == plan.id
                and subscription.payment_provider
                == UserSubscription.PaymentProvider.STRIPE
                and subscription.status
                in {
                    UserSubscription.Status.ACTIVE,
                    UserSubscription.Status.TRIALING,
                    UserSubscription.Status.PAST_DUE,
                }
                and subscription.billing_cycle == billing_cycle
            ):
                raise StripeCheckoutConflictError(
                    "You are already on this Stripe plan and billing cycle.",
                    requires_customer_portal=True,
                )

            if (
                subscription.plan.slug != LicenseService.FREE_PLAN_SLUG
                and subscription.status
                in {
                    UserSubscription.Status.ACTIVE,
                    UserSubscription.Status.TRIALING,
                    UserSubscription.Status.PAST_DUE,
                }
            ):
                if (
                    subscription.payment_provider
                    == UserSubscription.PaymentProvider.STRIPE
                    and subscription.stripe_customer_id
                ):
                    raise StripeCheckoutConflictError(
                        "You already have an active Stripe subscription. Use Manage Billing to change plans or billing cycle.",
                        requires_customer_portal=True,
                    )
                raise StripeCheckoutConflictError(
                    "Your account already has an active paid plan. Update it in billing or Django admin before creating a new Stripe checkout session."
                )

            stripe_customer_id = cls._ensure_customer(user, subscription)
            price_id = cls._get_price_id_for_plan(plan, billing_cycle)

            try:
                session = stripe.checkout.Session.create(
                    mode="subscription",
                    customer=stripe_customer_id,
                    client_reference_id=str(user.id),
                    line_items=[{"price": price_id, "quantity": 1}],
                    allow_promotion_codes=True,
                    success_url=cls._build_app_url(
                        "/payment/success?provider=stripe&session_id={CHECKOUT_SESSION_ID}"
                    ),
                    cancel_url=cls._build_app_url("/pricing?canceled=true"),
                    metadata={
                        "user_id": str(user.id),
                        "plan_id": str(plan.id),
                        "billing_cycle": billing_cycle,
                    },
                    subscription_data={
                        "metadata": {
                            "user_id": str(user.id),
                            "plan_id": str(plan.id),
                            "billing_cycle": billing_cycle,
                        }
                    },
                )
            except stripe.error.StripeError as exc:
                raise StripeServiceError(
                    "Stripe could not create a checkout session."
                ) from exc

        session_url = cls._value(session, "url")
        if not session_url:
            raise StripeServiceError("Stripe did not return a checkout URL.")
        return session_url

    @classmethod
    def create_customer_portal_session(cls, user):
        cls._require_configuration()

        subscription = LicenseService.get_user_subscription(user)
        if not subscription.stripe_customer_id:
            raise StripeUserInputError(
                "No Stripe billing profile exists for this account yet."
            )

        try:
            session = stripe.billing_portal.Session.create(
                customer=subscription.stripe_customer_id,
                return_url=cls._build_app_url("/profile"),
            )
        except stripe.error.StripeError as exc:
            raise StripeServiceError(
                "Stripe could not create a billing portal session."
            ) from exc

        portal_url = cls._value(session, "url")
        if not portal_url:
            raise StripeServiceError("Stripe did not return a billing portal URL.")
        return portal_url

    @classmethod
    def _sync_subscription_from_stripe(cls, stripe_subscription, *, user_id=None):
        stripe_customer_id = cls._value(stripe_subscription, "customer")
        stripe_subscription_id = cls._value(stripe_subscription, "id")
        local_subscription = cls._resolve_local_subscription(
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            user_id=user_id or cls._metadata_value(stripe_subscription, "user_id"),
        )
        price_id = cls._extract_subscription_price_id(stripe_subscription)
        plan, billing_cycle = cls._get_plan_for_price_id(price_id)

        previous_state = LicenseService.serialize_subscription_state(local_subscription)
        local_subscription.plan = plan
        local_subscription.status = cls._map_subscription_status(
            cls._value(stripe_subscription, "status")
        )
        local_subscription.billing_cycle = billing_cycle
        local_subscription.payment_provider = UserSubscription.PaymentProvider.STRIPE
        local_subscription.stripe_customer_id = (
            stripe_customer_id or local_subscription.stripe_customer_id
        )
        local_subscription.stripe_subscription_id = (
            stripe_subscription_id or local_subscription.stripe_subscription_id
        )
        local_subscription.current_period_start = cls._timestamp_to_datetime(
            cls._value(stripe_subscription, "current_period_start")
        )
        local_subscription.current_period_end = cls._timestamp_to_datetime(
            cls._value(stripe_subscription, "current_period_end")
        )
        local_subscription.cancel_at_period_end = False
        local_subscription.cancel_requested_at = None
        local_subscription.save()
        LicenseService.record_subscription_event(
            local_subscription,
            SubscriptionEvent.EventType.STRIPE_SYNC,
            metadata={"previous_state": previous_state},
        )
        return local_subscription

    @classmethod
    def _mark_past_due(cls, *, stripe_customer_id=None, stripe_subscription_id=None):
        local_subscription = cls._resolve_local_subscription(
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        previous_state = LicenseService.serialize_subscription_state(local_subscription)
        local_subscription.status = UserSubscription.Status.PAST_DUE
        local_subscription.payment_provider = UserSubscription.PaymentProvider.STRIPE
        if stripe_subscription_id:
            local_subscription.stripe_subscription_id = stripe_subscription_id
        if stripe_customer_id:
            local_subscription.stripe_customer_id = stripe_customer_id
        local_subscription.save(
            update_fields=[
                "status",
                "payment_provider",
                "stripe_subscription_id",
                "stripe_customer_id",
                "updated_at",
            ]
        )
        LicenseService.record_subscription_event(
            local_subscription,
            SubscriptionEvent.EventType.STRIPE_PAST_DUE,
            metadata={"previous_state": previous_state},
        )
        return local_subscription

    @classmethod
    def _downgrade_to_free(
        cls,
        *,
        stripe_customer_id=None,
        stripe_subscription_id=None,
        user_id=None,
    ):
        local_subscription = cls._resolve_local_subscription(
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            user_id=user_id,
        )
        previous_state = LicenseService.serialize_subscription_state(local_subscription)
        free_plan = LicenseService.get_free_plan()
        local_subscription.plan = free_plan
        local_subscription.status = UserSubscription.Status.ACTIVE
        local_subscription.billing_cycle = UserSubscription.BillingCycle.MONTHLY
        local_subscription.payment_provider = UserSubscription.PaymentProvider.NONE
        if stripe_customer_id:
            local_subscription.stripe_customer_id = stripe_customer_id
        local_subscription.stripe_subscription_id = None
        local_subscription.cancel_at_period_end = False
        local_subscription.cancel_requested_at = None
        local_subscription.current_period_start = None
        local_subscription.current_period_end = None
        local_subscription.save()
        LicenseService.record_subscription_event(
            local_subscription,
            SubscriptionEvent.EventType.STRIPE_CANCELLED,
            metadata={"previous_state": previous_state},
        )
        return local_subscription

    @classmethod
    def sync_checkout_session(cls, user, session_id):
        cls._require_configuration()

        normalized_session_id = (session_id or "").strip()
        if not normalized_session_id:
            raise StripeUserInputError("Stripe checkout session ID is required.")

        try:
            checkout_session = stripe.checkout.Session.retrieve(
                normalized_session_id,
                expand=["subscription"],
            )
        except stripe.error.StripeError as exc:
            raise StripeServiceError(
                "Stripe could not retrieve the checkout session."
            ) from exc

        if cls._value(checkout_session, "mode") != "subscription":
            raise StripeUserInputError(
                "This Stripe checkout session is not a subscription checkout."
            )

        session_user_id = str(
            cls._metadata_value(checkout_session, "user_id")
            or cls._value(checkout_session, "client_reference_id")
            or ""
        ).strip()
        if session_user_id and session_user_id != str(user.id):
            raise StripeUserInputError(
                "This Stripe checkout session does not belong to the current account."
            )

        local_subscription = LicenseService.get_user_subscription(user)
        stripe_customer_id = cls._value(checkout_session, "customer")
        if (
            local_subscription.stripe_customer_id
            and stripe_customer_id
            and local_subscription.stripe_customer_id != stripe_customer_id
        ):
            raise StripeUserInputError(
                "This Stripe checkout session does not belong to the current account."
            )

        session_status = str(cls._value(checkout_session, "status") or "").strip().lower()
        payment_status = str(
            cls._value(checkout_session, "payment_status") or ""
        ).strip().lower()
        if session_status not in {"complete", "completed"} or payment_status not in {
            "paid",
            "no_payment_required",
        }:
            return {
                "completed": False,
                "session_status": session_status,
                "payment_status": payment_status,
                "subscription": local_subscription,
            }

        stripe_subscription = cls._value(checkout_session, "subscription")
        if not stripe_subscription:
            raise StripeServiceError(
                "Stripe checkout completion did not include a subscription."
            )

        if isinstance(stripe_subscription, str):
            try:
                stripe_subscription = stripe.Subscription.retrieve(stripe_subscription)
            except stripe.error.StripeError as exc:
                raise StripeServiceError(
                    "Stripe could not retrieve the subscription for this checkout session."
                ) from exc

        synchronized_subscription = cls._sync_subscription_from_stripe(
            stripe_subscription,
            user_id=str(user.id),
        )
        return {
            "completed": LicenseService.is_subscription_paid_and_active(
                synchronized_subscription
            ),
            "session_status": session_status,
            "payment_status": payment_status,
            "subscription": synchronized_subscription,
        }

    @classmethod
    def handle_webhook(cls, payload, sig_header):
        cls._require_configuration(require_webhook=True)

        if not sig_header:
            raise StripeWebhookSignatureError("Missing Stripe signature header.")

        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except ValueError as exc:
            raise StripeWebhookSignatureError(
                "Invalid Stripe webhook payload."
            ) from exc
        except stripe.error.SignatureVerificationError as exc:
            raise StripeWebhookSignatureError(
                "Invalid Stripe webhook signature."
            ) from exc

        event_type = cls._value(event, "type")
        event_data = cls._value(cls._value(event, "data", {}), "object", {})

        with transaction.atomic():
            if event_type == "checkout.session.completed":
                if cls._value(event_data, "mode") != "subscription":
                    return event_type

                stripe_subscription_id = cls._value(event_data, "subscription")
                if not stripe_subscription_id:
                    raise StripeServiceError(
                        "Stripe checkout completion did not include a subscription ID."
                    )

                try:
                    stripe_subscription = stripe.Subscription.retrieve(
                        stripe_subscription_id
                    )
                except stripe.error.StripeError as exc:
                    raise StripeServiceError(
                        "Stripe could not retrieve the completed subscription."
                    ) from exc

                cls._sync_subscription_from_stripe(
                    stripe_subscription,
                    user_id=cls._metadata_value(event_data, "user_id"),
                )
                return event_type

            if event_type == "customer.subscription.updated":
                cls._sync_subscription_from_stripe(event_data)
                return event_type

            if event_type == "invoice.paid":
                stripe_subscription_id = cls._value(event_data, "subscription")
                if not stripe_subscription_id:
                    return event_type

                try:
                    stripe_subscription = stripe.Subscription.retrieve(
                        stripe_subscription_id
                    )
                except stripe.error.StripeError as exc:
                    raise StripeServiceError(
                        "Stripe could not retrieve the paid subscription."
                    ) from exc

                cls._sync_subscription_from_stripe(stripe_subscription)
                return event_type

            if event_type == "invoice.payment_failed":
                cls._mark_past_due(
                    stripe_customer_id=cls._value(event_data, "customer"),
                    stripe_subscription_id=cls._value(event_data, "subscription"),
                )
                return event_type

            if event_type == "customer.subscription.deleted":
                cls._downgrade_to_free(
                    stripe_customer_id=cls._value(event_data, "customer"),
                    stripe_subscription_id=cls._value(event_data, "id"),
                    user_id=cls._metadata_value(event_data, "user_id"),
                )
                return event_type

        logger.info("Ignoring unsupported Stripe event type: %s", event_type)
        return event_type
