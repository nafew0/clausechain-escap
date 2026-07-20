import uuid

from django.conf import settings
from django.db import models


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    tier = models.PositiveIntegerField(unique=True)
    max_items = models.PositiveIntegerField(default=0, help_text="Max main-entity items. 0 = unlimited.")
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stripe_price_id_monthly = models.CharField(max_length=255, blank=True, null=True)
    stripe_price_id_yearly = models.CharField(max_length=255, blank=True, null=True)
    bkash_price_monthly = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    bkash_price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="USD")
    is_active = models.BooleanField(default=True)
    features = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier"]

    def __str__(self):
        return self.name


class UserSubscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        PAST_DUE = "past_due", "Past due"
        TRIALING = "trialing", "Trialing"

    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class PaymentProvider(models.TextChoices):
        NONE = "none", "None"
        STRIPE = "stripe", "Stripe"
        BKASH = "bkash", "Bkash"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    payment_provider = models.CharField(
        max_length=20,
        choices=PaymentProvider.choices,
        default=PaymentProvider.NONE,
    )
    cancel_at_period_end = models.BooleanField(default=False)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    bkash_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"


class BkashTransaction(models.Model):
    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class RefundStatus(models.TextChoices):
        NONE = "none", "Not refunded"
        PENDING = "pending", "Refund pending"
        COMPLETED = "completed", "Refunded"
        FAILED = "failed", "Refund failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bkash_transactions",
    )
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bkash_transactions",
    )
    target_plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="bkash_transactions",
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=UserSubscription.BillingCycle.choices,
    )
    payment_id = models.CharField(max_length=255, unique=True)
    trx_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    invoice_number = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="BDT")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
    )
    refund_status = models.CharField(
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.NONE,
    )
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refund_reason = models.CharField(max_length=255, blank=True, default="")
    refund_sku = models.CharField(max_length=255, blank=True, default="")
    refund_trx_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    bkash_response = models.JSONField(default=dict, blank=True)
    refund_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.invoice_number} - {self.status}"


class SubscriptionEvent(models.Model):
    class EventType(models.TextChoices):
        BASELINE = "baseline", "Baseline"
        ADMIN_OVERRIDE = "admin_override", "Admin override"
        STRIPE_SYNC = "stripe_sync", "Stripe sync"
        STRIPE_PAST_DUE = "stripe_past_due", "Stripe past due"
        STRIPE_CANCELLED = "stripe_cancelled", "Stripe cancelled"
        BKASH_ACTIVATED = "bkash_activated", "bKash activated"
        BKASH_CANCEL_REQUESTED = "bkash_cancel_requested", "bKash cancel requested"
        BKASH_DOWNGRADED = "bkash_downgraded", "bKash downgraded"
        BKASH_REFUNDED = "bkash_refunded", "bKash refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription_events",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscription_events",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=UserSubscription.Status.choices,
        blank=True,
        default="",
    )
    payment_provider = models.CharField(
        max_length=20,
        choices=UserSubscription.PaymentProvider.choices,
        blank=True,
        default="",
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=UserSubscription.BillingCycle.choices,
        blank=True,
        default="",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["subscription", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.event_type}"
