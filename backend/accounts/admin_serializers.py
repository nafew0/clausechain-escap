from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from subscriptions.models import SubscriptionEvent, UserSubscription
from subscriptions.serializers import PlanSummarySerializer
from subscriptions.services import LicenseService

from .ai_secrets import get_ai_api_key_meta
from .branding import (
    get_branding_asset_limits,
    has_custom_branding_asset,
    resolve_branding_asset_url,
    sanitize_branding_upload,
)
from .models import (
    DEFAULT_SIGNUP_BURST_LIMIT,
    DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT,
    DEFAULT_SIGNUP_SUSTAINED_LIMIT,
    SiteSettings,
)
from .social_auth import get_social_provider_status

User = get_user_model()


class AdminSubscriptionSummarySerializer(serializers.ModelSerializer):
    plan = PlanSummarySerializer(read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "plan",
            "status",
            "billing_cycle",
            "payment_provider",
            "cancel_at_period_end",
            "cancel_requested_at",
            "current_period_start",
            "current_period_end",
        ]


class AdminUserListSerializer(serializers.ModelSerializer):
    current_plan = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_superuser",
            "email_verified",
            "current_plan",
            "created_at",
            "last_login",
        ]

    def get_current_plan(self, obj):
        subscription = getattr(obj, "subscription", None)
        plan = subscription.plan if subscription else LicenseService.get_free_plan()
        return PlanSummarySerializer(plan).data


class AdminUserDetailSerializer(serializers.ModelSerializer):
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "bio",
            "organization",
            "designation",
            "phone",
            "is_active",
            "is_staff",
            "is_superuser",
            "email_verified",
            "created_at",
            "last_login",
            "subscription",
        ]

    def get_subscription(self, obj):
        subscription = getattr(obj, "subscription", None) or LicenseService.get_user_subscription(
            obj
        )
        return AdminSubscriptionSummarySerializer(subscription).data


class AdminUserUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    plan_id = serializers.UUIDField(required=False)


class SubscriptionEventSerializer(serializers.ModelSerializer):
    plan = PlanSummarySerializer(read_only=True)

    class Meta:
        model = SubscriptionEvent
        fields = [
            "id",
            "event_type",
            "plan",
            "status",
            "payment_provider",
            "billing_cycle",
            "metadata",
            "created_at",
        ]


class SiteSettingsAdminSerializer(serializers.ModelSerializer):
    ai_api_key_openai_meta = serializers.SerializerMethodField()
    ai_api_key_anthropic_meta = serializers.SerializerMethodField()
    ai_secret_storage_mode = serializers.SerializerMethodField()
    social_login_google_meta = serializers.SerializerMethodField()
    social_login_facebook_meta = serializers.SerializerMethodField()
    social_login_github_meta = serializers.SerializerMethodField()
    rate_limit_storage_meta = serializers.SerializerMethodField()
    branding_logo_url = serializers.SerializerMethodField()
    branding_favicon_url = serializers.SerializerMethodField()
    branding_login_banner_url = serializers.SerializerMethodField()
    branding_register_banner_url = serializers.SerializerMethodField()
    branding_logo_customized = serializers.SerializerMethodField()
    branding_favicon_customized = serializers.SerializerMethodField()
    branding_login_banner_customized = serializers.SerializerMethodField()
    branding_register_banner_customized = serializers.SerializerMethodField()
    branding_asset_limits = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = [
            "require_email_verification",
            "logged_in_users_only_default",
            "signup_captcha_enabled",
            "signup_disposable_email_blocking_enabled",
            "signup_burst_limit",
            "signup_short_window_limit",
            "signup_sustained_limit",
            "branding_logo_url",
            "branding_favicon_url",
            "branding_login_banner_url",
            "branding_register_banner_url",
            "branding_logo_customized",
            "branding_favicon_customized",
            "branding_login_banner_customized",
            "branding_register_banner_customized",
            "branding_asset_limits",
            "social_login_google_enabled",
            "social_login_facebook_enabled",
            "social_login_github_enabled",
            "ai_provider",
            "ai_model_openai",
            "ai_model_anthropic",
            "ai_secret_storage_mode",
            "ai_api_key_openai_meta",
            "ai_api_key_anthropic_meta",
            "social_login_google_meta",
            "social_login_facebook_meta",
            "social_login_github_meta",
            "rate_limit_storage_meta",
        ]

    def get_ai_secret_storage_mode(self, obj):
        return "environment_only"

    def get_ai_api_key_openai_meta(self, obj):
        meta = get_ai_api_key_meta(obj, SiteSettings.AIProvider.OPENAI)
        return {
            "configured": meta["configured"],
            "source": meta["source"],
        }

    def get_ai_api_key_anthropic_meta(self, obj):
        meta = get_ai_api_key_meta(obj, SiteSettings.AIProvider.ANTHROPIC)
        return {
            "configured": meta["configured"],
            "source": meta["source"],
        }

    def get_social_login_google_meta(self, obj):
        status = get_social_provider_status("google", obj)
        return {"configured": status.configured, "source": status.source}

    def get_social_login_facebook_meta(self, obj):
        status = get_social_provider_status("facebook", obj)
        return {"configured": status.configured, "source": status.source}

    def get_social_login_github_meta(self, obj):
        status = get_social_provider_status("github", obj)
        return {"configured": status.configured, "source": status.source}

    def get_branding_logo_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_logo")

    def get_branding_favicon_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_favicon")

    def get_branding_login_banner_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_login_banner")

    def get_branding_register_banner_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_register_banner")

    def get_branding_logo_customized(self, obj):
        return has_custom_branding_asset(obj, "branding_logo")

    def get_branding_favicon_customized(self, obj):
        return has_custom_branding_asset(obj, "branding_favicon")

    def get_branding_login_banner_customized(self, obj):
        return has_custom_branding_asset(obj, "branding_login_banner")

    def get_branding_register_banner_customized(self, obj):
        return has_custom_branding_asset(obj, "branding_register_banner")

    def get_branding_asset_limits(self, obj):
        return get_branding_asset_limits()

    def get_rate_limit_storage_meta(self, obj):
        cache_backend = settings.CACHES["default"]["BACKEND"]
        use_redis = bool(getattr(settings, "USE_REDIS", False))
        is_shared_backend = cache_backend == "django.core.cache.backends.redis.RedisCache"
        warning = ""
        if getattr(settings, "IS_PRODUCTION", False) and (not use_redis or not is_shared_backend):
            warning = (
                "Production rate limiting requires USE_REDIS=true with a shared Redis cache. "
                "LocMemCache splits throttle state across workers."
            )
        return {
            "environment": getattr(settings, "ENVIRONMENT", "development"),
            "use_redis": use_redis,
            "cache_backend": cache_backend,
            "is_shared_backend": is_shared_backend,
            "trusted_proxy_ips_configured": bool(getattr(settings, "TRUSTED_PROXY_IPS", [])),
            "warning": warning,
        }


