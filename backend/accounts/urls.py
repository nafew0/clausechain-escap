from django.urls import path

from .password_reset_views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetValidateView,
)
from .views import (
    BrandingSettingsView,
    RegisterView,
    RegisterCaptchaView,
    SocialAuthCallbackView,
    SocialAuthStartView,
    SocialProvidersView,
    VerifiedTokenRefreshView,
    login_view,
    logout_view,
    get_user_view,
    UpdateProfileView,
    ChangePasswordView,
    delete_account_view,
    resend_verification_email_view,
    send_verification_email_view,
    verify_email_view,
)

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("branding/", BrandingSettingsView.as_view(), name="branding"),
    path("register/captcha/", RegisterCaptchaView.as_view(), name="register_captcha"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", login_view, name="login"),
    path("social/providers/", SocialProvidersView.as_view(), name="social_providers"),
    path(
        "social/<str:provider>/start/",
        SocialAuthStartView.as_view(),
        name="social_start",
    ),
    path(
        "social/<str:provider>/callback/",
        SocialAuthCallbackView.as_view(),
        name="social_callback",
    ),
    path("logout/", logout_view, name="logout"),
    path("token/refresh/", VerifiedTokenRefreshView.as_view(), name="token_refresh"),
    path(
        "send-verification-email/",
        send_verification_email_view,
        name="send_verification_email",
    ),
    path(
        "resend-verification-email/",
        resend_verification_email_view,
        name="resend_verification_email",
    ),
    path("verify-email/", verify_email_view, name="verify_email"),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password-reset/validate/",
        PasswordResetValidateView.as_view(),
        name="password_reset_validate",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    # User management
    path("user/", get_user_view, name="get_user"),
    path("user/update/", UpdateProfileView.as_view(), name="update_profile"),
    path("user/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("user/delete/", delete_account_view, name="delete_account"),
]
