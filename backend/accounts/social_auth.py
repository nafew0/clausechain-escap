import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import UserSocialAccount
from .verification import (
    get_site_settings,
    get_user_verification_retry_after_seconds,
    mask_email,
    send_verification_email,
)

User = get_user_model()

DEFAULT_SOCIAL_NEXT_PATH = "/dashboard"
SOCIAL_PROVIDER_LABELS = {
    UserSocialAccount.Provider.GOOGLE: "Google",
    UserSocialAccount.Provider.FACEBOOK: "Facebook",
    UserSocialAccount.Provider.GITHUB: "GitHub",
}
SOCIAL_PROVIDER_SETTINGS_FIELDS = {
    UserSocialAccount.Provider.GOOGLE: "social_login_google_enabled",
    UserSocialAccount.Provider.FACEBOOK: "social_login_facebook_enabled",
    UserSocialAccount.Provider.GITHUB: "social_login_github_enabled",
}
SOCIAL_TRUSTED_EMAIL_PROVIDERS = {
    UserSocialAccount.Provider.GOOGLE,
    UserSocialAccount.Provider.GITHUB,
}
USERNAME_ALLOWED_PATTERN = re.compile(r"[^A-Za-z0-9@.+_-]+")


class SocialAuthException(Exception):
    default_code = "social_auth_error"

    def __init__(self, detail, *, code=None):
        super().__init__(detail)
        self.detail = detail
        self.code = code or self.default_code


class SocialProviderUnsupported(SocialAuthException):
    default_code = "unsupported_provider"


class SocialProviderDisabled(SocialAuthException):
    default_code = "provider_disabled"


class SocialProviderNotConfigured(SocialAuthException):
    default_code = "provider_not_configured"


class SocialAuthStateError(SocialAuthException):
    default_code = "invalid_state"


class SocialAuthConflictError(SocialAuthException):
    default_code = "account_conflict"


class SocialAuthEmailError(SocialAuthException):
    default_code = "email_required"


@dataclass
class SocialProviderStatus:
    id: str
    name: str
    enabled: bool
    configured: bool
    available: bool
    source: str = "environment"


@dataclass
class SocialIdentity:
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    display_name: str
    first_name: str = ""
    last_name: str = ""
    avatar_url: str = ""


@dataclass
class SocialLoginResult:
    status: str
    provider: str
    user: User | None
    frontend_origin: str
    next_path: str
    detail: str = ""
    email_hint: str = ""


def normalize_provider(provider):
    normalized = (provider or "").strip().lower()
    if normalized not in SOCIAL_PROVIDER_LABELS:
        raise SocialProviderUnsupported("Unsupported social login provider.")
    return normalized


def sanitize_next_path(value):
    normalized = (value or "").strip()
    if not normalized:
        return DEFAULT_SOCIAL_NEXT_PATH

    parsed = urlparse(normalized)
    if parsed.scheme or parsed.netloc or not normalized.startswith("/"):
        return DEFAULT_SOCIAL_NEXT_PATH
    if normalized.startswith("//"):
        return DEFAULT_SOCIAL_NEXT_PATH
    return normalized


def get_social_provider_statuses(site_settings_obj=None):
    settings_obj = site_settings_obj or get_site_settings()
    statuses = []
    for provider, label in SOCIAL_PROVIDER_LABELS.items():
        enabled = bool(getattr(settings_obj, SOCIAL_PROVIDER_SETTINGS_FIELDS[provider]))
        configured = is_provider_configured(provider)
        statuses.append(
            SocialProviderStatus(
                id=provider,
                name=label,
                enabled=enabled,
                configured=configured,
                available=enabled and configured,
            )
        )
    return statuses


def get_social_provider_status(provider, site_settings_obj=None):
    normalized = normalize_provider(provider)
    for status in get_social_provider_statuses(site_settings_obj):
        if status.id == normalized:
            return status
    raise SocialProviderUnsupported("Unsupported social login provider.")


def get_default_frontend_origin():
    origins = getattr(settings, "SOCIAL_AUTH_ALLOWED_FRONTEND_ORIGINS", [])
    return (origins[0] if origins else "").rstrip("/")


