from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

from clausechain.client_ip import get_client_ip


class PaymentCheckoutThrottle(SimpleRateThrottle):
    scope = "payment_checkout"
    rate = "10/hour"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


class PaymentStatusThrottle(SimpleRateThrottle):
    scope = "payment_status"
    rate = "60/hour"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


BKASH_CALLBACK_WINDOW_SECONDS = 60 * 60
BKASH_CALLBACK_MAX_ATTEMPTS = 30


def get_bkash_callback_cache_key(ip_address):
    return f"subscriptions:bkash-callback:{ip_address or 'unknown'}"


def should_throttle_bkash_callback(ip_address):
    cache_key = get_bkash_callback_cache_key(ip_address)

    try:
        added = cache.add(cache_key, 1, timeout=BKASH_CALLBACK_WINDOW_SECONDS)
        if added:
            return False

        attempts = cache.incr(cache_key)
        return attempts > BKASH_CALLBACK_MAX_ATTEMPTS
    except Exception:
        return False


def get_bkash_callback_ip(request):
    return get_client_ip(request)