class SiteSettingsUpdateSerializer(serializers.Serializer):
    require_email_verification = serializers.BooleanField(required=False)
    logged_in_users_only_default = serializers.BooleanField(required=False)
    signup_captcha_enabled = serializers.BooleanField(required=False)
    signup_disposable_email_blocking_enabled = serializers.BooleanField(required=False)
    signup_burst_limit = serializers.IntegerField(required=False, min_value=1)
    signup_short_window_limit = serializers.IntegerField(required=False, min_value=1)
    signup_sustained_limit = serializers.IntegerField(required=False, min_value=1)
    branding_logo = serializers.ImageField(required=False, allow_empty_file=False)
    branding_favicon = serializers.ImageField(required=False, allow_empty_file=False)
    branding_login_banner = serializers.ImageField(required=False, allow_empty_file=False)
    branding_register_banner = serializers.ImageField(required=False, allow_empty_file=False)
    clear_branding_logo = serializers.BooleanField(required=False)
    clear_branding_favicon = serializers.BooleanField(required=False)
    clear_branding_login_banner = serializers.BooleanField(required=False)
    clear_branding_register_banner = serializers.BooleanField(required=False)
    social_login_google_enabled = serializers.BooleanField(required=False)
    social_login_facebook_enabled = serializers.BooleanField(required=False)
    social_login_github_enabled = serializers.BooleanField(required=False)
    ai_provider = serializers.ChoiceField(
        choices=SiteSettings.AIProvider.choices,
        required=False,
    )
    ai_model_openai = serializers.CharField(required=False, allow_blank=True, max_length=100)
    ai_model_anthropic = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate_branding_logo(self, value):
        try:
            return sanitize_branding_upload(value, "branding_logo")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_branding_favicon(self, value):
        try:
            return sanitize_branding_upload(value, "branding_favicon")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_branding_login_banner(self, value):
        try:
            return sanitize_branding_upload(value, "branding_login_banner")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_branding_register_banner(self, value):
        try:
            return sanitize_branding_upload(value, "branding_register_banner")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        rejected_fields = [
            field_name
            for field_name in ("ai_api_key_openai", "ai_api_key_anthropic")
            if field_name in self.initial_data
        ]
        if rejected_fields:
            raise serializers.ValidationError(
                {
                    field_name: "Configure AI API keys with environment variables."
                    for field_name in rejected_fields
                }
            )

        for field_name in (
            "branding_logo",
            "branding_favicon",
            "branding_login_banner",
            "branding_register_banner",
        ):
            if field_name in attrs and attrs.get(f"clear_{field_name}"):
                raise serializers.ValidationError(
                    {
                        f"clear_{field_name}": (
                            "Choose either a new upload or remove the current image."
                        )
                    }
                )

        instance = getattr(self, "instance", None)
        burst_limit = attrs.get(
            "signup_burst_limit",
            getattr(instance, "signup_burst_limit", DEFAULT_SIGNUP_BURST_LIMIT),
        )
        short_window_limit = attrs.get(
            "signup_short_window_limit",
            getattr(
                instance,
                "signup_short_window_limit",
                DEFAULT_SIGNUP_SHORT_WINDOW_LIMIT,
            ),
        )
        sustained_limit = attrs.get(
            "signup_sustained_limit",
            getattr(
                instance,
                "signup_sustained_limit",
                DEFAULT_SIGNUP_SUSTAINED_LIMIT,
            ),
        )

        if burst_limit > short_window_limit:
            raise serializers.ValidationError(
                {
                    "signup_short_window_limit": (
                        "The 10-minute signup limit must be greater than or equal "
                        "to the 15-second burst limit."
                    )
                }
            )
        if short_window_limit > sustained_limit:
            raise serializers.ValidationError(
                {
                    "signup_sustained_limit": (
                        "The hourly signup limit must be greater than or equal to "
                        "the 10-minute signup limit."
                    )
                }
            )
        return attrs


class AITestRequestSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SiteSettings.AIProvider.choices)
    model = serializers.CharField(max_length=100)

    def validate(self, attrs):
        if "api_key" in self.initial_data:
            raise serializers.ValidationError(
                {"api_key": "AI API keys must be configured on the server."}
            )
        return attrs


class PasswordResetValidateSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password": "Password fields didn't match."}
            )
        return attrs
