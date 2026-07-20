import csv

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from clausechain.audit import log_audit_event
from subscriptions.admin_services import AdminPaymentsService
from subscriptions.bkash_service import (
    BkashConfigurationError,
    BkashService,
    BkashServiceError,
    BkashUserInputError,
)
from subscriptions.models import BkashTransaction, Plan, SubscriptionEvent
from subscriptions.serializers import (
    BkashRefundRequestSerializer,
    BkashSearchTransactionSerializer,
)
from subscriptions.services import LicenseService

from .ai_secrets import get_ai_api_key, get_ai_api_key_env_var
from .admin_serializers import (
    AITestRequestSerializer,
    AdminSubscriptionSummarySerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserUpdateSerializer,
    SiteSettingsAdminSerializer,
    SiteSettingsUpdateSerializer,
    SubscriptionEventSerializer,
)
from .ai_testing import AITestConnectionError, AITestService
from .models import SiteSettings
from .password_reset import send_password_reset_email
from .throttles import AdminRateThrottle
from .user_deletion import delete_user_account
from .verification import get_site_settings as get_runtime_site_settings

User = get_user_model()
BRANDING_ASSET_FIELDS = (
    "branding_logo",
    "branding_favicon",
    "branding_login_banner",
    "branding_register_banner",
)


class IsSuperuserPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_superuser
        )


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminAPIView(APIView):
    permission_classes = [IsSuperuserPermission]
    throttle_classes = [AdminRateThrottle]


class AdminGateView(AdminAPIView):
    def get(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response["Cache-Control"] = "no-store"
        return response


def get_site_settings():
    return get_runtime_site_settings()


def parse_datetime_filter(value, *, end_of_day=False):
    if not value:
        return None
    try:
        parsed = timezone.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    if end_of_day:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


class AdminDashboardView(AdminAPIView):
    def get(self, request):
        return Response(AdminPaymentsService.build_dashboard_payload())


class AdminUsersView(AdminAPIView):
    pagination_class = AdminPagination

    def get_queryset(self, request):
        queryset = User.objects.select_related("subscription__plan")

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        plan_slug = (request.query_params.get("plan") or "").strip()
        if plan_slug:
            queryset = queryset.filter(subscription__plan__slug=plan_slug)

        is_active = (request.query_params.get("is_active") or "").strip().lower()
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        ordering = (request.query_params.get("ordering") or "-created_at").strip()
        ordering_map = {
            "created_at": "created_at",
            "-created_at": "-created_at",
            "last_login": "last_login",
            "-last_login": "-last_login",
            "username": "username",
            "-username": "-username",
            "email": "email",
            "-email": "-email",
        }
        return queryset.order_by(ordering_map.get(ordering, "-created_at"))

    def get(self, request):
        queryset = self.get_queryset(request)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AdminUserListSerializer(page, many=True)
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
                "plans": AdminPaymentsService.get_plans_for_admin(),
            }
        )


