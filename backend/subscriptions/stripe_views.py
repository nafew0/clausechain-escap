import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from clausechain.audit import log_audit_event
from .models import Plan
from .serializers import StripeCheckoutSessionSerializer, UserSubscriptionSerializer
from .stripe_service import (
    StripeCheckoutConflictError,
    StripeConfigurationError,
    StripeService,
    StripeServiceError,
    StripeUserInputError,
    StripeWebhookSignatureError,
)
from .throttles import PaymentCheckoutThrottle, PaymentStatusThrottle

logger = logging.getLogger(__name__)


class StripeConfigView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings

        return Response({"publishable_key": settings.STRIPE_PUBLISHABLE_KEY})


class StripeCheckoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentCheckoutThrottle]

    def post(self, request):
        serializer = StripeCheckoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = get_object_or_404(
            Plan.objects.filter(is_active=True),
            pk=serializer.validated_data["plan_id"],
        )

        try:
            checkout_url = StripeService.create_checkout_session(
                request.user,
                plan,
                serializer.validated_data["billing_cycle"],
            )
        except StripeCheckoutConflictError as exc:
            log_audit_event(
                "stripe_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=serializer.validated_data["plan_id"],
                billing_cycle=serializer.validated_data["billing_cycle"],
                reason="checkout_conflict",
            )
            return Response(
                {
                    "detail": str(exc),
                    "requires_customer_portal": exc.requires_customer_portal,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except StripeConfigurationError as exc:
            log_audit_event(
                "stripe_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=serializer.validated_data["plan_id"],
                billing_cycle=serializer.validated_data["billing_cycle"],
                reason="stripe_not_configured",
            )
            return Response(
                {"detail": str(exc), "code": "stripe_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripeUserInputError as exc:
            log_audit_event(
                "stripe_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=serializer.validated_data["plan_id"],
                billing_cycle=serializer.validated_data["billing_cycle"],
                reason="invalid_request",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StripeServiceError as exc:
            log_audit_event(
                "stripe_checkout",
                outcome="failure",
                level="warning",
                request=request,
                plan_id=serializer.validated_data["plan_id"],
                billing_cycle=serializer.validated_data["billing_cycle"],
                reason="provider_error",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        log_audit_event(
            "stripe_checkout",
            request=request,
            plan_id=str(plan.pk),
            billing_cycle=serializer.validated_data["billing_cycle"],
        )
        return Response({"checkout_url": checkout_url}, status=status.HTTP_200_OK)


class StripeCustomerPortalView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentCheckoutThrottle]

    def post(self, request):
        try:
            portal_url = StripeService.create_customer_portal_session(request.user)
        except StripeConfigurationError as exc:
            log_audit_event(
                "stripe_customer_portal",
                outcome="failure",
                level="warning",
                request=request,
                reason="stripe_not_configured",
            )
            return Response(
                {"detail": str(exc), "code": "stripe_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripeUserInputError as exc:
            log_audit_event(
                "stripe_customer_portal",
                outcome="failure",
                level="warning",
                request=request,
                reason="invalid_request",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StripeServiceError as exc:
            log_audit_event(
                "stripe_customer_portal",
                outcome="failure",
                level="warning",
                request=request,
                reason="provider_error",
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit_event("stripe_customer_portal", request=request)
        return Response({"portal_url": portal_url}, status=status.HTTP_200_OK)


class StripeCheckoutSessionStatusView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentStatusThrottle]

    def get(self, request, session_id):
        try:
            result = StripeService.sync_checkout_session(request.user, session_id)
        except StripeConfigurationError as exc:
            log_audit_event(
                "stripe_checkout_session_status",
                outcome="failure",
                level="warning",
                request=request,
                reason="stripe_not_configured",
                session_id=session_id,
            )
            return Response(
                {"detail": str(exc), "code": "stripe_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripeUserInputError as exc:
            log_audit_event(
                "stripe_checkout_session_status",
                outcome="failure",
                level="warning",
                request=request,
                reason="invalid_request",
                session_id=session_id,
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StripeServiceError as exc:
            log_audit_event(
                "stripe_checkout_session_status",
                outcome="failure",
                level="warning",
                request=request,
                reason="provider_error",
                session_id=session_id,
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        log_audit_event(
            "stripe_checkout_session_status",
            request=request,
            session_id=session_id,
            completed=result["completed"],
            payment_status=result["payment_status"],
            session_status=result["session_status"],
        )
        response_payload = {
            "completed": result["completed"],
            "session_status": result["session_status"],
            "payment_status": result["payment_status"],
            "subscription": UserSubscriptionSerializer(result["subscription"]).data,
        }
        return Response(response_payload, status=status.HTTP_200_OK)


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    try:
        StripeService.handle_webhook(
            request.body,
            request.headers.get("Stripe-Signature", ""),
        )
    except StripeWebhookSignatureError:
        return HttpResponse(status=400)
    except StripeConfigurationError:
        logger.exception("Stripe webhook received before Stripe was fully configured.")
        return HttpResponse(status=503)
    except StripeServiceError:
        logger.exception("Stripe webhook processing failed.")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
