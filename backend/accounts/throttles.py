import hashlib
import re

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from rest_framework.throttling import SimpleRateThrottle

from .models import (
    DEFAULT_SIGNUP_BURST_LIMIT,
    DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT,
    DEFAULT_SIGNUP_SUSTAINED_LIMIT,
    SiteSettings,
)
from .verification import get_request_ip_address

SIGNUP_LIMIT_DEFAULTS = {
    "signup_burst_limit": DEFAULT_SIGNUP_BURST_LIMIT,
    "signup_short_window_limit": DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT,
    "signup_sustained_limit": DEFAULT_SIGNUP_SUSTAINED_LIMIT,
}


def _hash_identifier(value):
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class LoginRateThrottle(SimpleRateThrottle):
    rate = "10/min"
    scope = "public_login"

    def get_cache_key(self, request, view):
        identifier = _hash_identifier(
            request.data.get("username") or request.data.get("identifier") or ""
        )
        client_ip = get_request_ip_address(request) or "unknown"
        ident = f"{client_ip}:{identifier}" if identifier else client_ip
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class VariableWindowRateThrottle(SimpleRateThrottle):
    rate = None
    default_rate = None
    rate_setting = ""
    rate_limit_field = ""
    rate_window = ""

    def __init__(self):
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def get_rate(self):
        if self.rate_limit_field and self.rate_window:
            configured_limit = self.get_site_settings_limit()
            if configured_limit:
                return f"{configured_limit}/{self.rate_window}"

        configured_rate = (
            getattr(settings, self.rate_setting, "").strip()
            if self.rate_setting
            else ""
        )
        return configured_rate or self.default_rate

    def get_site_settings_limit(self):
        if not self.rate_limit_field:
            return None

        default_limit = SIGNUP_LIMIT_DEFAULTS.get(self.rate_limit_field)

        try:
            configured_limit = (
                SiteSettings.objects.filter(pk=1)
                .values_list(self.rate_limit_field, flat=True)
                .first()
            )
        except (OperationalError, ProgrammingError):
            return default_limit

        if isinstance(configured_limit, int) and configured_limit > 0:
            return configured_limit
        return default_limit

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)

        num_requests, period = rate.split("/")
        match = re.fullmatch(r"(?:(\d+))?([smhd])", period.strip().lower())
        if not match:
            return super().parse_rate(rate)

        multiplier = int(match.group(1) or "1")
        unit = match.group(2)
        duration = {
            "s": 1,
            "m": 60,
            "h": 60 * 60,
            "d": 60 * 60 * 24,
        }[unit] * multiplier
        return int(num_requests), duration


class RegisterIPRateThrottle(VariableWindowRateThrottle):
    def get_cache_key(self, request, view):
        client_ip = get_request_ip_address(request) or "unknown"
        return self.cache_format % {
            "scope": self.scope,
            "ident": client_ip,
        }


class RegisterBurstRateThrottle(RegisterIPRateThrottle):
    scope = "public_register_burst"
    default_rate = "1/15s"
    rate_limit_field = "signup_burst_limit"
    rate_window = "15s"


class RegisterShortWindowRateThrottle(RegisterIPRateThrottle):
    scope = "public_register_short_window"
    default_rate = "3/10m"
    rate_limit_field = "signup_short_window_limit"
    rate_window = "10m"


class RegisterSustainedRateThrottle(RegisterIPRateThrottle):
    scope = "public_register_sustained"
    default_rate = "10/h"
    rate_limit_field = "signup_sustained_limit"
    rate_window = "1h"


class SocialLoginRateThrottle(VariableWindowRateThrottle):
    scope = "public_social_login"
    default_rate = "10/min"

    def get_cache_key(self, request, view):
        client_ip = get_request_ip_address(request) or "unknown"
        return self.cache_format % {
            "scope": self.scope,
            "ident": client_ip,
        }


class AdminRateThrottle(VariableWindowRateThrottle):
    scope = "admin_api"
    default_rate = "100/hour"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }
