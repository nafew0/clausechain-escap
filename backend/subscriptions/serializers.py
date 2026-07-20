from rest_framework import serializers

from .models import BkashTransaction, Plan, UserSubscription


class PlanSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "slug", "tier"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "slug",
            "tier",
            "max_items",
            "price_monthly",
            "price_yearly",
            "bkash_price_monthly",
            "bkash_price_yearly",
            "currency",
            "features",
            "is_active",
        ]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "plan",
            "status",
            "billing_cycle",
            "payment_provider",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "cancel_requested_at",
        ]


class StripeCheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=True)
    billing_cycle = serializers.ChoiceField(
        choices=UserSubscription.BillingCycle.choices,
        required=True,
    )


class BkashCheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=True)
    billing_cycle = serializers.ChoiceField(
        choices=UserSubscription.BillingCycle.choices,
        required=True,
    )


class BkashTransactionSerializer(serializers.ModelSerializer):
    target_plan = PlanSummarySerializer(read_only=True)

    class Meta:
        model = BkashTransaction
        fields = [
            "id",
            "payment_id",
            "trx_id",
            "invoice_number",
            "amount",
            "currency",
            "status",
            "refund_status",
            "refund_amount",
            "refund_reason",
            "refund_trx_id",
            "refund_requested_at",
            "refunded_at",
            "billing_cycle",
            "target_plan",
            "created_at",
            "updated_at",
        ]


class BkashRefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    sku = serializers.CharField(required=False, allow_blank=True, max_length=255)


class BkashSearchTransactionSerializer(serializers.Serializer):
    trx_id = serializers.CharField(required=True, max_length=255)

    def validate_trx_id(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("trx_id is required.")
        return normalized
