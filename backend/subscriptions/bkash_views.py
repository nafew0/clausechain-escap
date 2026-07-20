import logging
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from clausechain.audit import log_audit_event
from clausechain.client_ip import ip_matches_allowlist
from .bkash_sns import (
    BkashSNSPayloadError,
    BkashSNSVerificationError,
    confirm_sns_subscription,
    extract_notification_payload,
    parse_sns_message,
    verify_sns_message_signature,
)
from .bkash_service import (
    BkashCheckoutConflictError,
    BkashConfigurationError,
    BkashService,
    BkashServiceError,
    BkashUserInputError,
)
from .models import BkashTransaction, Plan
from .serializers import (
    BkashCheckoutSessionSerializer,
    BkashTransactionSerializer,
)
from .services import LicenseService
from .tasks import process_bkash_webhook_notification
from .throttles import (
    PaymentCheckoutThrottle,
    PaymentStatusThrottle,
    get_bkash_callback_ip,
    should_throttle_bkash_callback,
)

logger = logging.getLogger(__name__)


def _map_callback_status(value):
    normalized = str(value or "").strip().lower()
    if normalized == "cancel":
        return BkashTransaction.Status.CANCELLED
    if normalized == "expired":
        return BkashTransaction.Status.EXPIRED
    return BkashTransaction.Status.FAILED


def _safe_redirect(url_builder, *, status_value="failed", payment_id=""):
    try:
        if status_value == "success":
            return redirect(url_builder(payment_id=payment_id))
        return redirect(url_builder(status_value=status_value))
    except Exception:  # pragma: no cover - last-resort fallback for callback UX
        logger.exception("Could not build the reactdjango bKash callback redirect URL.")
        return redirect("/payment/failed")


