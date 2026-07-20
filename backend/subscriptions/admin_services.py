from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import stripe
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from accounts.models import User

from .models import BkashTransaction, Plan, UserSubscription
from .services import LicenseService
from .stripe_service import StripeService


@dataclass
class StripePaymentsResult:
    payments: list
    warnings: list


class AdminPaymentsService:
    STRIPE_CACHE_TIMEOUT_SECONDS = 300
    STRIPE_MAX_INVOICES = 1000

    @classmethod
    def _format_month_label(cls, dt_value):
        return timezone.localtime(dt_value).strftime("%b %Y")

    @classmethod
    def _month_start(cls, dt_value):
        localized = timezone.localtime(dt_value)
        return localized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def _iso_to_datetime(cls, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    @classmethod
    def _timestamp_to_datetime(cls, value):
        if not value:
            return None
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)

    @classmethod
    def _get_plan_by_price_id(cls, price_id):
        if not price_id:
            return None, ""
        try:
            return StripeService._get_plan_for_price_id(price_id)
        except Exception:
            return None, ""

    @classmethod
    def _resolve_user_lookup(cls):
        subscriptions = (
            UserSubscription.objects.select_related("user", "plan")
            .exclude(stripe_customer_id__isnull=True)
            .exclude(stripe_customer_id="")
        )
        customer_lookup = {}
        subscription_lookup = {}
        for subscription in subscriptions:
            customer_lookup[subscription.stripe_customer_id] = subscription.user
            if subscription.stripe_subscription_id:
                subscription_lookup[subscription.stripe_subscription_id] = (
                    subscription.user
                )
        return customer_lookup, subscription_lookup

    @classmethod
    def _build_stripe_cache_key(cls, *, date_from, date_to):
        start = date_from.isoformat() if date_from else "none"
        end = date_to.isoformat() if date_to else "none"
        return f"admin:stripe:invoices:{start}:{end}"

    @classmethod
    def _normalize_stripe_status(cls, invoice):
        if StripeService._value(invoice, "paid"):
            return "paid"
        return (StripeService._value(invoice, "status") or "unknown").strip().lower()

    @classmethod
    def _normalize_stripe_invoice(cls, invoice, customer_lookup, subscription_lookup):
        customer_id = StripeService._value(invoice, "customer")
        subscription_id = StripeService._value(invoice, "subscription")
        user = subscription_lookup.get(subscription_id) or customer_lookup.get(customer_id)

        lines = StripeService._value(invoice, "lines", {}) or {}
        line_items = StripeService._value(lines, "data", []) or []
        price_id = ""
        description = StripeService._value(invoice, "description") or "Stripe invoice"
        if line_items:
            first_line = line_items[0] or {}
            price = StripeService._value(first_line, "price", {}) or {}
            price_id = StripeService._value(price, "id") or ""
            description = (
                StripeService._value(first_line, "description")
                or description
            )

        plan, billing_cycle = cls._get_plan_by_price_id(price_id)
        created_at = cls._timestamp_to_datetime(StripeService._value(invoice, "created"))
        amount_paid = Decimal(StripeService._value(invoice, "amount_paid", 0) or 0) / Decimal("100")
        currency = (StripeService._value(invoice, "currency") or "usd").upper()
        status = cls._normalize_stripe_status(invoice)

        return {
            "id": StripeService._value(invoice, "id"),
            "provider": "stripe",
            "provider_reference": StripeService._value(invoice, "id"),
            "invoice_number": StripeService._value(invoice, "number") or "",
            "trx_id": "",
            "status": status,
            "amount": str(amount_paid),
            "currency": currency,
            "created_at": created_at.isoformat() if created_at else None,
            "description": description,
            "billing_cycle": billing_cycle,
            "user": {
                "id": str(user.id) if user else "",
                "username": user.username if user else "",
                "email": user.email if user else (StripeService._value(invoice, "customer_email") or ""),
            },
            "plan": {
                "id": str(plan.id) if plan else "",
                "name": plan.name if plan else "",
                "slug": plan.slug if plan else "",
            },
            "revenue_amount": float(amount_paid if status == "paid" else Decimal("0")),
        }

    @classmethod
    def fetch_stripe_payments(cls, *, date_from=None, date_to=None):
        if not settings.STRIPE_SECRET_KEY:
            return StripePaymentsResult(
                payments=[],
                warnings=["Stripe is not configured in this environment."],
            )

        cache_key = cls._build_stripe_cache_key(date_from=date_from, date_to=date_to)
        cached = cache.get(cache_key)
        if cached is not None:
            return StripePaymentsResult(payments=cached, warnings=[])

        stripe.api_key = settings.STRIPE_SECRET_KEY
        list_kwargs = {"limit": 100, "expand": ["data.lines.data.price"]}
        created_filter = {}
        if date_from:
            created_filter["gte"] = int(date_from.timestamp())
        if date_to:
            created_filter["lte"] = int(date_to.timestamp())
        if created_filter:
            list_kwargs["created"] = created_filter

        customer_lookup, subscription_lookup = cls._resolve_user_lookup()
        normalized = []

        try:
            invoices = stripe.Invoice.list(**list_kwargs)
            for index, invoice in enumerate(invoices.auto_paging_iter()):
                if index >= cls.STRIPE_MAX_INVOICES:
                    break
                normalized.append(
                    cls._normalize_stripe_invoice(
                        invoice,
                        customer_lookup,
                        subscription_lookup,
                    )
                )
        except Exception:
            return StripePaymentsResult(
                payments=[],
                warnings=["Stripe payment history is temporarily unavailable."],
            )

        try:
            cache.set(cache_key, normalized, cls.STRIPE_CACHE_TIMEOUT_SECONDS)
        except Exception:
            pass

        return StripePaymentsResult(payments=normalized, warnings=[])

    @classmethod
    def fetch_bkash_payments(cls, *, date_from=None, date_to=None):
        queryset = BkashTransaction.objects.select_related("user", "target_plan")
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        payments = []
        for transaction in queryset:
            payments.append(cls.serialize_bkash_payment(transaction))
        return payments

    @classmethod
    def serialize_bkash_payment(cls, transaction):
        amount = Decimal(transaction.amount or 0)
        refunded_amount = Decimal(transaction.refund_amount or 0)
        net_revenue_amount = amount
        if transaction.refund_status == BkashTransaction.RefundStatus.COMPLETED:
            net_revenue_amount = max(Decimal("0"), amount - refunded_amount)
        refundable = (
            transaction.status == BkashTransaction.Status.COMPLETED
            and transaction.refund_status == BkashTransaction.RefundStatus.NONE
            and amount > 0
        )
        return {
            "id": str(transaction.id),
            "provider": "bkash",
            "provider_reference": transaction.payment_id,
            "invoice_number": transaction.invoice_number,
            "trx_id": transaction.trx_id or "",
            "status": transaction.status,
            "amount": str(amount),
            "currency": transaction.currency,
            "created_at": transaction.created_at.isoformat(),
            "description": f"bKash {transaction.target_plan.name} plan",
            "billing_cycle": transaction.billing_cycle,
            "user": {
                "id": str(transaction.user_id),
                "username": transaction.user.username,
                "email": transaction.user.email,
            },
            "plan": {
                "id": str(transaction.target_plan_id),
                "name": transaction.target_plan.name,
                "slug": transaction.target_plan.slug,
            },
            "refund_status": transaction.refund_status,
            "refund_amount": str(refunded_amount),
            "refund_reason": transaction.refund_reason,
            "refund_trx_id": transaction.refund_trx_id or "",
            "refundable": refundable,
            "available_refund_amount": str(
                amount - refunded_amount if refundable else Decimal("0")
            ),
            "revenue_amount": float(
                net_revenue_amount
                if transaction.status == BkashTransaction.Status.COMPLETED
                else Decimal("0")
            ),
        }

    @classmethod
    def _matches_search(cls, payment, search):
        haystack = " ".join(
            [
                payment.get("provider_reference", ""),
                payment.get("invoice_number", ""),
                payment.get("trx_id", ""),
                payment.get("description", ""),
                payment.get("user", {}).get("username", ""),
                payment.get("user", {}).get("email", ""),
                payment.get("plan", {}).get("name", ""),
            ]
        ).lower()
        return search.lower() in haystack

    @classmethod
    def list_payments(
        cls,
        *,
        provider="",
        status="",
        user_id="",
        date_from=None,
        date_to=None,
        search="",
        ordering="-created_at",
    ):
        warnings = []
        payments = []

        if provider in {"", "stripe"}:
            stripe_result = cls.fetch_stripe_payments(date_from=date_from, date_to=date_to)
            payments.extend(stripe_result.payments)
            warnings.extend(stripe_result.warnings)

        if provider in {"", "bkash"}:
            payments.extend(cls.fetch_bkash_payments(date_from=date_from, date_to=date_to))

        if provider:
            payments = [payment for payment in payments if payment["provider"] == provider]
        if status:
            payments = [payment for payment in payments if payment["status"] == status]
        if user_id:
            payments = [
                payment
                for payment in payments
                if payment.get("user", {}).get("id") == str(user_id)
            ]
        if search:
            payments = [
                payment for payment in payments if cls._matches_search(payment, search)
            ]

        reverse = ordering.startswith("-")
        ordering_key = ordering.lstrip("-")
        sort_map = {
            "created_at": lambda item: item.get("created_at") or "",
            "amount": lambda item: Decimal(item.get("amount") or "0"),
            "status": lambda item: item.get("status") or "",
            "provider": lambda item: item.get("provider") or "",
        }
        payments.sort(key=sort_map.get(ordering_key, sort_map["created_at"]), reverse=reverse)

        revenue_totals = defaultdict(lambda: Decimal("0"))
        for payment in payments:
            revenue_amount = Decimal(str(payment.get("revenue_amount", 0)))
            if revenue_amount <= 0:
                continue
            revenue_totals[payment.get("currency") or "USD"] += revenue_amount

        return {
            "payments": payments,
            "warnings": list(dict.fromkeys(warnings)),
            "revenue_totals": {
                currency: str(total.quantize(Decimal("0.01")))
                for currency, total in revenue_totals.items()
            },
        }

    @classmethod
    def build_dashboard_payload(cls):
        now = timezone.now()
        range_start = now - timedelta(days=180)
        payment_data = cls.list_payments(date_from=range_start)
        payments = payment_data["payments"]

        total_users = User.objects.count()
        active_subscriptions = UserSubscription.objects.exclude(
            plan__slug=LicenseService.FREE_PLAN_SLUG
        ).filter(status__in=list(LicenseService.PAID_ACTIVE_STATUSES)).count()
        monthly_revenue_totals = defaultdict(lambda: Decimal("0"))
        for payment in payments:
            if not payment.get("created_at", "").startswith(now.strftime("%Y-%m")):
                continue
            revenue_amount = Decimal(str(payment.get("revenue_amount", 0)))
            if revenue_amount <= 0:
                continue
            monthly_revenue_totals[payment.get("currency") or "USD"] += revenue_amount

        users_by_plan = (
            UserSubscription.objects.select_related("plan")
            .values("plan__name")
            .annotate(count=Count("id"))
            .order_by("plan__tier", "plan__name")
        )

        user_growth = defaultdict(int)
        for user in User.objects.filter(created_at__gte=range_start):
            user_growth[cls._month_start(user.created_at)] += 1

        revenue_growth = defaultdict(lambda: {"stripe": Decimal("0"), "bkash": Decimal("0")})
        for payment in payments:
            created_at = cls._iso_to_datetime(payment.get("created_at"))
            if not created_at:
                continue
            month_start = cls._month_start(created_at)
            revenue_growth[month_start][payment["provider"]] += Decimal(
                str(payment.get("revenue_amount", 0))
            )

        recent_signups = list(
            User.objects.order_by("-created_at").values(
                "id",
                "username",
                "email",
                "first_name",
                "last_name",
                "created_at",
            )[:5]
        )
        recent_payments = payments[:8]

        users_by_plan_payload = [
            {"label": item["plan__name"] or "Unknown", "count": item["count"]}
            for item in users_by_plan
        ]
        user_growth_payload = [
            {"label": cls._format_month_label(month), "count": count}
            for month, count in sorted(user_growth.items(), key=lambda item: item[0])
        ]
        revenue_payload = [
            {
                "label": cls._format_month_label(month),
                "stripe": float(values["stripe"]),
                "bkash": float(values["bkash"]),
                "total": float(values["stripe"] + values["bkash"]),
            }
            for month, values in sorted(revenue_growth.items(), key=lambda item: item[0])
        ]

        return {
            "summary": {
                "total_users": total_users,
                "active_subscriptions": active_subscriptions,
                "monthly_revenue_totals": {
                    currency: str(total.quantize(Decimal("0.01")))
                    for currency, total in monthly_revenue_totals.items()
                },
            },
            "users_by_plan": users_by_plan_payload,
            "user_growth_over_time": user_growth_payload,
            "revenue_over_time": revenue_payload,
            "recent_signups": recent_signups,
            "recent_payments": recent_payments,
            "warnings": payment_data["warnings"],
        }

    @classmethod
    def build_user_detail_snapshot(cls, user):
        subscription = LicenseService.get_user_subscription(user)
        payments_data = cls.list_payments(user_id=user.id)
        return {
            "subscription": subscription,
            "usage": {
                "usage_snapshot": LicenseService.get_usage_snapshot(user),
            },
            "recent_payments": payments_data["payments"][:10],
            "payment_warnings": payments_data["warnings"],
        }

    @classmethod
    def get_plans_for_admin(cls):
        return list(
            Plan.objects.filter(is_active=True).values("id", "name", "slug", "tier")
        )
