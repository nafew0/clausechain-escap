import logging
import random
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from .verification import get_site_settings

logger = logging.getLogger(__name__)

GENERIC_SIGNUP_FAILURE_MESSAGE = (
    "Registration could not be completed. Please refresh the form and try again."
)
CAPTCHA_SALT = "accounts.signup.captcha"
SIGNUP_FORM_SALT = "accounts.signup.form"
DISPOSABLE_DOMAINS_PATH = Path(__file__).resolve().parent / "data" / "disposable_email_domains.txt"


def get_signup_captcha_cache_key(captcha_id):
    return f"accounts:signup:captcha:{captcha_id}"


def get_signup_captcha_ttl_seconds():
    return max(int(getattr(settings, "SIGNUP_CAPTCHA_TTL_SECONDS", 600)), 60)


def get_signup_form_min_age_seconds():
    return max(int(getattr(settings, "SIGNUP_FORM_MIN_AGE_SECONDS", 3)), 0)


def get_signup_form_max_age_seconds():
    return max(int(getattr(settings, "SIGNUP_FORM_MAX_AGE_SECONDS", 3600)), 60)


def build_registration_token(*, issued_at=None):
    issued_timestamp = int((issued_at or timezone.now()).timestamp())
    return signing.dumps(
        {
            "nonce": uuid.uuid4().hex,
            "issued_at": issued_timestamp,
        },
        salt=SIGNUP_FORM_SALT,
    )


def build_signup_captcha_challenge():
    left = random.randint(1, 9)
    operator = random.choice(["+", "-"])
    if operator == "-":
        right = random.randint(0, left)
        answer = left - right
    else:
        right = random.randint(0, 9)
        answer = left + right

    captcha_id = signing.dumps(
        {
            "id": uuid.uuid4().hex,
            "operator": operator,
        },
        salt=CAPTCHA_SALT,
    )

    cache_key = get_signup_captcha_cache_key(captcha_id)
    try:
        cache.set(cache_key, str(answer), timeout=get_signup_captcha_ttl_seconds())
        if cache.get(cache_key) != str(answer):
            raise RuntimeError("captcha cache store failed")
    except Exception as exc:  # pragma: no cover - depends on cache backend failure
        logger.warning("Signup captcha cache unavailable.", exc_info=True)
        raise RuntimeError("Signup protection is temporarily unavailable.") from exc

    return {
        "captcha_id": captcha_id,
        "captcha_prompt": f"What is {left} {operator} {right}?",
    }


def get_signup_challenge_payload(site_settings_obj=None):
    site_settings_obj = site_settings_obj or get_site_settings()
    payload = {
        "captcha_enabled": bool(site_settings_obj.signup_captcha_enabled),
        "registration_token": build_registration_token(),
        "minimum_submit_seconds": get_signup_form_min_age_seconds(),
    }

    if not site_settings_obj.signup_captcha_enabled:
        payload.update({"captcha_id": "", "captcha_prompt": ""})
        return payload

    payload.update(build_signup_captcha_challenge())
    return payload


def validate_signup_request_token(registration_token):
    if not (registration_token or "").strip():
        raise ValueError(GENERIC_SIGNUP_FAILURE_MESSAGE)

    try:
        payload = signing.loads(
            registration_token,
            salt=SIGNUP_FORM_SALT,
            max_age=get_signup_form_max_age_seconds(),
        )
    except signing.BadSignature as exc:
        raise ValueError(GENERIC_SIGNUP_FAILURE_MESSAGE) from exc

    issued_at = int(payload.get("issued_at") or 0)
    elapsed_seconds = int(timezone.now().timestamp()) - issued_at
    if issued_at <= 0 or elapsed_seconds < get_signup_form_min_age_seconds():
        raise ValueError(GENERIC_SIGNUP_FAILURE_MESSAGE)


def validate_signup_captcha(site_settings_obj, *, captcha_id, captcha_answer):
    if not site_settings_obj.signup_captcha_enabled:
        return

    normalized_captcha_id = (captcha_id or "").strip()
    normalized_answer = (captcha_answer or "").strip()
    if not normalized_captcha_id or not normalized_answer:
        raise ValueError("Complete the CAPTCHA challenge before registering.")

    cache_key = get_signup_captcha_cache_key(normalized_captcha_id)
    try:
        expected_answer = cache.get(cache_key)
    except Exception as exc:  # pragma: no cover - depends on cache backend failure
        logger.warning("Signup captcha cache unavailable.", exc_info=True)
        raise ValueError("Signup protection is temporarily unavailable.") from exc
    finally:
        try:
            cache.delete(cache_key)
        except Exception:
            logger.warning("Signup captcha cache cleanup failed.", exc_info=True)

    if expected_answer is None:
        raise ValueError("This CAPTCHA challenge expired. Refresh it and try again.")

    if normalized_answer != str(expected_answer).strip():
        raise ValueError("Incorrect CAPTCHA answer. Refresh the challenge and try again.")


def get_normalized_email_domain(email):
    normalized_email = (email or "").strip()
    if "@" not in normalized_email:
        return ""
    return normalized_email.rsplit("@", 1)[-1].strip().lower()


@lru_cache(maxsize=1)
def get_bundled_disposable_email_domains():
    if not DISPOSABLE_DOMAINS_PATH.exists():
        return frozenset()

    with DISPOSABLE_DOMAINS_PATH.open("r", encoding="utf-8") as source:
        return frozenset(
            line.strip().lower()
            for line in source
            if line.strip() and not line.lstrip().startswith("#")
        )


def is_disposable_email_domain(email):
    domain = get_normalized_email_domain(email)
    if not domain:
        return False

    allowed_domains = {
        value.strip().lower()
        for value in getattr(settings, "SIGNUP_DISPOSABLE_EMAIL_ALLOWLIST", [])
        if value and value.strip()
    }
    if domain in allowed_domains:
        return False

    blocked_domains = set(get_bundled_disposable_email_domains())
    blocked_domains.update(
        value.strip().lower()
        for value in getattr(settings, "SIGNUP_DISPOSABLE_EMAIL_BLOCKLIST", [])
        if value and value.strip()
    )
    return domain in blocked_domains