def extract_request_origin(request):
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    if origin:
        return origin

    referer = (request.headers.get("Referer") or "").strip()
    if not referer:
        return ""

    parsed = urlparse(referer)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return ""


def validate_frontend_origin(request):
    origin = extract_request_origin(request)
    allowed_origins = {
        item.rstrip("/")
        for item in getattr(settings, "SOCIAL_AUTH_ALLOWED_FRONTEND_ORIGINS", [])
        if item
    }
    if not origin or origin not in allowed_origins:
        raise SocialAuthException(
            "This request origin is not allowed to start social login.",
            code="invalid_origin",
        )
    return origin


def is_provider_configured(provider):
    normalized = normalize_provider(provider)
    credentials = get_provider_credentials(normalized)
    return bool(credentials["client_id"] and credentials["client_secret"])


def get_provider_credentials(provider):
    normalized = normalize_provider(provider)
    credential_mapping = {
        UserSocialAccount.Provider.GOOGLE: {
            "client_id": getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "").strip(),
            "client_secret": getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        },
        UserSocialAccount.Provider.FACEBOOK: {
            "client_id": getattr(settings, "FACEBOOK_OAUTH_CLIENT_ID", "").strip(),
            "client_secret": getattr(settings, "FACEBOOK_OAUTH_CLIENT_SECRET", "").strip(),
        },
        UserSocialAccount.Provider.GITHUB: {
            "client_id": getattr(settings, "GITHUB_OAUTH_CLIENT_ID", "").strip(),
            "client_secret": getattr(settings, "GITHUB_OAUTH_CLIENT_SECRET", "").strip(),
        },
    }
    return credential_mapping[normalized]


def ensure_provider_available(provider, site_settings_obj=None):
    status = get_social_provider_status(provider, site_settings_obj)
    if not status.enabled:
        raise SocialProviderDisabled(f"{status.name} login is disabled.")
    if not status.configured:
        raise SocialProviderNotConfigured(
            f"{status.name} login is not configured on the server."
        )
    return status


def get_oauth_client(provider):
    normalized = normalize_provider(provider)
    credentials = get_provider_credentials(normalized)
    oauth = OAuth()
    if normalized == UserSocialAccount.Provider.GOOGLE:
        oauth.register(
            name=normalized,
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
            code_challenge_method="S256",
        )
    elif normalized == UserSocialAccount.Provider.GITHUB:
        oauth.register(
            name=normalized,
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            api_base_url="https://api.github.com/",
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            client_kwargs={"scope": "read:user user:email"},
        )
    elif normalized == UserSocialAccount.Provider.FACEBOOK:
        version = getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "v25.0").strip()
        oauth.register(
            name=normalized,
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            api_base_url=f"https://graph.facebook.com/{version}/",
            access_token_url=f"https://graph.facebook.com/{version}/oauth/access_token",
            authorize_url=f"https://www.facebook.com/{version}/dialog/oauth",
            client_kwargs={"scope": "email public_profile"},
        )
    return oauth.create_client(normalized)


def build_social_authorization(request, provider, next_path):
    normalized = normalize_provider(provider)
    ensure_provider_available(normalized)
    frontend_origin = validate_frontend_origin(request)
    next_path = sanitize_next_path(next_path)
    client = get_oauth_client(normalized)
    redirect_uri = request.build_absolute_uri(
        reverse("accounts:social_callback", kwargs={"provider": normalized})
    )
    authorize_kwargs = {}
    if normalized == UserSocialAccount.Provider.GOOGLE:
        authorize_kwargs["prompt"] = "select_account"

    authorization = client.create_authorization_url(redirect_uri, **authorize_kwargs)
    client.save_authorize_data(
        request,
        redirect_uri=redirect_uri,
        frontend_origin=frontend_origin,
        next_path=next_path,
        **authorization,
    )
    request.session.modified = True
    return {
        "authorization_url": authorization["url"],
        "provider": normalized,
        "next_path": next_path,
    }


