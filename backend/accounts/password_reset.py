import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .branding import resolve_branding_asset_url
from .models import User
from .verification import get_site_settings

logger = logging.getLogger(__name__)

PASSWORD_RESET_EMAIL_COOLDOWN_SECONDS = 120
PUBLIC_PASSWORD_RESET_WINDOW_SECONDS = 15 * 60
PUBLIC_PASSWORD_RESET_MAX_ATTEMPTS = 10


def build_password_reset_link(user):
    public_app_url = (getattr(settings, "PUBLIC_APP_URL", "") or "").rstrip("/")
    if not public_app_url:
        raise ImproperlyConfigured(
            "PUBLIC_APP_URL must be configured for password reset emails."
        )

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{public_app_url}/reset-password?uid={uid}&token={token}", uid, token


def resolve_password_reset_user(uid):
    if not uid:
        return None

    try:
        user_id = urlsafe_base64_decode(uid).decode()
    except (TypeError, ValueError, OverflowError):
        return None

    return User.objects.filter(pk=user_id, is_active=True).first()


def is_password_reset_token_valid(uid, token):
    user = resolve_password_reset_user(uid)
    if not user or not token:
        return None

    if not default_token_generator.check_token(user, token):
        return None
    return user


def send_password_reset_email(user, *, requested_by=None):
    reset_url, uid, token = build_password_reset_link(user)
    public_app_url = (getattr(settings, "PUBLIC_APP_URL", "") or "").rstrip("/")
    logo_url = resolve_branding_asset_url(
        get_site_settings(),
        "branding_logo",
        public_app_url=public_app_url,
    )
    context = {
        "user": user,
        "reset_url": reset_url,
        "requested_by": requested_by,
        "logo_url": logo_url,
    }
    subject = "Reset your reactdjango password"
    html_body = render_to_string("emails/password_reset.html", context)
    text_body = strip_tags(html_body)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
    mark_password_reset_sent(user)
    return {"uid": uid, "token": token, "reset_url": reset_url}


def get_password_reset_cache_key(user):
    return f"accounts:password-reset:user:{user.pk}"


def get_public_password_reset_cache_key(ip_address):
    return f"accounts:password-reset:public:{ip_address or 'unknown'}"


def get_password_reset_retry_after_seconds(user):
    cache_key = get_password_reset_cache_key(user)
    try:
        sent_at = cache.get(cache_key)
    except Exception:
        logger.warning("Password reset cooldown cache unavailable.", exc_info=True)
        return 0

    if not sent_at:
        return 0

    remaining = PASSWORD_RESET_EMAIL_COOLDOWN_SECONDS - int(timezone.now().timestamp() - sent_at)
    return max(remaining, 0)


def mark_password_reset_sent(user):
    try:
        cache.set(
            get_password_reset_cache_key(user),
            int(timezone.now().timestamp()),
            timeout=PASSWORD_RESET_EMAIL_COOLDOWN_SECONDS,
        )
    except Exception:
        logger.warning("Password reset cooldown cache unavailable.", exc_info=True)


def should_throttle_public_password_reset(ip_address):
    cache_key = get_public_password_reset_cache_key(ip_address)

    try:
        added = cache.add(cache_key, 1, timeout=PUBLIC_PASSWORD_RESET_WINDOW_SECONDS)
        if added:
            return False
        attempts = cache.incr(cache_key)
        return attempts > PUBLIC_PASSWORD_RESET_MAX_ATTEMPTS
    except Exception:
        logger.warning("Public password reset throttle unavailable.", exc_info=True)
        return False


def get_public_password_reset_user(identifier):
    normalized = (identifier or "").strip()
    if not normalized:
        return None

    return (
        User.objects.filter(
            is_active=True,
        )
        .filter(models.Q(username__iexact=normalized) | models.Q(email__iexact=normalized))
        .first()
    )