def _notification_candidates(notification_payload):
    candidates = []
    if isinstance(notification_payload, dict):
        candidates.append(notification_payload)

        for key in ("data", "payment", "transaction", "payload", "details"):
            nested_value = notification_payload.get(key)
            if isinstance(nested_value, dict):
                candidates.append(nested_value)
            elif isinstance(nested_value, str):
                try:
                    parsed = json.loads(nested_value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    candidates.append(parsed)

    return candidates


def _extract_notification_value(notification_payload, *keys):
    for candidate in _notification_candidates(notification_payload):
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    return normalized
    return ""


def _map_notification_status_value(notification_payload):
    raw_value = _extract_notification_value(
        notification_payload,
        "transactionStatus",
        "paymentStatus",
        "status",
        "statusMessage",
    ).lower()
    if raw_value in {"completed", "complete", "success", "successful"}:
        return BkashTransaction.Status.COMPLETED
    if raw_value in {"cancel", "cancelled"}:
        return BkashTransaction.Status.CANCELLED
    if raw_value in {"expired"}:
        return BkashTransaction.Status.EXPIRED
    if raw_value in {"failed", "failure", "error"}:
        return BkashTransaction.Status.FAILED
    return None


def _sync_bkash_webhook_transaction(*, payment_id, status_hint=None, response_data=None):
    task_kwargs = {
        "payment_id": payment_id,
        "status_hint": status_hint,
    }
    if response_data:
        task_kwargs["response_data"] = response_data

    try:
        process_bkash_webhook_notification.delay(**task_kwargs)
    except Exception:
        logger.exception("Could not queue bKash webhook processing; falling back inline.")
        process_bkash_webhook_notification(**task_kwargs)


class BkashCheckoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentCheckoutThrottle]

    def post(self, request):
        serializer = BkashCheckoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = get_object_or_404(
            Plan.objects.filter(is_active=True),
            pk=serializer.validated_data["plan_id"],
        )
        billing_cycle = serializer.validated_data["billing_cycle"]

        if plan.slug == LicenseService.FREE_PLAN_SLUG:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="free_plan",
            )
            return Response(
                {"detail": "The Free plan does not require bKash checkout."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if LicenseService.get_bkash_amount_for_plan(plan, billing_cycle) <= 0:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="missing_bdt_price",
            )
            return Response(
                {
                    "detail": f"The BDT price for the {plan.name} {billing_cycle} plan is not configured yet."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            subscription = LicenseService.get_user_subscription(
                request.user,
                for_update=True,
            )
            validation = LicenseService.validate_bkash_checkout_request(
                subscription,
                plan,
                billing_cycle,
            )
            if not validation.allowed:
                log_audit_event(
                    "bkash_checkout",
                    outcome="failure",
                    level="warning",
                    request=request,
                    plan_id=str(plan.pk),
                    billing_cycle=billing_cycle,
                    reason="validation_blocked",
                )
                return Response(
                    {"detail": validation.message},
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            payment_session = BkashService.create_payment(
                request.user,
                plan,
                billing_cycle,
            )
        except BkashCheckoutConflictError as exc:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="checkout_conflict",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except BkashConfigurationError as exc:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="bkash_not_configured",
            )
            return Response(
                {"detail": str(exc), "code": "bkash_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except BkashUserInputError as exc:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="invalid_request",
            )
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except BkashServiceError as exc:
            log_audit_event(
                "bkash_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=str(plan.pk),
                billing_cycle=billing_cycle,
                reason="provider_error",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            subscription = LicenseService.get_user_subscription(
                request.user,
                for_update=True,
            )
            validation = LicenseService.validate_bkash_checkout_request(
                subscription,
                plan,
                billing_cycle,
            )
            if not validation.allowed:
                logger.warning(
                    "bKash checkout session orphaned by state change for user=%s plan=%s",
                    request.user.pk,
                    plan.pk,
                )
                log_audit_event(
                    "bkash_checkout",
                    outcome="failure",
                    level="warning",
                    request=request,
                    plan_id=str(plan.pk),
                    billing_cycle=billing_cycle,
                    reason="state_changed",
                )
                return Response(
                    {"detail": validation.message},
                    status=status.HTTP_409_CONFLICT,
                )

            BkashTransaction.objects.create(
                user=request.user,
                subscription=subscription,
                target_plan=plan,
                billing_cycle=billing_cycle,
                payment_id=payment_session["payment_id"],
                invoice_number=payment_session["invoice_number"],
                amount=payment_session["amount"],
                currency="BDT",
                status=BkashTransaction.Status.INITIATED,
                bkash_response=payment_session["response"],
            )

        log_audit_event(
            "bkash_checkout",
            request=request,
            plan_id=str(plan.pk),
            billing_cycle=billing_cycle,
            payment_id=payment_session["payment_id"],
        )
        return Response(
            {
                "bkash_url": payment_session["bkash_url"],
                "payment_id": payment_session["payment_id"],
            },
            status=status.HTTP_200_OK,
        )


@csrf_exempt
def bkash_callback_view(request):
    payment_id = (request.GET.get("paymentID") or "").strip()
    status_value = (request.GET.get("status") or "").strip().lower()
    callback_ip = get_bkash_callback_ip(request)

    if should_throttle_bkash_callback(callback_ip):
        log_audit_event(
            "bkash_callback",
            outcome="failure",
            level="warning",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
            reason="rate_limited",
        )
        return _safe_redirect(
            BkashService.build_failure_redirect_url,
            status_value="failed",
        )

    trusted_ips = getattr(settings, "BKASH_CALLBACK_TRUSTED_IPS", [])
    if trusted_ips:
        if not ip_matches_allowlist(callback_ip, trusted_ips):
            log_audit_event(
                "bkash_callback",
                outcome="rejected",
                level="warning",
                request=request,
                payment_id=payment_id,
                status_value=status_value,
                reason="source_not_allowlisted",
            )
            return _safe_redirect(
                BkashService.build_failure_redirect_url,
                status_value="failed",
            )
    else:
        log_audit_event(
            "bkash_callback_allowlist_unconfigured",
            outcome="warning",
            level="warning",
            request=request,
        )

    try:
        if not payment_id:
            log_audit_event(
                "bkash_callback",
                outcome="failure",
                level="warning",
                request=request,
                status_value=status_value,
                reason="missing_payment_id",
            )
            return _safe_redirect(
                BkashService.build_failure_redirect_url,
                status_value="failed",
            )

        if status_value == "success":
            BkashService.sync_transaction(
                payment_id,
                status_hint=BkashTransaction.Status.COMPLETED,
            )
            log_audit_event(
                "bkash_callback",
                request=request,
                payment_id=payment_id,
                status_value=status_value,
            )
            return _safe_redirect(
                BkashService.build_success_redirect_url,
                status_value="success",
                payment_id=payment_id,
            )

        BkashService.sync_transaction(
            payment_id,
            status_hint=_map_callback_status(status_value),
        )
        log_audit_event(
            "bkash_callback",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
        )
        return _safe_redirect(
            BkashService.build_failure_redirect_url,
            status_value=status_value,
        )
    except BkashUserInputError:
        log_audit_event(
            "bkash_callback",
            outcome="failure",
            level="warning",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
            reason="unknown_payment_id",
        )
        logger.warning(
            "bKash callback referenced an unknown payment ID.", exc_info=True
        )
    except BkashConfigurationError:
        log_audit_event(
            "bkash_callback",
            outcome="failure",
            level="warning",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
            reason="bkash_not_configured",
        )
        logger.exception("bKash callback received before the gateway was configured.")
    except BkashServiceError:
        log_audit_event(
            "bkash_callback",
            outcome="failure",
            level="warning",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
            reason="provider_error",
        )
        logger.exception("bKash callback processing failed.")
    except Exception:
        log_audit_event(
            "bkash_callback",
            outcome="failure",
            level="warning",
            request=request,
            payment_id=payment_id,
            status_value=status_value,
            reason="unexpected_error",
        )
        logger.exception("Unexpected bKash callback failure.")

    return _safe_redirect(
        BkashService.build_failure_redirect_url,
        status_value="failed",
    )


@csrf_exempt
@require_POST
def bkash_webhook_view(request):
    try:
        message = parse_sns_message(request.body)
        verify_sns_message_signature(
            message,
            expected_topic_arn=getattr(settings, "BKASH_WEBHOOK_TOPIC_ARN", ""),
        )
    except BkashSNSPayloadError:
        log_audit_event(
            "bkash_webhook",
            outcome="failure",
            level="warning",
            request=request,
            reason="invalid_payload",
        )
        return HttpResponse(status=400)
    except BkashSNSVerificationError:
        log_audit_event(
            "bkash_webhook",
            outcome="rejected",
            level="warning",
            request=request,
            reason="signature_verification_failed",
        )
        return HttpResponse(status=400)

    message_type = (message.get("Type") or "").strip()
    topic_arn = (message.get("TopicArn") or "").strip()
    message_id = (message.get("MessageId") or "").strip()

    if message_type == "SubscriptionConfirmation":
        try:
            confirm_sns_subscription(message)
        except (BkashSNSPayloadError, BkashSNSVerificationError):
            log_audit_event(
                "bkash_webhook_subscription",
                outcome="failure",
                level="warning",
                request=request,
                topic_arn=topic_arn,
                message_id=message_id,
                reason="confirmation_rejected",
            )
            return HttpResponse(status=400)
        except Exception:
            log_audit_event(
                "bkash_webhook_subscription",
                outcome="failure",
                level="warning",
                request=request,
                topic_arn=topic_arn,
                message_id=message_id,
                reason="confirmation_failed",
            )
            logger.exception("Could not confirm the bKash SNS subscription.")
            return HttpResponse(status=500)

        log_audit_event(
            "bkash_webhook_subscription",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
        )
        return HttpResponse(status=200)

    if message_type == "UnsubscribeConfirmation":
        log_audit_event(
            "bkash_webhook_unsubscribe",
            outcome="warning",
            level="warning",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
        )
        return HttpResponse(status=200)

    if message_type != "Notification":
        log_audit_event(
            "bkash_webhook",
            outcome="rejected",
            level="warning",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
            reason="unsupported_message_type",
            message_type=message_type,
        )
        return HttpResponse(status=400)

    try:
        notification_payload = extract_notification_payload(message)
    except BkashSNSPayloadError:
        log_audit_event(
            "bkash_webhook",
            outcome="failure",
            level="warning",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
            reason="invalid_notification",
        )
        return HttpResponse(status=400)

    payment_id = _extract_notification_value(
        notification_payload, "paymentID", "paymentId"
    )
    trx_id = _extract_notification_value(
        notification_payload, "trxID", "trxId", "transactionId"
    )
    invoice_number = _extract_notification_value(
        notification_payload,
        "merchantInvoiceNumber",
        "merchantInvoiceNo",
        "invoiceNumber",
        "invoiceNo",
    )
    provider_status = None

    if not payment_id and trx_id:
        try:
            provider_status = BkashService.search_transaction(trx_id)
        except BkashServiceError:
            log_audit_event(
                "bkash_webhook",
                outcome="failure",
                level="warning",
                request=request,
                topic_arn=topic_arn,
                message_id=message_id,
                trx_id=trx_id,
                reason="search_transaction_failed",
            )
            logger.exception("bKash webhook could not resolve a payment by trxID.")
            return HttpResponse(status=500)

        payment_id = (provider_status.get("paymentID") or payment_id or "").strip()
        trx_id = (provider_status.get("trxID") or trx_id or "").strip()
        invoice_number = (
            provider_status.get("merchantInvoiceNumber")
            or provider_status.get("merchantInvoiceNo")
            or invoice_number
            or ""
        ).strip()

    transaction_record = BkashService.get_matching_transaction(
        payment_id=payment_id,
        trx_id=trx_id,
        invoice_number=invoice_number,
    )
    if not transaction_record:
        log_audit_event(
            "bkash_webhook",
            outcome="warning",
            level="warning",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
            payment_id=payment_id,
            trx_id=trx_id,
            invoice_number=invoice_number,
            reason="transaction_not_found",
        )
        return HttpResponse(status=200)

    status_hint = _map_notification_status_value(notification_payload)
    try:
        if status_hint == BkashTransaction.Status.COMPLETED:
            _sync_bkash_webhook_transaction(
                payment_id=transaction_record.payment_id,
                status_hint=status_hint,
            )
        elif status_hint:
            _sync_bkash_webhook_transaction(
                payment_id=transaction_record.payment_id,
                status_hint=status_hint,
                response_data=provider_status or notification_payload,
            )
        else:
            _sync_bkash_webhook_transaction(payment_id=transaction_record.payment_id)
    except BkashServiceError:
        log_audit_event(
            "bkash_webhook",
            outcome="failure",
            level="warning",
            request=request,
            topic_arn=topic_arn,
            message_id=message_id,
            payment_id=transaction_record.payment_id,
            trx_id=trx_id,
            invoice_number=invoice_number,
            reason="sync_failed",
        )
        logger.exception("bKash webhook processing failed.")
        return HttpResponse(status=500)

    log_audit_event(
        "bkash_webhook",
        request=request,
        topic_arn=topic_arn,
        message_id=message_id,
        payment_id=transaction_record.payment_id,
        trx_id=trx_id,
        invoice_number=invoice_number,
        notification_status=status_hint or "",
    )
    return HttpResponse(status=200)


class BkashPaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentStatusThrottle]

    def get(self, request, payment_id):
        transaction_record = get_object_or_404(
            BkashTransaction.objects.select_related("target_plan"),
            payment_id=payment_id,
            user=request.user,
        )

        provider_status = transaction_record.bkash_response
        if transaction_record.status == BkashTransaction.Status.INITIATED:
            try:
                transaction_record = BkashService.sync_transaction(payment_id)
                provider_status = transaction_record.bkash_response
            except BkashConfigurationError as exc:
                return Response(
                    {
                        "transaction": BkashTransactionSerializer(
                            transaction_record
                        ).data,
                        "provider_status": provider_status,
                        "provider_status_unavailable": True,
                        "detail": str(exc),
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except BkashServiceError as exc:
                return Response(
                    {
                        "transaction": BkashTransactionSerializer(
                            transaction_record
                        ).data,
                        "provider_status": provider_status,
                        "provider_status_unavailable": True,
                        "detail": str(exc),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return Response(
            {
                "transaction": BkashTransactionSerializer(transaction_record).data,
                "provider_status": provider_status,
            },
            status=status.HTTP_200_OK,
        )
