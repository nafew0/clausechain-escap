from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Plan
from .serializers import PlanSerializer, UserSubscriptionSerializer
from .services import LicenseService


class PlanListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        return Plan.objects.filter(is_active=True).order_by("tier")


class CurrentSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = LicenseService.get_user_subscription(request.user)
        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)


class SubscriptionUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(LicenseService.get_usage_snapshot(request.user))


class SubscriptionCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        with transaction.atomic():
            subscription = LicenseService.get_user_subscription(
                request.user, for_update=True
            )

            if not LicenseService.is_subscription_paid_and_active(subscription):
                return Response(
                    {"detail": "There is no active paid subscription to cancel."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if subscription.payment_provider == subscription.PaymentProvider.STRIPE:
                return Response(
                    {
                        "detail": "Stripe-managed subscriptions must be canceled from the billing portal.",
                        "code": "stripe_customer_portal_required",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if subscription.payment_provider != subscription.PaymentProvider.BKASH:
                return Response(
                    {"detail": "This subscription cannot be canceled from here."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            LicenseService.cancel_bkash_subscription_at_period_end(subscription)
            serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data, status=status.HTTP_200_OK)
