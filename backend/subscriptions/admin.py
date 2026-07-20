from django.contrib import admin

from .models import BkashTransaction, Plan, SubscriptionEvent, UserSubscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "tier",
        "max_items",
        "price_monthly",
        "price_yearly",
        "is_active",
    ]
    list_filter = ["is_active", "currency", "tier"]
    search_fields = ["name", "slug"]
    ordering = ["tier"]


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "plan",
        "status",
        "billing_cycle",
        "payment_provider",
        "cancel_at_period_end",
        "current_period_end",
        "updated_at",
    ]
    list_filter = [
        "status",
        "billing_cycle",
        "payment_provider",
        "cancel_at_period_end",
        "plan",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "stripe_customer_id",
        "stripe_subscription_id",
    ]
    autocomplete_fields = ["user", "plan"]


@admin.register(BkashTransaction)
class BkashTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "user",
        "target_plan",
        "billing_cycle",
        "amount",
        "currency",
        "status",
        "payment_id",
        "trx_id",
        "updated_at",
    ]
    list_filter = ["status", "billing_cycle", "currency", "target_plan"]
    search_fields = [
        "invoice_number",
        "payment_id",
        "trx_id",
        "user__username",
        "user__email",
    ]
    autocomplete_fields = ["user", "subscription", "target_plan"]
    readonly_fields = [
        "user",
        "subscription",
        "target_plan",
        "billing_cycle",
        "payment_id",
        "trx_id",
        "invoice_number",
        "amount",
        "currency",
        "status",
        "bkash_response",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "event_type",
        "plan",
        "status",
        "payment_provider",
        "billing_cycle",
        "created_at",
    ]
    list_filter = ["event_type", "status", "payment_provider", "billing_cycle"]
    search_fields = ["user__username", "user__email"]
    autocomplete_fields = ["subscription", "user", "plan"]
    readonly_fields = [
        "subscription",
        "user",
        "event_type",
        "plan",
        "status",
        "payment_provider",
        "billing_cycle",
        "metadata",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False
