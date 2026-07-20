import json
import logging
import secrets
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import BkashTransaction, SubscriptionEvent, UserSubscription
from .services import LicenseService

logger = logging.getLogger(__name__)


class BkashConfigurationError(Exception):
    pass


class BkashServiceError(Exception):
    pass


class BkashUserInputError(BkashServiceError):
    pass


class BkashCheckoutConflictError(BkashServiceError):
    pass


class BkashApiError(BkashServiceError):
    def __init__(self, message, *, response_data=None, http_status=None):
        super().__init__(message)
        self.response_data = response_data or {}
        self.http_status = http_status


class BkashExecutionFallbackRequired(BkashServiceError):
    def __init__(self, message, *, response_data=None):
        super().__init__(message)
        self.response_data = response_data or {}


class BkashService:
    REQUEST_TIMEOUT_SECONDS = 30
    TOKEN_CACHE_KEY = "subscriptions:bkash:token"
    TOKEN_CACHE_TTL_FALLBACK_SECONDS = 3500
    SUCCESS_CODES = {"0000", "000", "0"}
    AUTH_FAILURE_CODES = {"2001", "2002", "2011", "2023"}
    ALREADY_PROCESSED_CODES = {"2029"}
    CALLBACK_PATH = "/api/payments/bkash/callback/"
    WEBHOOK_PATH = "/api/payments/bkash/webhook/"

    @classmethod
    def _build_api_url(cls, path, query_params=None):
        base_url = (settings.BKASH_BASE_URL or "").rstrip("/")
        if not base_url:
            raise BkashConfigurationError("BKASH_BASE_URL must be configured.")
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{base_url}{normalized_path}"
        if query_params:
            url = f"{url}?{urlencode(query_params)}"
        return url

    @classmethod
    def _build_callback_url(cls):
        api_origin = (getattr(settings, "API_ORIGIN", "") or "").rstrip("/")
        if not api_origin:
            raise BkashConfigurationError(
                "API_ORIGIN must be configured for the public bKash callback URL."
            )
        return f"{api_origin}{cls.CALLBACK_PATH}"

    @classmethod
    def build_webhook_url(cls):
        configured_url = (getattr(settings, "BKASH_WEBHOOK_URL", "") or "").strip()
        if configured_url:
            return configured_url

        api_origin = (getattr(settings, "API_ORIGIN", "") or "").rstrip("/")
        if not api_origin:
            raise BkashConfigurationError(
                "API_ORIGIN must be configured for the public bKash webhook URL."
            )
        return f"{api_origin}{cls.WEBHOOK_PATH}"

    @classmethod
    def _require_configuration(cls, *, require_callback=False):
        missing = [
            name
            for name in [
                "BKASH_APP_KEY",
                "BKASH_APP_SECRET",
                "BKASH_USERNAME",
                "BKASH_PASSWORD",
                "BKASH_BASE_URL",
            ]
            if not getattr(settings, name, "")
        ]
        if require_callback and not getattr(settings, "API_ORIGIN", ""):
            missing.append("API_ORIGIN")

        if missing:
            raise BkashConfigurationError(
                "bKash payments are not fully configured. Missing: "
                + ", ".join(missing)
            )

    @classmethod
    def _cache_get_token_bundle(cls):
        try:
            return cache.get(cls.TOKEN_CACHE_KEY)
        except Exception:  # pragma: no cover - cache failures should not break billing
            logger.warning("bKash token cache read failed.", exc_info=True)
            return None

    @classmethod
    def _cache_set_token_bundle(cls, token_bundle):
        expires_in = int(
            token_bundle.get("expires_in") or cls.TOKEN_CACHE_TTL_FALLBACK_SECONDS
        )
        timeout = max(60, expires_in - 60)
        try:
            cache.set(cls.TOKEN_CACHE_KEY, token_bundle, timeout=timeout)
        except Exception:  # pragma: no cover - cache failures should not break billing
            logger.warning("bKash token cache write failed.", exc_info=True)

    @classmethod
    def _cache_clear_token_bundle(cls):
        try:
            cache.delete(cls.TOKEN_CACHE_KEY)
        except Exception:  # pragma: no cover - cache failures should not break billing
            logger.warning("bKash token cache clear failed.", exc_info=True)

    @classmethod
    def _request(cls, method, path, *, payload=None, headers=None, query_params=None):
        request_headers = {
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        body = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        request = Request(
            cls._build_api_url(path, query_params=query_params),
            data=body,
            headers=request_headers,
            method=method.upper(),
        )

        try:
            with urlopen(request, timeout=cls.REQUEST_TIMEOUT_SECONDS) as response:
                raw_body = response.read().decode("utf-8")
                if not raw_body:
                    return {}
                try:
                    return json.loads(raw_body)
                except json.JSONDecodeError as exc:
                    raise BkashServiceError(
                        "bKash returned an unreadable response."
                    ) from exc
        except HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                data = {}
            raise BkashApiError(
                cls._extract_error_message(
                    data,
                    default="bKash payment request failed.",
                ),
                response_data=data,
                http_status=exc.code,
            ) from exc
        except URLError as exc:
            raise BkashServiceError(
                "Could not reach the bKash payment gateway."
            ) from exc

    @classmethod
    def _extract_error_message(cls, data, *, default):
        if not isinstance(data, dict):
            return default

        for key in ("statusMessage", "errorMessage", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return default

    @classmethod
    def _sanitize_response(cls, data):
        if not isinstance(data, dict):
            return {}

        redacted_keys = {
            "id_token",
            "refresh_token",
            "token",
            "authorization",
            "Authorization",
            "customerMsisdn",
            "msisdn",
            "payerReference",
        }

        sanitized = {}
        for key, value in data.items():
            if key in redacted_keys:
                continue
            if isinstance(value, dict):
                sanitized[key] = cls._sanitize_response(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    cls._sanitize_response(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _is_success_response(cls, data):
        status_code = str((data or {}).get("statusCode", "")).strip()
        status_message = str((data or {}).get("statusMessage", "")).strip().lower()
        return status_code in cls.SUCCESS_CODES or status_message in {
            "successful",
            "success",
        }

    @classmethod
    def _is_auth_failure(cls, error):
        if error.http_status in {401, 403}:
            return True
        status_code = str(error.response_data.get("statusCode", "")).strip()
        return status_code in cls.AUTH_FAILURE_CODES

    @classmethod
    def _looks_already_processed(cls, data):
        status_code = str((data or {}).get("statusCode", "")).strip()
        message = str((data or {}).get("statusMessage", "")).strip().lower()
        return (
            status_code in cls.ALREADY_PROCESSED_CODES
            or "already" in message
            or "duplicate" in message
            or "processing" in message
        )

    @classmethod
    def _normalize_remote_status(cls, data):
        normalized = str((data or {}).get("transactionStatus", "")).strip().lower()
        status_message = str((data or {}).get("statusMessage", "")).strip().lower()
        execution_status = str((data or {}).get("status", "")).strip().lower()

        if cls._is_success_response(data) and (data or {}).get("trxID"):
            return BkashTransaction.Status.COMPLETED
        if normalized in {"completed", "complete", "success"}:
            return BkashTransaction.Status.COMPLETED
        if normalized in {"cancel", "cancelled"} or execution_status in {
            "cancel",
            "cancelled",
        }:
            return BkashTransaction.Status.CANCELLED
        if normalized in {"expired"} or "expired" in status_message:
            return BkashTransaction.Status.EXPIRED
        if normalized in {"failed", "failure"} or execution_status in {
            "failed",
            "failure",
        }:
            return BkashTransaction.Status.FAILED
        if "cancel" in status_message:
            return BkashTransaction.Status.CANCELLED
        if "expired" in status_message:
            return BkashTransaction.Status.EXPIRED
        return BkashTransaction.Status.FAILED

    @classmethod
    def _authorized_request(cls, method, path, *, payload=None, query_params=None):
        token_bundle = cls._cache_get_token_bundle() or {}
        id_token = token_bundle.get("id_token") or cls.grant_token()

        headers = {
            "Authorization": id_token,
            "X-APP-Key": settings.BKASH_APP_KEY,
        }

        try:
            return cls._request(
                method,
                path,
                payload=payload,
                headers=headers,
                query_params=query_params,
            )
        except BkashApiError as exc:
            if not cls._is_auth_failure(exc):
                raise

            refresh_token = token_bundle.get("refresh_token")
            if refresh_token:
                refreshed_token = cls.refresh_token(refresh_token)
            else:
                cls._cache_clear_token_bundle()
                refreshed_token = cls.grant_token(force_refresh=True)

            headers["Authorization"] = refreshed_token
            return cls._request(
                method,
                path,
                payload=payload,
                headers=headers,
                query_params=query_params,
            )

    @classmethod
    def grant_token(cls, *, force_refresh=False):
        cls._require_configuration()

        if not force_refresh:
            token_bundle = cls._cache_get_token_bundle() or {}
            if token_bundle.get("id_token"):
                return token_bundle["id_token"]

        response = cls._request(
            "POST",
            "/tokenized/checkout/token/grant",
            payload={
                "app_key": settings.BKASH_APP_KEY,
                "app_secret": settings.BKASH_APP_SECRET,
            },
            headers={
                "username": settings.BKASH_USERNAME,
                "password": settings.BKASH_PASSWORD,
            },
        )
        if not cls._is_success_response(response):
            raise BkashServiceError(
                cls._extract_error_message(
                    response,
                    default="bKash authentication failed.",
                )
            )

        id_token = response.get("id_token")
        if not id_token:
            raise BkashServiceError(
                "bKash authentication did not return a usable token."
            )

        cls._cache_set_token_bundle(
            {
                "id_token": id_token,
                "refresh_token": response.get("refresh_token", ""),
                "expires_in": response.get(
                    "expires_in", cls.TOKEN_CACHE_TTL_FALLBACK_SECONDS
                ),
            }
        )
        return id_token

    @classmethod
    def refresh_token(cls, refresh_token=None):
        cls._require_configuration()

        token_bundle = cls._cache_get_token_bundle() or {}
        refresh_token = refresh_token or token_bundle.get("refresh_token")
        if not refresh_token:
            return cls.grant_token(force_refresh=True)

        response = cls._request(
            "POST",
            "/tokenized/checkout/token/refresh",
            payload={
                "app_key": settings.BKASH_APP_KEY,
                "app_secret": settings.BKASH_APP_SECRET,
                "refresh_token": refresh_token,
            },
            headers={
                "username": settings.BKASH_USERNAME,
                "password": settings.BKASH_PASSWORD,
            },
        )
        if not cls._is_success_response(response):
            cls._cache_clear_token_bundle()
            return cls.grant_token(force_refresh=True)

        id_token = response.get("id_token")
        if not id_token:
            raise BkashServiceError(
                "bKash token refresh did not return a usable token."
            )

        cls._cache_set_token_bundle(
            {
                "id_token": id_token,
                "refresh_token": response.get("refresh_token", refresh_token),
                "expires_in": response.get(
                    "expires_in", cls.TOKEN_CACHE_TTL_FALLBACK_SECONDS
                ),
            }
        )
        return id_token

    @classmethod
    def _get_bkash_amount(cls, plan, billing_cycle):
        amount = LicenseService.get_bkash_amount_for_plan(plan, billing_cycle)
        if amount <= 0:
            raise BkashUserInputError(
                f"The BDT price for the {plan.name} {billing_cycle} plan is not configured yet."
            )
        return amount.quantize(Decimal("0.01"))

    @classmethod
    def _generate_invoice_number(cls):
        return f"QTZ-BK-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(4).upper()}"

    @classmethod
    def create_payment(cls, user, plan, billing_cycle):
        cls._require_configuration(require_callback=True)

        amount = cls._get_bkash_amount(plan, billing_cycle)
        invoice_number = cls._generate_invoice_number()
        response = cls._authorized_request(
            "POST",
            "/tokenized/checkout/create",
            payload={
                "mode": "0011",
                "payerReference": str(user.id),
                "callbackURL": cls._build_callback_url(),
                "amount": f"{amount:.2f}",
                "currency": "BDT",
                "intent": "sale",
                "merchantInvoiceNumber": invoice_number,
            },
        )
        if not cls._is_success_response(response):
            raise BkashServiceError(
                cls._extract_error_message(
                    response,
                    default="bKash could not start the payment session.",
                )
            )

        payment_id = response.get("paymentID")
        bkash_url = response.get("bkashURL")
        if not payment_id or not bkash_url:
            raise BkashServiceError(
                "bKash did not return a valid hosted checkout session."
            )

        return {
            "payment_id": payment_id,
            "bkash_url": bkash_url,
            "invoice_number": invoice_number,
            "amount": amount,
            "response": cls._sanitize_response(response),
        }

    @classmethod
    def execute_payment(cls, payment_id):
        cls._require_configuration()

        response = cls._authorized_request(
            "POST",
            "/tokenized/checkout/execute",
            payload={"paymentID": payment_id},
        )
        if cls._is_success_response(response) and response.get("trxID"):
            return cls._sanitize_response(response)

        if cls._looks_already_processed(response):
            raise BkashExecutionFallbackRequired(
                "The bKash payment requires a status query fallback.",
                response_data=cls._sanitize_response(response),
            )

        raise BkashServiceError(
            cls._extract_error_message(
                response,
                default="bKash could not confirm the payment.",
            )
        )

    @classmethod
    def query_payment(cls, payment_id):
        cls._require_configuration()
        response = cls._authorized_request(
            "GET",
            "/tokenized/checkout/payment/status",
            query_params={"paymentID": payment_id},
        )
        return cls._sanitize_response(response)

    @classmethod
    def search_transaction(cls, trx_id):
        cls._require_configuration()
        normalized_trx_id = (trx_id or "").strip()
        if not normalized_trx_id:
            raise BkashUserInputError("trxID is required to search a transaction.")
        response = cls._authorized_request(
            "GET",
            f"/tokenized/checkout/payment/search/{quote(normalized_trx_id, safe='')}",
        )
        return cls._sanitize_response(response)

    @classmethod
    def _normalize_refund_status(cls, data):
        transaction_status = str((data or {}).get("transactionStatus", "")).strip().lower()
        status_message = str((data or {}).get("statusMessage", "")).strip().lower()

        if cls._is_success_response(data) or (data or {}).get("refundTrxID"):
            return BkashTransaction.RefundStatus.COMPLETED
        if transaction_status in {"pending", "processing"}:
            return BkashTransaction.RefundStatus.PENDING
        if "pending" in status_message or "processing" in status_message:
            return BkashTransaction.RefundStatus.PENDING
        return BkashTransaction.RefundStatus.FAILED

    @classmethod
    def verify_payment(cls, payment_id):
        try:
            response = cls.execute_payment(payment_id)
            return BkashTransaction.Status.COMPLETED, response
        except BkashExecutionFallbackRequired as exc:
            response = cls.query_payment(payment_id)
            return cls._normalize_remote_status(response), response

    @classmethod
    def build_failure_redirect_url(cls, *, status_value):
        public_app_url = (getattr(settings, "PUBLIC_APP_URL", "") or "").rstrip("/")
        if not public_app_url:
            raise BkashConfigurationError(
                "PUBLIC_APP_URL must be configured for payment result redirects."
            )
        normalized_status = str(status_value or "failed").strip().lower() or "failed"
        return (
            f"{public_app_url}/payment/failed?provider=bkash&status={normalized_status}"
        )

    @classmethod
    def build_success_redirect_url(cls, *, payment_id=""):
        public_app_url = (getattr(settings, "PUBLIC_APP_URL", "") or "").rstrip("/")
        if not public_app_url:
            raise BkashConfigurationError(
                "PUBLIC_APP_URL must be configured for payment result redirects."
            )
        query_params = {"provider": "bkash"}
        normalized_payment_id = (payment_id or "").strip()
        if normalized_payment_id:
            query_params["payment_id"] = normalized_payment_id
        return f"{public_app_url}/payment/success?{urlencode(query_params)}"

    @classmethod
    def get_matching_transaction(
        cls,
        *,
        payment_id="",
        trx_id="",
        invoice_number="",
    ):
        queryset = BkashTransaction.objects.select_related("user", "target_plan")
        if payment_id:
            transaction_record = queryset.filter(payment_id=payment_id).first()
            if transaction_record:
                return transaction_record
        if trx_id:
            transaction_record = queryset.filter(trx_id=trx_id).first()
            if transaction_record:
                return transaction_record
        if invoice_number:
            transaction_record = queryset.filter(invoice_number=invoice_number).first()
            if transaction_record:
                return transaction_record
        return None

    @classmethod
    def _merge_responses(cls, current_response, new_response):
        merged = {}
        if isinstance(current_response, dict):
            merged.update(current_response)
        if isinstance(new_response, dict):
            merged.update(new_response)
        return merged

    @classmethod
    def sync_transaction(cls, payment_id, *, status_hint=None, response_data=None):
        transaction_record = (
            BkashTransaction.objects.select_related("user", "target_plan")
            .filter(payment_id=payment_id)
            .first()
        )
        if not transaction_record:
            raise BkashUserInputError("The bKash payment could not be found.")

        if transaction_record.status == BkashTransaction.Status.COMPLETED:
            return transaction_record

        remote_status = None
        response_data = cls._sanitize_response(response_data or {})

        if status_hint == BkashTransaction.Status.COMPLETED and not response_data:
            remote_status, response_data = cls.verify_payment(payment_id)
        elif status_hint is None:
            remote_status, response_data = cls.verify_payment(payment_id)
        else:
            remote_status = status_hint

        with transaction.atomic():
            transaction_record = (
                BkashTransaction.objects.select_related("user", "target_plan")
                .select_for_update()
                .get(pk=transaction_record.pk)
            )
            subscription = LicenseService.get_user_subscription(
                transaction_record.user,
                for_update=True,
            )
            previous_state = LicenseService.serialize_subscription_state(subscription)

            if transaction_record.status == BkashTransaction.Status.COMPLETED:
                return transaction_record

            if remote_status == BkashTransaction.Status.COMPLETED:
                subscription = LicenseService.activate_bkash_subscription(
                    subscription,
                    plan=transaction_record.target_plan,
                    billing_cycle=transaction_record.billing_cycle,
                    event_metadata={
                        "previous_state": previous_state,
                        "payment_id": transaction_record.payment_id,
                        "invoice_number": transaction_record.invoice_number,
                    },
                )
                transaction_record.subscription = subscription
                transaction_record.trx_id = (
                    response_data.get("trxID") or transaction_record.trx_id
                )
                transaction_record.status = BkashTransaction.Status.COMPLETED
            else:
                transaction_record.status = (
                    remote_status or BkashTransaction.Status.FAILED
                )

            transaction_record.bkash_response = cls._merge_responses(
                transaction_record.bkash_response,
                response_data,
            )
            transaction_record.save(
                update_fields=[
                    "subscription",
                    "trx_id",
                    "status",
                    "bkash_response",
                    "updated_at",
                ]
            )
            return transaction_record

    @classmethod
    def refund_payment(cls, payment_id, *, amount, reason="", sku=""):
        normalized_payment_id = (payment_id or "").strip()
        if not normalized_payment_id:
            raise BkashUserInputError("paymentID is required to issue a refund.")

        transaction_record = (
            BkashTransaction.objects.select_related("subscription", "target_plan", "user")
            .filter(payment_id=normalized_payment_id)
            .first()
        )
        if not transaction_record:
            raise BkashUserInputError("The bKash payment could not be found.")
        if transaction_record.status != BkashTransaction.Status.COMPLETED:
            raise BkashUserInputError("Only completed bKash transactions can be refunded.")
        if transaction_record.refund_status in {
            BkashTransaction.RefundStatus.PENDING,
            BkashTransaction.RefundStatus.COMPLETED,
        }:
            raise BkashUserInputError("This bKash transaction has already been refunded.")
        if not transaction_record.trx_id:
            raise BkashUserInputError("The original bKash transaction ID is missing.")

        refund_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        if refund_amount <= 0:
            raise BkashUserInputError("Refund amount must be greater than zero.")
        if refund_amount > Decimal(transaction_record.amount):
            raise BkashUserInputError("Refund amount cannot exceed the original payment amount.")

        response = cls._authorized_request(
            "POST",
            "/tokenized/checkout/payment/refund",
            payload={
                "paymentID": normalized_payment_id,
                "trxID": transaction_record.trx_id,
                "amount": f"{refund_amount:.2f}",
                "sku": (sku or transaction_record.invoice_number or "").strip(),
                "reason": (reason or "").strip(),
            },
        )
        refund_status = cls._normalize_refund_status(response)
        if refund_status == BkashTransaction.RefundStatus.FAILED:
            raise BkashServiceError(
                cls._extract_error_message(
                    response,
                    default="bKash could not complete the refund request.",
                )
            )

        with transaction.atomic():
            transaction_record = (
                BkashTransaction.objects.select_related("target_plan", "user")
                .select_for_update()
                .get(pk=transaction_record.pk)
            )
            if transaction_record.refund_status in {
                BkashTransaction.RefundStatus.PENDING,
                BkashTransaction.RefundStatus.COMPLETED,
            }:
                raise BkashUserInputError("This bKash transaction has already been refunded.")

            transaction_record.refund_status = refund_status
            transaction_record.refund_amount = refund_amount
            transaction_record.refund_reason = (reason or "").strip()
            transaction_record.refund_sku = (sku or transaction_record.invoice_number or "").strip()
            transaction_record.refund_requested_at = timezone.now()
            transaction_record.refunded_at = (
                timezone.now()
                if refund_status == BkashTransaction.RefundStatus.COMPLETED
                else None
            )
            transaction_record.refund_trx_id = (
                response.get("refundTrxID") or transaction_record.refund_trx_id
            )
            transaction_record.refund_response = cls._merge_responses(
                transaction_record.refund_response,
                cls._sanitize_response(response),
            )
            transaction_record.save(
                update_fields=[
                    "refund_status",
                    "refund_amount",
                    "refund_reason",
                    "refund_sku",
                    "refund_requested_at",
                    "refunded_at",
                    "refund_trx_id",
                    "refund_response",
                    "updated_at",
                ]
            )

            if (
                refund_status == BkashTransaction.RefundStatus.COMPLETED
                and refund_amount == Decimal(transaction_record.amount)
                and transaction_record.subscription_id
            ):
                subscription = UserSubscription.objects.select_for_update().get(
                    pk=transaction_record.subscription_id
                )
                if (
                    subscription.payment_provider == UserSubscription.PaymentProvider.BKASH
                    and subscription.plan_id == transaction_record.target_plan_id
                ):
                    previous_state = LicenseService.serialize_subscription_state(subscription)
                    LicenseService.downgrade_to_free(
                        subscription,
                        event_type=SubscriptionEvent.EventType.BKASH_REFUNDED,
                        event_metadata={
                            "previous_state": previous_state,
                            "payment_id": transaction_record.payment_id,
                            "refund_trx_id": transaction_record.refund_trx_id or "",
                        },
                    )

            return transaction_record