def get_callback_state_data(request, provider):
    normalized = normalize_provider(provider)
    state = (
        request.GET.get("state")
        or request.POST.get("state")
        or ""
    ).strip()
    if not state:
        raise SocialAuthStateError("The social login session is missing or invalid.")

    client = get_oauth_client(normalized)
    state_data = client.framework.get_state_data(request.session, state)
    if not state_data:
        raise SocialAuthStateError("The social login session has expired or is invalid.")

    frontend_origin = (state_data.get("frontend_origin") or "").rstrip("/")
    if not frontend_origin:
        frontend_origin = get_default_frontend_origin()

    return client, state_data, frontend_origin, sanitize_next_path(
        state_data.get("next_path")
    )


def complete_social_login(request, provider):
    normalized = normalize_provider(provider)
    client, _, frontend_origin, next_path = get_callback_state_data(
        request,
        normalized,
    )
    token = client.authorize_access_token(request)
    identity = fetch_social_identity(normalized, client, token)
    return resolve_social_login(
        identity,
        frontend_origin=frontend_origin,
        next_path=next_path,
    )


def fetch_social_identity(provider, client, token):
    normalized = normalize_provider(provider)
    if normalized == UserSocialAccount.Provider.GOOGLE:
        return fetch_google_identity(client, token)
    if normalized == UserSocialAccount.Provider.GITHUB:
        return fetch_github_identity(client, token)
    if normalized == UserSocialAccount.Provider.FACEBOOK:
        return fetch_facebook_identity(client, token)
    raise SocialProviderUnsupported("Unsupported social login provider.")


def fetch_google_identity(client, token):
    userinfo = token.get("userinfo")
    if not userinfo:
        response = client.get("userinfo", token=token)
        response.raise_for_status()
        userinfo = response.json()

    provider_user_id = str(userinfo.get("sub") or "").strip()
    email = (userinfo.get("email") or "").strip().lower()
    email_verified = bool(userinfo.get("email_verified"))
    if not provider_user_id or not email or not email_verified:
        raise SocialAuthEmailError(
            "Google did not return a verified email address for this account."
        )

    return SocialIdentity(
        provider=UserSocialAccount.Provider.GOOGLE,
        provider_user_id=provider_user_id,
        email=email,
        email_verified=True,
        display_name=(userinfo.get("name") or email).strip(),
        first_name=(userinfo.get("given_name") or "").strip(),
        last_name=(userinfo.get("family_name") or "").strip(),
        avatar_url=(userinfo.get("picture") or "").strip(),
    )


def fetch_github_identity(client, token):
    headers = {"Accept": "application/vnd.github+json"}
    profile_response = client.get("user", token=token, headers=headers)
    profile_response.raise_for_status()
    profile = profile_response.json()

    emails_response = client.get("user/emails", token=token, headers=headers)
    emails_response.raise_for_status()
    emails = emails_response.json()

    email = select_verified_github_email(emails)
    if not email:
        raise SocialAuthEmailError(
            "GitHub did not return a verified email address for this account."
        )

    provider_user_id = str(profile.get("id") or "").strip()
    if not provider_user_id:
        raise SocialAuthException(
            "GitHub did not return a valid account identifier.",
            code="provider_profile_invalid",
        )

    first_name, last_name = split_name((profile.get("name") or "").strip())
    display_name = (
        (profile.get("name") or "").strip()
        or (profile.get("login") or "").strip()
        or email
    )
    return SocialIdentity(
        provider=UserSocialAccount.Provider.GITHUB,
        provider_user_id=provider_user_id,
        email=email,
        email_verified=True,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        avatar_url=(profile.get("avatar_url") or "").strip(),
    )


def fetch_facebook_identity(client, token):
    response = client.get(
        "me",
        token=token,
        params={"fields": "id,name,first_name,last_name,email,picture.type(large)"},
    )
    response.raise_for_status()
    profile = response.json()

    provider_user_id = str(profile.get("id") or "").strip()
    email = (profile.get("email") or "").strip().lower()
    if not provider_user_id or not email:
        raise SocialAuthEmailError(
            "Facebook did not return an email address for this account."
        )

    picture = profile.get("picture") or {}
    picture_data = picture.get("data") or {}
    return SocialIdentity(
        provider=UserSocialAccount.Provider.FACEBOOK,
        provider_user_id=provider_user_id,
        email=email,
        email_verified=False,
        display_name=(profile.get("name") or email).strip(),
        first_name=(profile.get("first_name") or "").strip(),
        last_name=(profile.get("last_name") or "").strip(),
        avatar_url=(picture_data.get("url") or "").strip(),
    )


