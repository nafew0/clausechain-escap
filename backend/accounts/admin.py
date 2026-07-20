from django.contrib import messages
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse

from clausechain.audit import log_audit_event

from .models import EmailVerificationToken, SiteSettings, UserSocialAccount
from .user_deletion import delete_user_account

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for custom User model."""

    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "organization",
        "designation",
        "email_verified",
        "is_staff",
        "created_at",
    ]
    list_filter = ["is_staff", "is_superuser", "is_active", "email_verified", "created_at"]
    search_fields = [
        "username",
        "email",
        "first_name",
        "last_name",
        "organization",
        "designation",
        "phone",
    ]
    ordering = ["-created_at"]

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Additional Info",
            {
                "fields": (
                    "bio",
                    "avatar",
                    "organization",
                    "designation",
                    "phone",
                    "email_verified",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    readonly_fields = ["created_at", "updated_at"]
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Additional Info",
            {
                "fields": (
                    "email",
                    "bio",
                    "avatar",
                    "organization",
                    "designation",
                    "phone",
                    "email_verified",
                )
            },
        ),
    )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser:
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_view(self, request, object_id, extra_context=None):
        user = self.get_object(request, object_id)
        if user is not None and user.is_superuser:
            log_audit_event(
                "django_admin_user_delete",
                outcome="failure",
                level="warning",
                request=request,
                target_user=user,
                reason="superuser_delete_blocked",
            )
            self.message_user(
                request,
                "Admin accounts cannot be deleted.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:accounts_user_change", args=[object_id])
            )
        return super().delete_view(request, object_id, extra_context)

    def delete_model(self, request, obj):
        delete_user_account(
            obj,
            request=request,
            audit_event="django_admin_user_delete",
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin interface for singleton site settings."""

    list_display = [
        "require_email_verification",
        "logged_in_users_only_default",
        "signup_captcha_enabled",
        "signup_disposable_email_blocking_enabled",
        "signup_burst_limit",
        "signup_short_window_limit",
        "signup_sustained_limit",
        "social_login_google_enabled",
        "social_login_facebook_enabled",
        "social_login_github_enabled",
        "ai_provider",
        "updated_at",
    ]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "Authentication",
            {
                "fields": (
                    "require_email_verification",
                    "logged_in_users_only_default",
                    "signup_captcha_enabled",
                    "signup_disposable_email_blocking_enabled",
                    "signup_burst_limit",
                    "signup_short_window_limit",
                    "signup_sustained_limit",
                )
            },
        ),
        (
            "Social login",
            {
                "fields": (
                    "social_login_google_enabled",
                    "social_login_facebook_enabled",
                    "social_login_github_enabled",
                )
            },
        ),
        (
            "AI settings",
            {
                "fields": (
                    "ai_provider",
                    "ai_model_openai",
                    "ai_model_anthropic",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        if SiteSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if SiteSettings.objects.exists():
            object_id = SiteSettings.objects.first().pk
            url = reverse("admin:accounts_sitesettings_change", args=[object_id])
            return HttpResponseRedirect(url)
        return super().changelist_view(request, extra_context)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Read-only operational visibility for verification tokens."""

    list_display = ["user", "token", "used", "created_at", "expires_at"]
    list_filter = ["used", "created_at", "expires_at"]
    search_fields = ["user__username", "user__email", "token"]
    readonly_fields = ["id", "user", "token", "used", "created_at", "expires_at"]

    def has_add_permission(self, request):
        return False


@admin.register(UserSocialAccount)
class UserSocialAccountAdmin(admin.ModelAdmin):
    """Operational visibility into social account links."""

    list_display = [
        "user",
        "provider",
        "email",
        "email_verified",
        "is_active",
        "last_login_at",
        "created_at",
    ]
    list_filter = ["provider", "email_verified", "is_active", "created_at"]
    search_fields = [
        "user__username",
        "user__email",
        "provider_user_id",
        "email",
        "display_name",
    ]
    readonly_fields = ["created_at", "updated_at", "last_login_at"]
