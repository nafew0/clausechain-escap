import os
import re
import tempfile
from io import BytesIO
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from PIL import Image

from subscriptions.models import BkashTransaction, Plan, SubscriptionEvent, UserSubscription

from .admin import UserAdmin as AccountsUserAdmin
from .admin_views import get_site_settings
from .models import EmailVerificationToken, User, UserSocialAccount
from .social_auth import (
    SocialAuthConflictError,
    SocialAuthEmailError,
    SocialIdentity,
    SocialLoginResult,
    fetch_github_identity,
    resolve_social_login,
)
from .signup_protection import build_registration_token, get_signup_captcha_cache_key
from .token_cookies import get_refresh_cookie_name
from .user_deletion import delete_user_account


class StubResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError("Provider request failed.")

    def json(self):
        return self.payload


class StubGitHubClient:
    def __init__(self, profile, emails):
        self.profile = profile
        self.emails = emails

    def get(self, path, **kwargs):
        if path == "user":
            return StubResponse(self.profile)
        if path == "user/emails":
            return StubResponse(self.emails)
        raise AssertionError(f"Unexpected GitHub path: {path}")


class StubSessionFramework:
    def set_state_data(self, session, state, data):
        session[f"_state_google_{state}"] = {"data": data}


class StubOAuthClient:
    framework = StubSessionFramework()

    def create_authorization_url(self, redirect_uri, **kwargs):
        return {
            "url": "https://provider.example/oauth/authorize",
            "state": "state-123",
            "code_verifier": "verifier-123",
        }

    def save_authorize_data(self, request, **kwargs):
        state = kwargs.pop("state")
        self.framework.set_state_data(request.session, state, kwargs)


def make_uploaded_image(name, *, size=(640, 360), image_format="PNG", color=(91, 45, 98)):
    buffer = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(buffer, format=image_format)
    buffer.seek(0)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type=f"image/{image_format.lower()}",
    )


class AccountsBaseTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.site_settings = get_site_settings()
        self.site_settings.require_email_verification = False
        self.site_settings.signup_captcha_enabled = False
        self.site_settings.signup_disposable_email_blocking_enabled = False
        self.site_settings.signup_burst_limit = 1
        self.site_settings.signup_short_window_limit = 3
        self.site_settings.signup_sustained_limit = 10
        self.site_settings.social_login_google_enabled = False
        self.site_settings.social_login_facebook_enabled = False
        self.site_settings.social_login_github_enabled = False
        self.site_settings.save()

    def get_signup_challenge(self, *, client=None, **extra_headers):
        response = (client or self.client).get(
            "/api/auth/register/captcha/",
            format="json",
            **extra_headers,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def solve_signup_captcha(self, prompt):
        match = re.fullmatch(r"What is (\d+) ([+-]) (\d+)\?", (prompt or "").strip())
        self.assertIsNotNone(match)
        left, operator, right = match.groups()
        if operator == "+":
            return str(int(left) + int(right))
        return str(int(left) - int(right))

    def get_aged_registration_token(self, *, age_seconds):
        issued_at = timezone.now() - timedelta(seconds=age_seconds)
        return build_registration_token(issued_at=issued_at)

    def build_registration_payload(self, *, client=None, challenge=None, **overrides):
        challenge = challenge or self.get_signup_challenge(client=client)
        payload = {
            "username": "verifyme",
            "email": "verifyme@example.com",
            "password": "TestPass123!",
            "password2": "TestPass123!",
            "first_name": "",
            "last_name": "",
            "organization": "",
            "registration_token": challenge["registration_token"],
            "company_website": "",
        }
        if challenge.get("captcha_enabled"):
            payload["captcha_id"] = challenge["captcha_id"]
            payload["captcha_answer"] = self.solve_signup_captcha(
                challenge["captcha_prompt"]
            )
        payload.update(overrides)
        return payload


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_URL="http://localhost:5555",
    SIGNUP_FORM_MIN_AGE_SECONDS=0,
)
class RegistrationAndLoginContractTests(AccountsBaseTestCase):
    def test_registration_returns_access_token_by_default(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["user"]["email_verified"])
        self.assertIn("user", response.data)
        self.assertIn("access_token", response.data)
        self.assertIn(get_refresh_cookie_name(), response.cookies)
        self.assertEqual(len(mail.outbox), 0)

    def test_registration_requires_verification_when_enabled(self):
        self.site_settings.require_email_verification = True
        self.site_settings.save(update_fields=["require_email_verification"])

        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                username="autologin",
                email="autologin@example.com",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["email_verification_required"])
        self.assertNotIn("access_token", response.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_login_success_returns_access_token_and_refresh_cookie(self):
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
            email_verified=True,
        )

        response = self.client.post(
            "/api/auth/login/",
            {"username": user.email, "password": "TestPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("user", response.data)
        self.assertFalse(response.data["user"]["is_superuser"])
        self.assertIn(get_refresh_cookie_name(), response.cookies)

    def test_logout_is_idempotent_and_always_expires_refresh_cookie(self):
        cookie_name = get_refresh_cookie_name()
        self.client.cookies[cookie_name] = "not-a-valid-refresh-token"

        first = self.client.post("/api/auth/logout/", {}, format="json")
        second = self.client.post("/api/auth/logout/", {}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.cookies[cookie_name].value, "")
        self.assertEqual(first.cookies[cookie_name]["max-age"], 0)
        self.assertEqual(second.cookies[cookie_name].value, "")


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_URL="http://localhost:5555",
    SIGNUP_FORM_MIN_AGE_SECONDS=0,
)
class SignupProtectionTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.site_settings.signup_burst_limit = 100
        self.site_settings.signup_short_window_limit = 100
        self.site_settings.signup_sustained_limit = 100
        self.site_settings.save(
            update_fields=[
                "signup_burst_limit",
                "signup_short_window_limit",
                "signup_sustained_limit",
            ]
        )

    def test_signup_challenge_returns_registration_token_and_no_cache_when_captcha_disabled(self):
        response = self.client.get("/api/auth/register/captcha/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["captcha_enabled"])
        self.assertEqual(response.data["captcha_id"], "")
        self.assertEqual(response.data["captcha_prompt"], "")
        self.assertTrue(response.data["registration_token"])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_signup_challenge_returns_captcha_when_enabled(self):
        self.site_settings.signup_captcha_enabled = True
        self.site_settings.save(update_fields=["signup_captcha_enabled"])

        challenge = self.get_signup_challenge()

        self.assertTrue(challenge["captcha_enabled"])
        self.assertTrue(challenge["captcha_id"])
        self.assertTrue(challenge["captcha_prompt"])

    def test_registration_bypasses_captcha_when_disabled(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_registration_requires_captcha_when_enabled(self):
        self.site_settings.signup_captcha_enabled = True
        self.site_settings.save(update_fields=["signup_captcha_enabled"])
        challenge = self.get_signup_challenge()
        payload = self.build_registration_payload(
            challenge=challenge,
            captcha_answer="",
        )

        response = self.client.post("/api/auth/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha_answer", response.data)

    def test_registration_rejects_wrong_captcha(self):
        self.site_settings.signup_captcha_enabled = True
        self.site_settings.save(update_fields=["signup_captcha_enabled"])
        challenge = self.get_signup_challenge()
        payload = self.build_registration_payload(
            challenge=challenge,
            captcha_answer="999",
        )

        response = self.client.post("/api/auth/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha_answer", response.data)

    def test_registration_rejects_reused_captcha(self):
        self.site_settings.signup_captcha_enabled = True
        self.site_settings.save(update_fields=["signup_captcha_enabled"])
        challenge = self.get_signup_challenge()

        first_response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                challenge=challenge,
                username="first-user",
                email="first-user@example.com",
            ),
            format="json",
        )
        second_response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                challenge=challenge,
                username="second-user",
                email="second-user@example.com",
            ),
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha_answer", second_response.data)

    def test_registration_rejects_expired_captcha(self):
        self.site_settings.signup_captcha_enabled = True
        self.site_settings.save(update_fields=["signup_captcha_enabled"])
        challenge = self.get_signup_challenge()
        cache.delete(get_signup_captcha_cache_key(challenge["captcha_id"]))

        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                challenge=challenge,
                username="expired-user",
                email="expired-user@example.com",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha_answer", response.data)

    def test_registration_rejects_honeypot_field(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(company_website="https://spam.example.com"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)

    @override_settings(SIGNUP_FORM_MIN_AGE_SECONDS=3)
    def test_registration_rejects_too_fast_submission(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                username="too-fast",
                email="too-fast@example.com",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)

    @override_settings(SIGNUP_FORM_MIN_AGE_SECONDS=3)
    def test_registration_accepts_valid_aged_form_token(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(
                username="aged-form",
                email="aged-form@example.com",
                registration_token=self.get_aged_registration_token(age_seconds=5),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_registration_blocks_disposable_domain_when_enabled(self):
        self.site_settings.signup_disposable_email_blocking_enabled = True
        self.site_settings.save(
            update_fields=["signup_disposable_email_blocking_enabled"]
        )

        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(email="blocked@mailinator.com"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_registration_allows_disposable_domain_when_disabled(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(email="allowed@mailinator.com"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(SIGNUP_DISPOSABLE_EMAIL_BLOCKLIST=["throwaway.example"])
    def test_custom_disposable_blocklist_is_enforced(self):
        self.site_settings.signup_disposable_email_blocking_enabled = True
        self.site_settings.save(
            update_fields=["signup_disposable_email_blocking_enabled"]
        )

        response = self.client.post(
            "/api/auth/register/",
            self.build_registration_payload(email="custom@throwaway.example"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    @patch(
        "accounts.verification.SiteSettings.objects.get_or_create",
        side_effect=OperationalError("missing column"),
    )
    def test_signup_challenge_survives_site_settings_schema_drift(self, mocked_get_or_create):
        response = self.client.get("/api/auth/register/captcha/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("registration_token", response.data)
        mocked_get_or_create.assert_called()


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_URL="http://localhost:5555",
    SIGNUP_FORM_MIN_AGE_SECONDS=0,
)
class RegistrationThrottleTests(AccountsBaseTestCase):
    def set_signup_limits(self, *, burst=1, short_window=3, sustained=10):
        self.site_settings.signup_burst_limit = burst
        self.site_settings.signup_short_window_limit = short_window
        self.site_settings.signup_sustained_limit = sustained
        self.site_settings.save(
            update_fields=[
                "signup_burst_limit",
                "signup_short_window_limit",
                "signup_sustained_limit",
            ]
        )

    def post_registration(self, index, *, client=None, remote_addr="127.0.0.1", **extra_headers):
        payload = self.build_registration_payload(
            client=client,
            username=f"user-{index}",
            email=f"user-{index}@example.com",
        )
        return (client or self.client).post(
            "/api/auth/register/",
            payload,
            format="json",
            REMOTE_ADDR=remote_addr,
            **extra_headers,
        )

    def test_burst_rate_returns_429_on_second_request_from_same_ip(self):
        first = self.post_registration(1)
        second = self.post_registration(2)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_short_window_rate_returns_429_on_fourth_request_from_same_ip(self):
        self.set_signup_limits(burst=100, short_window=3, sustained=100)
        responses = [self.post_registration(index) for index in range(1, 5)]

        self.assertTrue(
            all(response.status_code == status.HTTP_201_CREATED for response in responses[:3])
        )
        self.assertEqual(responses[3].status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_sustained_rate_returns_429_on_eleventh_request_from_same_ip(self):
        self.set_signup_limits(burst=100, short_window=100, sustained=10)
        responses = [self.post_registration(index) for index in range(1, 12)]

        self.assertTrue(
            all(response.status_code == status.HTTP_201_CREATED for response in responses[:10])
        )
        self.assertEqual(responses[10].status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        TRUSTED_PROXY_IPS=["10.0.0.1"],
    )
    def test_register_throttle_uses_forwarded_ip_for_trusted_proxy(self):
        self.set_signup_limits(burst=1, short_window=100, sustained=100)
        trusted_client = APIClient()

        first = self.post_registration(
            1,
            client=trusted_client,
            remote_addr="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 198.51.100.2",
        )
        second = self.post_registration(
            2,
            client=trusted_client,
            remote_addr="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 198.51.100.2",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        TRUSTED_PROXY_IPS=[],
    )
    def test_register_throttle_ignores_forwarded_ip_for_untrusted_proxy(self):
        self.set_signup_limits(burst=1, short_window=100, sustained=100)
        first = self.post_registration(
            1,
            remote_addr="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 198.51.100.2",
        )
        second = self.post_registration(
            2,
            remote_addr="10.0.0.2",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 198.51.100.2",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    CSRF_TRUSTED_ORIGINS=["http://testserver"],
)
class TokenRefreshSecurityTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="refresh-user",
            email="refresh@example.com",
            password="TestPass123!",
            email_verified=True,
        )

    def set_refresh_cookie(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies[get_refresh_cookie_name()] = str(refresh)

    def test_cookie_refresh_rejects_untrusted_origin(self):
        self.set_refresh_cookie()

        response = self.client.post("/api/auth/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Refresh request origin is not allowed.")

    def test_cookie_refresh_allows_trusted_origin(self):
        self.set_refresh_cookie()

        response = self.client.post(
            "/api/auth/token/refresh/",
            {},
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn(get_refresh_cookie_name(), response.cookies)


@override_settings(DB_ENGINE="django.db.backends.sqlite3")
class ProfileUpdateSecurityTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="profile-user",
            email="profile@example.com",
            password="TestPass123!",
            email_verified=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_profile_update_rejects_email_changes(self):
        response = self.client.patch(
            "/api/auth/user/update/",
            {
                "first_name": "Updated",
                "email": "attacker@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    PUBLIC_APP_URL="http://localhost:5555",
    SOCIAL_AUTH_ALLOWED_FRONTEND_ORIGINS=["http://localhost:5555"],
    GOOGLE_OAUTH_CLIENT_ID="google-id",
    GOOGLE_OAUTH_CLIENT_SECRET="google-secret",
)
class SocialProviderEndpointTests(AccountsBaseTestCase):
    def test_social_provider_list_reflects_admin_flags_and_env_configuration(self):
        self.site_settings.social_login_google_enabled = True
        self.site_settings.social_login_facebook_enabled = True
        self.site_settings.save(
            update_fields=[
                "social_login_google_enabled",
                "social_login_facebook_enabled",
            ]
        )

        response = self.client.get("/api/auth/social/providers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        providers = {item["id"]: item for item in response.data["providers"]}
        self.assertTrue(providers["google"]["configured"])
        self.assertTrue(providers["google"]["enabled"])
        self.assertTrue(providers["google"]["available"])
        self.assertFalse(providers["facebook"]["configured"])
        self.assertTrue(providers["facebook"]["enabled"])
        self.assertFalse(providers["facebook"]["available"])

    def test_social_start_rejects_invalid_origin(self):
        self.site_settings.social_login_google_enabled = True
        self.site_settings.save(update_fields=["social_login_google_enabled"])

        response = self.client.post(
            "/api/auth/social/google/start/",
            {"next": "/dashboard"},
            format="json",
            HTTP_ORIGIN="https://untrusted.example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    @patch(
        "accounts.verification.SiteSettings.objects.get_or_create",
        side_effect=OperationalError("missing column"),
    )
    def test_social_provider_list_survives_site_settings_schema_drift(
        self,
        mocked_get_or_create,
    ):
        response = self.client.get("/api/auth/social/providers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("providers", response.data)
        mocked_get_or_create.assert_called()

    @patch("accounts.social_auth.get_oauth_client", return_value=StubOAuthClient())
    def test_social_start_returns_authorization_url_for_enabled_provider(self, mocked_client):
        self.site_settings.social_login_google_enabled = True
        self.site_settings.save(update_fields=["social_login_google_enabled"])

        response = self.client.post(
            "/api/auth/social/google/start/",
            {"next": "/dashboard"},
            format="json",
            HTTP_ORIGIN="http://localhost:5555",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["authorization_url"],
            "https://provider.example/oauth/authorize",
        )
        session = self.client.session
        self.assertIn("_state_google_state-123", session)
        mocked_client.assert_called_once_with("google")


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    GOOGLE_OAUTH_CLIENT_ID="google-id",
    GOOGLE_OAUTH_CLIENT_SECRET="google-secret",
    MEDIA_ROOT=tempfile.mkdtemp(prefix="reactdjango-branding-tests-"),
)
class AdminSettingsSocialTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_superuser(
            username="admin-user",
            email="admin@example.com",
            password="AdminPass123!",
        )
        self.client.force_authenticate(user=self.admin_user)

    def test_admin_settings_returns_social_toggle_meta(self):
        self.site_settings.social_login_google_enabled = True
        self.site_settings.save(update_fields=["social_login_google_enabled"])

        response = self.client.get("/api/admin/settings/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["social_login_google_enabled"])
        self.assertFalse(response.data["require_email_verification"])
        self.assertFalse(response.data["signup_captcha_enabled"])
        self.assertFalse(response.data["signup_disposable_email_blocking_enabled"])
        self.assertEqual(response.data["signup_burst_limit"], 1)
        self.assertEqual(response.data["signup_short_window_limit"], 3)
        self.assertEqual(response.data["signup_sustained_limit"], 10)
        self.assertTrue(response.data["social_login_google_meta"]["configured"])
        self.assertEqual(
            response.data["social_login_google_meta"]["source"],
            "environment",
        )
        self.assertIn("rate_limit_storage_meta", response.data)
        self.assertEqual(response.data["branding_logo_url"], "/branding/logo.svg")
        self.assertEqual(response.data["branding_favicon_url"], "/branding/logo.ico")
        self.assertFalse(response.data["branding_logo_customized"])

    def test_admin_settings_patch_updates_social_toggles(self):
        response = self.client.patch(
            "/api/admin/settings/",
            {
                "require_email_verification": True,
                "signup_captcha_enabled": True,
                "signup_disposable_email_blocking_enabled": True,
                "signup_burst_limit": 5,
                "signup_short_window_limit": 12,
                "signup_sustained_limit": 30,
                "social_login_google_enabled": True,
                "social_login_github_enabled": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.site_settings.refresh_from_db()
        self.assertTrue(self.site_settings.require_email_verification)
        self.assertTrue(self.site_settings.signup_captcha_enabled)
        self.assertTrue(self.site_settings.signup_disposable_email_blocking_enabled)
        self.assertEqual(self.site_settings.signup_burst_limit, 5)
        self.assertEqual(self.site_settings.signup_short_window_limit, 12)
        self.assertEqual(self.site_settings.signup_sustained_limit, 30)
        self.assertTrue(self.site_settings.social_login_google_enabled)
        self.assertTrue(self.site_settings.social_login_github_enabled)

    def test_public_branding_returns_custom_uploaded_assets(self):
        response = self.client.patch(
            "/api/admin/settings/",
            {
                "branding_logo": make_uploaded_image(
                    "logo.png",
                    size=(1200, 320),
                ),
                "branding_favicon": make_uploaded_image(
                    "favicon.png",
                    size=(256, 256),
                ),
                "branding_login_banner": make_uploaded_image(
                    "login-banner.png",
                    size=(1800, 1200),
                ),
                "branding_register_banner": make_uploaded_image(
                    "register-banner.png",
                    size=(1800, 1200),
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.site_settings.refresh_from_db()
        self.assertTrue(bool(self.site_settings.branding_logo))
        self.assertTrue(bool(self.site_settings.branding_favicon))
        self.assertTrue(response.data["branding_logo_customized"])
        self.assertTrue(response.data["branding_favicon_customized"])

        public_client = APIClient()
        public_response = public_client.get("/api/auth/branding/")

        self.assertEqual(public_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            public_response.data["branding_logo_url"].startswith("/media/branding/")
        )
        self.assertTrue(
            public_response.data["branding_favicon_url"].startswith("/media/branding/")
        )
        self.assertTrue(
            public_response.data["branding_login_banner_url"].startswith(
                "/media/branding/"
            )
        )
        self.assertTrue(
            public_response.data["branding_register_banner_url"].startswith(
                "/media/branding/"
            )
        )

    def test_admin_settings_rejects_oversized_favicon_dimensions(self):
        response = self.client.patch(
            "/api/admin/settings/",
            {
                "branding_favicon": make_uploaded_image(
                    "favicon.png",
                    size=(768, 768),
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("branding_favicon", response.data)
        self.assertIn("512x512", str(response.data["branding_favicon"][0]))


@override_settings(DB_ENGINE="django.db.backends.sqlite3")
class AdminGateTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_superuser(
            username="admin-user",
            email="admin@example.com",
            password="AdminPass123!",
        )
        self.regular_user = User.objects.create_user(
            username="regular-user",
            email="regular@example.com",
            password="TestPass123!",
            email_verified=True,
        )

    def test_superuser_gate_returns_no_content(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get("/api/admin/_gate/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_regular_user_gate_is_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/admin/_gate/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_URL="http://localhost:5555",
)
class SocialAuthServiceTests(AccountsBaseTestCase):
    def test_google_verified_identity_creates_user_and_social_link(self):
        identity = SocialIdentity(
            provider="google",
            provider_user_id="google-123",
            email="google@example.com",
            email_verified=True,
            display_name="Google User",
            first_name="Google",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
        )

        result = resolve_social_login(
            identity,
            frontend_origin="http://localhost:5555",
            next_path="/dashboard",
        )

        self.assertEqual(result.status, "success")
        user = User.objects.get(email="google@example.com")
        self.assertTrue(user.email_verified)
        social_account = UserSocialAccount.objects.get(user=user, provider="google")
        self.assertTrue(social_account.is_active)
        self.assertTrue(social_account.email_verified)
        self.assertEqual(social_account.provider_user_id, "google-123")

    def test_google_verified_identity_links_existing_user_by_email(self):
        user = User.objects.create_user(
            username="existing",
            email="existing@example.com",
            password="TestPass123!",
            email_verified=False,
        )
        identity = SocialIdentity(
            provider="google",
            provider_user_id="google-456",
            email="existing@example.com",
            email_verified=True,
            display_name="Existing User",
            first_name="Existing",
            last_name="User",
        )

        result = resolve_social_login(
            identity,
            frontend_origin="http://localhost:5555",
            next_path="/dashboard",
        )

        user.refresh_from_db()
        self.assertEqual(result.status, "success")
        self.assertTrue(user.email_verified)
        self.assertTrue(
            UserSocialAccount.objects.filter(
                user=user,
                provider="google",
                provider_user_id="google-456",
            ).exists()
        )

    def test_github_identity_requires_verified_email(self):
        client = StubGitHubClient(
            profile={"id": 1001, "login": "octocat", "name": "Octo Cat"},
            emails=[
                {"email": "octocat@example.com", "primary": True, "verified": False},
            ],
        )

        with self.assertRaises(SocialAuthEmailError):
            fetch_github_identity(client, token={"access_token": "token"})

    def test_facebook_identity_requires_local_email_verification(self):
        identity = SocialIdentity(
            provider="facebook",
            provider_user_id="facebook-123",
            email="facebook@example.com",
            email_verified=False,
            display_name="Facebook User",
            first_name="Facebook",
            last_name="User",
        )

        result = resolve_social_login(
            identity,
            frontend_origin="http://localhost:5555",
            next_path="/dashboard",
        )

        self.assertEqual(result.status, "verification_required")
        user = User.objects.get(email="facebook@example.com")
        self.assertFalse(user.email_verified)
        social_account = UserSocialAccount.objects.get(user=user, provider="facebook")
        self.assertFalse(social_account.is_active)
        self.assertEqual(len(mail.outbox), 1)

    def test_social_identity_conflict_is_blocked(self):
        existing_user = User.objects.create_user(
            username="existing-social",
            email="existing-social@example.com",
            password="TestPass123!",
            email_verified=True,
        )
        UserSocialAccount.objects.create(
            user=existing_user,
            provider="google",
            provider_user_id="existing-google-id",
            email=existing_user.email,
            email_verified=True,
            display_name="Existing Social",
        )
        identity = SocialIdentity(
            provider="google",
            provider_user_id="new-google-id",
            email=existing_user.email,
            email_verified=True,
            display_name="Existing User New Google",
        )

        with self.assertRaises(SocialAuthConflictError):
            resolve_social_login(
                identity,
                frontend_origin="http://localhost:5555",
                next_path="/dashboard",
            )

    def test_verify_email_activates_pending_social_accounts(self):
        user = User.objects.create_user(
            username="pending-facebook",
            email="pending-facebook@example.com",
            password="TestPass123!",
            email_verified=False,
        )
        UserSocialAccount.objects.create(
            user=user,
            provider="facebook",
            provider_user_id="facebook-999",
            email=user.email,
            email_verified=False,
            display_name="Pending Facebook",
            is_active=False,
        )
        token = EmailVerificationToken.objects.create(user=user)

        response = self.client.get(f"/api/auth/verify-email/?token={token.token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        social_account = UserSocialAccount.objects.get(user=user, provider="facebook")
        self.assertTrue(social_account.is_active)
        self.assertTrue(social_account.email_verified)


@override_settings(
    DB_ENGINE="django.db.backends.sqlite3",
    SOCIAL_AUTH_FRONTEND_CALLBACK_PATH="/auth/social/callback",
)
class SocialAuthCallbackViewTests(AccountsBaseTestCase):
    @patch(
        "accounts.views.complete_social_login",
        return_value=SocialLoginResult(
            status="success",
            provider="google",
            user=User(username="callback-user", email="callback@example.com"),
            frontend_origin="http://localhost:5555",
            next_path="/dashboard",
        ),
    )
    @patch(
        "accounts.views.get_callback_state_data",
        return_value=(None, {}, "http://localhost:5555", "/dashboard"),
    )
    def test_social_callback_success_redirect_sets_refresh_cookie(
        self,
        mocked_state,
        mocked_complete,
    ):
        user = User.objects.create_user(
            username="callback-user",
            email="callback@example.com",
            password="TestPass123!",
            email_verified=True,
        )
        mocked_complete.return_value.user = user

        response = self.client.get("/api/auth/social/google/callback/?state=test-state")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=success", response.url)
        self.assertIn(get_refresh_cookie_name(), response.cookies)

    @patch(
        "accounts.views.complete_social_login",
        return_value=SocialLoginResult(
            status="verification_required",
            provider="facebook",
            user=None,
            frontend_origin="http://localhost:5555",
            next_path="/dashboard",
            detail="Verify your email.",
            email_hint="f*****k@example.com",
        ),
    )
    @patch(
        "accounts.views.get_callback_state_data",
        return_value=(None, {}, "http://localhost:5555", "/dashboard"),
    )
    def test_social_callback_verification_redirect_clears_refresh_cookie(
        self,
        mocked_state,
        mocked_complete,
    ):
        response = self.client.get("/api/auth/social/facebook/callback/?state=test-state")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=verification_required", response.url)
        self.assertIn(get_refresh_cookie_name(), response.cookies)
        self.assertEqual(response.cookies[get_refresh_cookie_name()].value, "")


@override_settings(DB_ENGINE="django.db.backends.sqlite3")
class AdminUserDeletionTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_superuser(
            username="admin-user",
            email="admin@example.com",
            password="AdminPass123!",
        )
        self.client.force_authenticate(user=self.admin_user)

    def get_free_plan(self):
        plan, _ = Plan.objects.get_or_create(
            slug="free",
            defaults={
                "name": "Free",
                "tier": 1,
                "max_items": 0,
                "price_monthly": 0,
                "price_yearly": 0,
                "bkash_price_monthly": 0,
                "bkash_price_yearly": 0,
                "currency": "USD",
                "is_active": True,
            },
        )
        return plan

    def create_user_with_related_data(self, *, username="target", email="target@example.com"):
        plan = self.get_free_plan()
        user = User.objects.create_user(
            username=username,
            email=email,
            password="TestPass123!",
            email_verified=True,
        )
        EmailVerificationToken.objects.create(user=user)
        UserSocialAccount.objects.create(
            user=user,
            provider=UserSocialAccount.Provider.GOOGLE,
            provider_user_id=f"google-{user.pk}",
            email=user.email,
            email_verified=True,
            display_name="Target User",
        )
        subscription, _ = UserSubscription.objects.get_or_create(
            user=user,
            defaults={
                "plan": plan,
                "status": UserSubscription.Status.ACTIVE,
                "billing_cycle": UserSubscription.BillingCycle.MONTHLY,
                "payment_provider": UserSubscription.PaymentProvider.NONE,
            },
        )
        BkashTransaction.objects.create(
            user=user,
            subscription=subscription,
            target_plan=plan,
            billing_cycle=UserSubscription.BillingCycle.MONTHLY,
            payment_id=f"payment-{user.pk}",
            trx_id=f"trx-{user.pk}",
            invoice_number=f"invoice-{user.pk}",
            amount="100.00",
            currency="BDT",
            status=BkashTransaction.Status.COMPLETED,
        )
        SubscriptionEvent.objects.create(
            subscription=subscription,
            user=user,
            event_type=SubscriptionEvent.EventType.BASELINE,
            plan=plan,
            status=subscription.status,
            payment_provider=subscription.payment_provider,
            billing_cycle=subscription.billing_cycle,
            metadata={"source": "test"},
        )
        return user

    def test_superuser_can_delete_normal_user_and_related_records(self):
        target_user = self.create_user_with_related_data()

        response = self.client.delete(f"/api/admin/users/{target_user.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "User deleted successfully.")
        self.assertFalse(User.objects.filter(pk=target_user.pk).exists())
        self.assertEqual(
            EmailVerificationToken.objects.filter(user_id=target_user.pk).count(), 0
        )
        self.assertEqual(
            UserSocialAccount.objects.filter(user_id=target_user.pk).count(), 0
        )
        self.assertEqual(
            UserSubscription.objects.filter(user_id=target_user.pk).count(), 0
        )
        self.assertEqual(
            BkashTransaction.objects.filter(user_id=target_user.pk).count(), 0
        )
        self.assertEqual(
            SubscriptionEvent.objects.filter(user_id=target_user.pk).count(), 0
        )

    def test_delete_rejects_superuser_target(self):
        target_user = User.objects.create_superuser(
            username="other-admin",
            email="other-admin@example.com",
            password="AdminPass123!",
        )

        response = self.client.delete(f"/api/admin/users/{target_user.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Admin accounts cannot be deleted.")
        self.assertTrue(User.objects.filter(pk=target_user.pk).exists())

    def test_non_superuser_cannot_delete_user(self):
        regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="TestPass123!",
            email_verified=True,
        )
        target_user = self.create_user_with_related_data(
            username="victim",
            email="victim@example.com",
        )
        client = APIClient()
        client.force_authenticate(user=regular_user)

        response = client.delete(f"/api/admin/users/{target_user.pk}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=target_user.pk).exists())


@override_settings(DB_ENGINE="django.db.backends.sqlite3")
class UserDeletionServiceTests(AccountsBaseTestCase):
    def test_delete_user_account_removes_avatar_file(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                user = User.objects.create_user(
                    username="avatar-user",
                    email="avatar@example.com",
                    password="TestPass123!",
                    email_verified=True,
                )
                user.avatar.save(
                    "avatar.txt",
                    SimpleUploadedFile("avatar.txt", b"avatar-bytes"),
                    save=True,
                )
                avatar_path = user.avatar.path

                self.assertTrue(os.path.exists(avatar_path))
                with self.captureOnCommitCallbacks(execute=True):
                    delete_user_account(user, audit_event="test_user_delete")

                self.assertFalse(User.objects.filter(pk=user.pk).exists())
                self.assertFalse(os.path.exists(avatar_path))

    def test_self_service_delete_removes_user(self):
        user = User.objects.create_user(
            username="self-delete",
            email="self-delete@example.com",
            password="TestPass123!",
            email_verified=True,
        )
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.delete("/api/auth/user/delete/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Account deleted successfully.")
        self.assertFalse(User.objects.filter(pk=user.pk).exists())


@override_settings(DB_ENGINE="django.db.backends.sqlite3")
class DjangoAdminUserDeletionTests(AccountsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_superuser(
            username="site-admin",
            email="site-admin@example.com",
            password="AdminPass123!",
        )
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)
        self.request_factory = RequestFactory()
        self.model_admin = AccountsUserAdmin(User, admin.site)

    def test_superuser_objects_are_not_deletable(self):
        target_user = User.objects.create_superuser(
            username="protected-admin",
            email="protected-admin@example.com",
            password="AdminPass123!",
        )
        request = self.request_factory.get("/admin/accounts/user/")
        request.user = self.admin_user

        response = self.admin_client.get(
            reverse("admin:accounts_user_delete", args=[target_user.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertFalse(self.model_admin.has_delete_permission(request, target_user))
        self.assertTrue(User.objects.filter(pk=target_user.pk).exists())

    def test_bulk_delete_action_is_removed(self):
        request = self.request_factory.get("/admin/accounts/user/")
        request.user = self.admin_user

        actions = self.model_admin.get_actions(request)

        self.assertNotIn("delete_selected", actions)