def select_verified_github_email(emails):
    normalized_emails = [
        item
        for item in emails
        if isinstance(item, dict)
        and item.get("email")
        and item.get("verified")
    ]
    if not normalized_emails:
        return ""

    primary_email = next(
        (item["email"] for item in normalized_emails if item.get("primary")),
        None,
    )
    selected = primary_email or normalized_emails[0]["email"]
    return selected.strip().lower()


def split_name(value):
    normalized = (value or "").strip()
    if not normalized:
        return "", ""
    parts = normalized.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def resolve_social_login(identity, *, frontend_origin, next_path):
    with transaction.atomic():
        social_account = (
            UserSocialAccount.objects.select_related("user")
            .filter(
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
            )
            .first()
        )
        if social_account:
            user = social_account.user
            ensure_user_is_eligible(user)
            populate_user_from_identity(user, identity)
            if identity.provider in SOCIAL_TRUSTED_EMAIL_PROVIDERS:
                mark_user_email_verified(user)
                update_social_account(
                    social_account,
                    identity,
                    is_active=True,
                    email_verified=True,
                    last_login=True,
                )
                return SocialLoginResult(
                    status="success",
                    provider=identity.provider,
                    user=user,
                    frontend_origin=frontend_origin,
                    next_path=next_path,
                )

            if user.email_verified:
                update_social_account(
                    social_account,
                    identity,
                    is_active=True,
                    email_verified=True,
                    last_login=True,
                )
                return SocialLoginResult(
                    status="success",
                    provider=identity.provider,
                    user=user,
                    frontend_origin=frontend_origin,
                    next_path=next_path,
                )

            update_social_account(
                social_account,
                identity,
                is_active=False,
                email_verified=False,
                last_login=False,
            )
            ensure_verification_email(user)
            return SocialLoginResult(
                status="verification_required",
                provider=identity.provider,
                user=user,
                frontend_origin=frontend_origin,
                next_path=next_path,
                detail=(
                    "Verify your email address to finish connecting your Facebook "
                    "account."
                ),
                email_hint=mask_email(user.email),
            )

        if identity.provider in SOCIAL_TRUSTED_EMAIL_PROVIDERS:
            user = get_or_create_user_from_verified_identity(identity)
            update_social_account(
                get_or_create_social_account(user, identity),
                identity,
                is_active=True,
                email_verified=True,
                last_login=True,
            )
            return SocialLoginResult(
                status="success",
                provider=identity.provider,
                user=user,
                frontend_origin=frontend_origin,
                next_path=next_path,
            )

        user = get_or_create_user_for_unverified_identity(identity)
        if user.email_verified:
            update_social_account(
                get_or_create_social_account(user, identity),
                identity,
                is_active=True,
                email_verified=True,
                last_login=True,
            )
            return SocialLoginResult(
                status="success",
                provider=identity.provider,
                user=user,
                frontend_origin=frontend_origin,
                next_path=next_path,
            )

        update_social_account(
            get_or_create_social_account(user, identity),
            identity,
            is_active=False,
            email_verified=False,
            last_login=False,
        )
        ensure_verification_email(user)
        return SocialLoginResult(
            status="verification_required",
            provider=identity.provider,
            user=user,
            frontend_origin=frontend_origin,
            next_path=next_path,
            detail=(
                "Verify your email address to finish connecting your Facebook account."
            ),
            email_hint=mask_email(user.email),
        )


def ensure_user_is_eligible(user):
    if not user.is_active:
        raise SocialAuthConflictError("This account has been disabled.")
    return user


def mark_user_email_verified(user):
    if user.email_verified:
        return user
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    return user


def populate_user_from_identity(user, identity):
    changed_fields = []
    if identity.first_name and not user.first_name:
        user.first_name = identity.first_name
        changed_fields.append("first_name")
    if identity.last_name and not user.last_name:
        user.last_name = identity.last_name
        changed_fields.append("last_name")
    if changed_fields:
        user.save(update_fields=changed_fields)
    return user


