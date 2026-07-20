import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .branding import branding_asset_upload_to


def get_default_verification_expiry():
    return timezone.now() + timedelta(hours=24)


def generate_email_verification_token():
    return secrets.token_hex(32)


DEFAULT_SIGNUP_BURST_LIMIT = 1
DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT = 3
DEFAULT_SIGNUP_SUSTAINED_LIMIT = 10


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    Uses UUID as primary key for better security.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, default="")
    designation = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Make email required and unique
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        """Returns the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.username


class SiteSettings(models.Model):
    """Singleton site-wide settings used by auth and later feature phases."""

    class AIProvider(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        ANTHROPIC = "anthropic", "Anthropic"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    require_email_verification = models.BooleanField(default=False)
    logged_in_users_only_default = models.BooleanField(default=False)
    signup_captcha_enabled = models.BooleanField(default=False)
    signup_disposable_email_blocking_enabled = models.BooleanField(default=False)
    signup_burst_limit = models.PositiveIntegerField(default=DEFAULT_SIGNUP_BURST_LIMIT)
    signup_short_window_limit = models.PositiveIntegerField(
        default=DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT
    )
    signup_sustained_limit = models.PositiveIntegerField(
        default=DEFAULT_SIGNUP_SUSTAINED_LIMIT
    )
    branding_logo = models.ImageField(
        upload_to=branding_asset_upload_to,
        blank=True,
        null=True,
    )
    branding_favicon = models.ImageField(
        upload_to=branding_asset_upload_to,
        blank=True,
        null=True,
    )
    branding_login_banner = models.ImageField(
        upload_to=branding_asset_upload_to,
        blank=True,
        null=True,
    )
    branding_register_banner = models.ImageField(
        upload_to=branding_asset_upload_to,
        blank=True,
        null=True,
    )
    social_login_google_enabled = models.BooleanField(default=False)
    social_login_facebook_enabled = models.BooleanField(default=False)
    social_login_github_enabled = models.BooleanField(default=False)
    ai_provider = models.CharField(
        max_length=20,
        choices=AIProvider.choices,
        default=AIProvider.OPENAI,
    )
    ai_model_openai = models.CharField(max_length=100, blank=True, default="")
    ai_model_anthropic = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"


class UserSocialAccount(models.Model):
    """OAuth-linked social account metadata for a user."""

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        FACEBOOK = "facebook", "Facebook"
        GITHUB = "github", "GitHub"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_user_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    email_verified = models.BooleanField(default=False)
    display_name = models.CharField(max_length=255, blank=True, default="")
    avatar_url = models.URLField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_social_accounts"
        verbose_name = "User social account"
        verbose_name_plural = "User social accounts"
        ordering = ["provider", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="accounts_social_provider_user_id_uniq",
            ),
            models.UniqueConstraint(
                fields=["user", "provider"],
                name="accounts_social_user_provider_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} for {self.user.username}"


class EmailVerificationToken(models.Model):
    """Single-use verification token for email verification links."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_email_verification_token,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=get_default_verification_expiry)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Verification token for {self.user.username}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()