class AdminUserDetailView(AdminAPIView):
    def get_user(self, user_id):
        return get_object_or_404(
            User.objects.select_related("subscription__plan"),
            pk=user_id,
        )

    def get(self, request, user_id):
        user = self.get_user(user_id)
        detail = AdminPaymentsService.build_user_detail_snapshot(user)
        events = SubscriptionEvent.objects.filter(user=user).select_related("plan")[:10]

        return Response(
            {
                "user": AdminUserDetailSerializer(user).data,
                "subscription": AdminSubscriptionSummarySerializer(
                    detail["subscription"]
                ).data,
                "usage": detail["usage"],

                "recent_payments": detail["recent_payments"],
                "payment_warnings": detail["payment_warnings"],
                "subscription_events": SubscriptionEventSerializer(
                    events, many=True
                ).data,
                "plans": AdminPaymentsService.get_plans_for_admin(),
            }
        )

    def patch(self, request, user_id):
        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_user = self.get_user(user_id)
        validated = serializer.validated_data

        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(pk=target_user.pk)
            subscription = LicenseService.get_user_subscription(
                locked_user, for_update=True
            )

            if "is_active" in validated:
                next_is_active = validated["is_active"]
                if locked_user.pk == request.user.pk and not next_is_active:
                    log_audit_event(
                        "admin_user_update",
                        outcome="failure",
                        level="warning",
                        request=request,
                        target_user=locked_user,
                        reason="self_deactivation_blocked",
                    )
                    return Response(
                        {"detail": "You cannot deactivate your own account."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if (
                    locked_user.is_superuser
                    and locked_user.is_active
                    and not next_is_active
                    and User.objects.filter(is_superuser=True, is_active=True).count() <= 1
                ):
                    log_audit_event(
                        "admin_user_update",
                        outcome="failure",
                        level="warning",
                        request=request,
                        target_user=locked_user,
                        reason="last_superuser_blocked",
                    )
                    return Response(
                        {
                            "detail": "At least one active superuser account is required."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                locked_user.is_active = next_is_active
                locked_user.save(update_fields=["is_active"])

            if "plan_id" in validated:
                plan = get_object_or_404(Plan.objects.filter(is_active=True), pk=validated["plan_id"])
                if (
                    subscription.payment_provider
                    == subscription.PaymentProvider.STRIPE
                    and LicenseService.is_subscription_paid_and_active(subscription)
                ):
                    log_audit_event(
                        "admin_user_update",
                        outcome="failure",
                        level="warning",
                        request=request,
                        target_user=locked_user,
                        reason="active_stripe_subscription",
                    )
                    return Response(
                        {
                            "detail": "Active Stripe-managed subscriptions must be changed from the Stripe billing portal."
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                previous_state = LicenseService.serialize_subscription_state(subscription)
                subscription.plan = plan
                subscription.status = subscription.Status.ACTIVE
                subscription.payment_provider = subscription.PaymentProvider.NONE
                if not subscription.billing_cycle:
                    subscription.billing_cycle = subscription.BillingCycle.MONTHLY
                subscription.cancel_at_period_end = False
                subscription.cancel_requested_at = None
                subscription.stripe_customer_id = None
                subscription.stripe_subscription_id = None
                subscription.bkash_subscription_id = None
                subscription.current_period_start = None
                subscription.current_period_end = None
                subscription.save()
                LicenseService.record_subscription_event(
                    subscription,
                    SubscriptionEvent.EventType.ADMIN_OVERRIDE,
                    metadata={
                        "actor_user_id": str(request.user.id),
                        "previous_state": previous_state,
                    },
                )
        log_audit_event(
            "admin_user_update",
            request=request,
            target_user=target_user,
            updated_fields=sorted(validated.keys()),
        )

        refreshed_user = self.get_user(user_id)
        detail = AdminPaymentsService.build_user_detail_snapshot(refreshed_user)
        events = SubscriptionEvent.objects.filter(user=refreshed_user).select_related(
            "plan"
        )[:10]
        return Response(
            {
                "user": AdminUserDetailSerializer(refreshed_user).data,
                "subscription": AdminSubscriptionSummarySerializer(
                    detail["subscription"]
                ).data,
                "usage": detail["usage"],

                "recent_payments": detail["recent_payments"],
                "payment_warnings": detail["payment_warnings"],
                "subscription_events": SubscriptionEventSerializer(
                    events, many=True
                ).data,
            }
        )

    def delete(self, request, user_id):
        target_user = self.get_user(user_id)

        if target_user.is_superuser:
            log_audit_event(
                "admin_user_delete",
                outcome="failure",
                level="warning",
                request=request,
                target_user=target_user,
                reason="superuser_delete_blocked",
            )
            return Response(
                {"detail": "Admin accounts cannot be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delete_user_account(
            target_user,
            request=request,
            audit_event="admin_user_delete",
        )
        return Response(
            {"message": "User deleted successfully."},
            status=status.HTTP_200_OK,
        )


class AdminSendPasswordResetView(AdminAPIView):
    def post(self, request, user_id):
        target_user = get_object_or_404(User, pk=user_id, is_active=True)
        try:
            send_password_reset_email(target_user, requested_by=request.user)
        except ImproperlyConfigured as exc:
            log_audit_event(
                "admin_password_reset_send",
                outcome="failure",
                level="warning",
                request=request,
                target_user=target_user,
                reason="email_not_configured",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        log_audit_event(
            "admin_password_reset_send",
            request=request,
            target_user=target_user,
        )
        return Response(
            {"detail": "Password reset email sent successfully."},
            status=status.HTTP_200_OK,
        )


class AdminPaymentsView(AdminAPIView):
    pagination_class = AdminPagination

    def get_payment_data(self, request):
        return AdminPaymentsService.list_payments(
            provider=(request.query_params.get("provider") or "").strip(),
            status=(request.query_params.get("status") or "").strip(),
            user_id=(request.query_params.get("user_id") or "").strip(),
            date_from=parse_datetime_filter(request.query_params.get("date_from")),
            date_to=parse_datetime_filter(
                request.query_params.get("date_to"), end_of_day=True
            ),
            search=(request.query_params.get("search") or "").strip(),
            ordering=(request.query_params.get("ordering") or "-created_at").strip(),
        )

    def get(self, request):
        payment_data = self.get_payment_data(request)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(payment_data["payments"], request)
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": page,
                "revenue_totals": payment_data["revenue_totals"],
                "warnings": payment_data["warnings"],
            }
        )


class AdminPaymentsExportView(AdminPaymentsView):
    def get(self, request):
        payment_data = self.get_payment_data(request)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="payments.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "provider",
                "provider_reference",
                "invoice_number",
                "status",
                "amount",
                "currency",
                "billing_cycle",
                "plan",
                "username",
                "email",
                "created_at",
            ]
        )
        for payment in payment_data["payments"]:
            writer.writerow(
                [
                    payment.get("provider", ""),
                    payment.get("provider_reference", ""),
                    payment.get("invoice_number", ""),
                    payment.get("status", ""),
                    payment.get("amount", ""),
                    payment.get("currency", ""),
                    payment.get("billing_cycle", ""),
                    payment.get("plan", {}).get("name", ""),
                    payment.get("user", {}).get("username", ""),
                    payment.get("user", {}).get("email", ""),
                    payment.get("created_at", ""),
                ]
            )
        return response


class AdminBkashPaymentSearchView(AdminAPIView):
    def get(self, request):
        serializer = BkashSearchTransactionSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        trx_id = serializer.validated_data["trx_id"]
        try:
            provider_status = BkashService.search_transaction(trx_id)
        except BkashConfigurationError as exc:
            log_audit_event(
                "admin_bkash_search",
                outcome="failure",
                level="warning",
                request=request,
                trx_id=trx_id,
                reason="bkash_not_configured",
            )
            return Response(
                {"detail": str(exc), "code": "bkash_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except BkashServiceError as exc:
            log_audit_event(
                "admin_bkash_search",
                outcome="failure",
                level="warning",
                request=request,
                trx_id=trx_id,
                reason="provider_error",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        transaction_record = BkashService.get_matching_transaction(
            payment_id=(provider_status.get("paymentID") or "").strip(),
            trx_id=(provider_status.get("trxID") or trx_id).strip(),
            invoice_number=(
                provider_status.get("merchantInvoiceNumber")
                or provider_status.get("merchantInvoiceNo")
                or ""
            ).strip(),
        )
        log_audit_event(
            "admin_bkash_search",
            request=request,
            target_user=transaction_record.user if transaction_record else None,
            trx_id=trx_id,
            payment_id=(provider_status.get("paymentID") or "").strip(),
            transaction_found=bool(transaction_record),
        )
        return Response(
            {
                "provider_status": provider_status,
                "transaction": (
                    AdminPaymentsService.serialize_bkash_payment(transaction_record)
                    if transaction_record
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )


class AdminBkashRefundView(AdminAPIView):
    def post(self, request, payment_id):
        transaction_record = get_object_or_404(
            BkashTransaction.objects.select_related("user", "target_plan"),
            payment_id=payment_id,
        )
        serializer = BkashRefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refunded_transaction = BkashService.refund_payment(
                payment_id,
                amount=serializer.validated_data["amount"],
                reason=serializer.validated_data.get("reason", ""),
                sku=serializer.validated_data.get("sku", ""),
            )
        except BkashConfigurationError as exc:
            log_audit_event(
                "admin_bkash_refund",
                outcome="failure",
                level="warning",
                request=request,
                target_user=transaction_record.user,
                payment_id=payment_id,
                reason="bkash_not_configured",
            )
            return Response(
                {"detail": str(exc), "code": "bkash_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except BkashUserInputError as exc:
            log_audit_event(
                "admin_bkash_refund",
                outcome="failure",
                level="warning",
                request=request,
                target_user=transaction_record.user,
                payment_id=payment_id,
                refund_amount=str(serializer.validated_data["amount"]),
                reason="invalid_request",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except BkashServiceError as exc:
            log_audit_event(
                "admin_bkash_refund",
                outcome="failure",
                level="warning",
                request=request,
                target_user=transaction_record.user,
                payment_id=payment_id,
                refund_amount=str(serializer.validated_data["amount"]),
                reason="provider_error",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        log_audit_event(
            "admin_bkash_refund",
            request=request,
            target_user=refunded_transaction.user,
            payment_id=payment_id,
            refund_amount=str(refunded_transaction.refund_amount),
            refund_status=refunded_transaction.refund_status,
            refund_trx_id=refunded_transaction.refund_trx_id or "",
        )
        return Response(
            {
                "transaction": AdminPaymentsService.serialize_bkash_payment(
                    refunded_transaction
                ),
                "provider_status": refunded_transaction.refund_response,
            },
            status=status.HTTP_200_OK,
        )


class AdminSettingsView(AdminAPIView):
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        return Response(SiteSettingsAdminSerializer(get_site_settings()).data)

    def patch(self, request):
        settings_obj = get_site_settings()
        serializer = SiteSettingsUpdateSerializer(
            settings_obj,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        previous_files = {}
        updated_fields = []

        for field_name in BRANDING_ASSET_FIELDS:
            existing_file = getattr(settings_obj, field_name, None)
            if existing_file and getattr(existing_file, "name", ""):
                previous_files[field_name] = (existing_file.storage, existing_file.name)

        for field, value in serializer.validated_data.items():
            if field.startswith("clear_") or field in BRANDING_ASSET_FIELDS:
                continue
            setattr(settings_obj, field, value)
            updated_fields.append(field)

        for field_name in BRANDING_ASSET_FIELDS:
            should_clear = bool(serializer.validated_data.get(f"clear_{field_name}", False))
            if should_clear:
                setattr(settings_obj, field_name, None)
                updated_fields.append(field_name)
                continue

            if field_name in serializer.validated_data:
                setattr(settings_obj, field_name, serializer.validated_data[field_name])
                updated_fields.append(field_name)

        settings_obj.save()

        for field_name, (storage, old_name) in previous_files.items():
            current_field = getattr(settings_obj, field_name, None)
            current_name = getattr(current_field, "name", "") if current_field else ""
            if old_name and old_name != current_name:
                storage.delete(old_name)

        log_audit_event(
            "admin_settings_update",
            request=request,
            updated_fields=sorted(set(updated_fields)),
        )
        return Response(SiteSettingsAdminSerializer(settings_obj).data)


class AdminSettingsTestAIView(AdminAPIView):
    def post(self, request):
        settings_obj = get_site_settings()
        provider = request.data.get("provider") or settings_obj.ai_provider
        model = request.data.get("model") or (
            settings_obj.ai_model_openai
            if provider == SiteSettings.AIProvider.OPENAI
            else settings_obj.ai_model_anthropic
        )
        payload = {
            "provider": provider,
            "model": model,
        }
        serializer = AITestRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        api_key = get_ai_api_key(settings_obj, serializer.validated_data["provider"])
        if not api_key:
            env_var_name = get_ai_api_key_env_var(serializer.validated_data["provider"])
            log_audit_event(
                "admin_ai_test",
                outcome="failure",
                level="warning",
                request=request,
                provider=serializer.validated_data["provider"],
                model=serializer.validated_data["model"],
                reason="missing_api_key",
            )
            return Response(
                {
                    "detail": f"Set {env_var_name} on the server before testing this provider."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = AITestService.test_connection(
                api_key=api_key,
                **serializer.validated_data,
            )
        except AITestConnectionError as exc:
            log_audit_event(
                "admin_ai_test",
                outcome="failure",
                level="warning",
                request=request,
                provider=serializer.validated_data["provider"],
                model=serializer.validated_data["model"],
                reason="connection_failed",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit_event(
            "admin_ai_test",
            request=request,
            provider=serializer.validated_data["provider"],
            model=serializer.validated_data["model"],
        )
        return Response(result, status=status.HTTP_200_OK)