def get_or_create_user_from_verified_identity(identity):
    user = User.objects.filter(email__iexact=identity.email).first()
    if user:
        ensure_user_is_eligible(user)
        populate_user_from_identity(user, identity)
        mark_user_email_verified(user)
        return user

    user = User(
        username=generate_unique_username(identity),
        email=identity.email,
        first_name=identity.first_name,
        last_name=identity.last_name,
        email_verified=True,
    )
    user.set_unusable_password()
    user.save()
    return user


def get_or_create_user_for_unverified_identity(identity):
    user = User.objects.filter(email__iexact=identity.email).first()
    if user:
        ensure_user_is_eligible(user)
        populate_user_from_identity(user, identity)
        return user

    user = User(
        username=generate_unique_username(identity),
        email=identity.email,
        first_name=identity.first_name,
        last_name=identity.last_name,
        email_verified=False,
    )
    user.set_unusable_password()
    user.save()
    return user


def generate_unique_username(identity):
    base_candidates = [
        identity.email.split("@", 1)[0] if identity.email else "",
        identity.display_name,
        f"{identity.provider}_{identity.provider_user_id}",
    ]
    for candidate in base_candidates:
        normalized = USERNAME_ALLOWED_PATTERN.sub("-", (candidate or "").strip())
        normalized = normalized.strip("-._+")[:150]
        if normalized:
            return append_unique_suffix(normalized)
    return append_unique_suffix(f"{identity.provider}-user")


def append_unique_suffix(base_value):
    normalized = base_value[:150]
    if not User.objects.filter(username__iexact=normalized).exists():
        return normalized

    counter = 1
    while True:
        suffix = f"-{counter}"
        candidate = f"{normalized[:150 - len(suffix)]}{suffix}"
        if not User.objects.filter(username__iexact=candidate).exists():
            return candidate
        counter += 1


def get_or_create_social_account(user, identity):
    conflicting_account = (
        UserSocialAccount.objects.select_related("user")
        .filter(
            provider=identity.provider,
            provider_user_id=identity.provider_user_id,
        )
        .exclude(user=user)
        .first()
    )
    if conflicting_account:
        raise SocialAuthConflictError(
            f"This {SOCIAL_PROVIDER_LABELS[identity.provider]} account is already linked "
            "to another user."
        )

    social_account = UserSocialAccount.objects.filter(
        user=user,
        provider=identity.provider,
    ).first()
    if social_account and social_account.provider_user_id != identity.provider_user_id:
        raise SocialAuthConflictError(
            f"{SOCIAL_PROVIDER_LABELS[identity.provider]} is already linked for this user."
        )

    return social_account or UserSocialAccount(
        user=user,
        provider=identity.provider,
        provider_user_id=identity.provider_user_id,
    )


def update_social_account(
    social_account,
    identity,
    *,
    is_active,
    email_verified,
    last_login,
):
    social_account.provider_user_id = identity.provider_user_id
    social_account.email = identity.email
    social_account.email_verified = email_verified
    social_account.display_name = identity.display_name
    social_account.avatar_url = identity.avatar_url
    social_account.is_active = is_active
    social_account.last_login_at = timezone.now() if last_login else social_account.last_login_at
    social_account.save()
    return social_account


def ensure_verification_email(user):
    retry_after_seconds = get_user_verification_retry_after_seconds(user)
    if retry_after_seconds <= 0:
        send_verification_email(user)
    return user


def activate_pending_social_accounts(user):
    if not user.email_verified:
        return 0

    activated = 0
    for social_account in user.social_accounts.filter(is_active=False):
        social_account.is_active = True
        social_account.email_verified = True
        social_account.save()
        activated += 1
    return activated


def build_frontend_callback_url(frontend_origin, **params):
    base_origin = (frontend_origin or "").rstrip("/") or get_default_frontend_origin()
    callback_path = getattr(
        settings,
        "SOCIAL_AUTH_FRONTEND_CALLBACK_PATH",
        "/auth/social/callback",
    ).strip()
    callback_path = callback_path if callback_path.startswith("/") else f"/{callback_path}"
    query = urlencode({key: value for key, value in params.items() if value not in {"", None}})
    if not base_origin:
        return ""
    if not query:
        return f"{base_origin}{callback_path}"
    return f"{base_origin}{callback_path}?{query}"
