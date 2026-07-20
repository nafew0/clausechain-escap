import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError
from authlib.integrations.base_client.errors import OAuthError

from clausechain.audit import log_audit_event

from .models import EmailVerificationToken
from .social_auth import (
    SocialAuthException,
    SocialAuthStateError,
    activate_pending_social_accounts,
    build_frontend_callback_url,
    build_social_authorization,
    complete_social_login,
    get_callback_state_data,
    get_default_frontend_origin,
    normalize_provider,
)
from .signup_protection import get_signup_challenge_payload
from .throttles import (
    LoginRateThrottle,
    RegisterBurstRateThrottle,
    RegisterShortWindowRateThrottle,
    RegisterSustainedRateThrottle,
    SocialLoginRateThrottle,
)
from .token_cookies import (
    clear_refresh_cookie,
    get_refresh_token_from_request,
    set_refresh_cookie,
)
from .user_deletion import delete_user_account
from .serializers import (
    PublicBrandingSerializer,
    UserSerializer,
    UserRegistrationSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    SocialAuthStartSerializer,
    SocialProvidersResponseSerializer,
    VerificationEmailRequestSerializer,
    VerifyEmailQuerySerializer,
)
from .verification import (
    get_request_ip_address,
    get_site_settings,
    get_user_verification_retry_after_seconds,
    is_email_verification_required,
    mask_email,
    send_verification_email,
    should_throttle_public_resend,
    VERIFICATION_EMAIL_COOLDOWN_SECONDS,
)

User = get_user_model()
logger = logging.getLogger(__name__)
INVALID_LOGIN_DETAIL = "No active account found with the given credentials."


class EmailVerificationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Email verification is temporarily unavailable. Please try again later."
    default_code = "email_verification_unavailable"


def get_request_origin(request):
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    if origin:
        return origin

    referer = (request.headers.get("Referer") or "").strip()
    if not referer:
        return ""

    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def has_trusted_refresh_origin(request):
    request_origin = get_request_origin(request)
    if not request_origin:
        return False

    trusted_origins = {
        origin.strip().rstrip("/")
        for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        if origin and origin.strip()
    }
    return request_origin in trusted_origins


def get_resend_verification_response():
    return {
        "detail": "If an eligible account exists, a verification email will arrive shortly.",
        "email_verification_required": True,
        "cooldown_seconds": VERIFICATION_EMAIL_COOLDOWN_SECONDS,
    }


def maybe_send_verification_email_or_raise(user):
    try:
        send_verification_email(user)
    except (ImproperlyConfigured, ValueError) as exc:
        logger.error("Verification email configuration error.", exc_info=True)
        raise EmailVerificationUnavailable() from exc
    except Exception as exc:
        logger.exception("Verification email delivery failed.")
        raise EmailVerificationUnavailable() from exc


def get_public_resend_user(identifier):
    normalized_identifier = (identifier or "").strip()
    if not normalized_identifier:
        return None

    return (
        User.objects.filter(
            Q(username__iexact=normalized_identifier) | Q(email__iexact=normalized_identifier),
            is_active=True,
        )
        .distinct()
        .first()
    )


def issue_refresh_token(user):
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    return refresh


def build_authenticated_response(user, *, message, status_code):
    refresh = issue_refresh_token(user)
    response = Response(
        {
            "user": UserSerializer(user).data,
            "access_token": str(refresh.access_token),
            "message": message,
        },
        status=status_code,
    )
    set_refresh_cookie(response, str(refresh))
    return response


def build_social_redirect_response(url, *, refresh_token=""):
    response = HttpResponseRedirect(url)
    if refresh_token:
        set_refresh_cookie(response, refresh_token)
    else:
        clear_refresh_cookie(response)
    return response


class RegisterView(generics.CreateAPIView):
    """
    User registration endpoint.
    POST: Create a new user account.
    """

    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer
    throttle_classes = [
        RegisterBurstRateThrottle,
        RegisterShortWindowRateThrottle,
        RegisterSustainedRateThrottle,
    ]

    def create(self, request, *args, **kwargs):
        site_settings = get_site_settings()
        verification_required = site_settings.require_email_verification
        serializer = self.get_serializer(data=request.data)
        serializer.context["site_settings"] = site_settings
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save(email_verified=not verification_required)

            if verification_required:
                maybe_send_verification_email_or_raise(user)

        response_payload = {
            "user": UserSerializer(user).data,
            "message": "User registered successfully.",
            "email_verification_required": verification_required,
            "email_hint": mask_email(user.email),
        }

        if verification_required:
            response_payload["message"] = "Registration successful. Please check your email to verify your account."
            return Response(response_payload, status=status.HTTP_201_CREATED)

        return build_authenticated_response(
            user,
            message="User registered successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class RegisterCaptchaView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            payload = get_signup_challenge_payload(get_site_settings())
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = Response(
            payload,
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-store"
        return response


class BrandingSettingsView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        response = Response(
            PublicBrandingSerializer(get_site_settings()).data,
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-store"
        return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    """
    User login endpoint.
    Accepts either username or email and returns user data with JWT tokens.
    """
    identifier = (request.data.get("username") or request.data.get("identifier") or "").strip()
    password = request.data.get("password") or ""

    if not identifier or not password:
        log_audit_event(
            "login_failure",
            outcome="failure",
            level="warning",
            request=request,
            identifier=identifier,
            reason="missing_credentials",
        )
        return Response(
            {"detail": "Username/email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = (
        User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
        .distinct()
        .first()
    )

    if not user or not user.check_password(password) or not user.is_active:
        log_audit_event(
            "login_failure",
            outcome="failure",
            level="warning",
            request=request,
            actor_user=user,
            identifier=identifier,
            reason="invalid_credentials",
        )
        return Response(
            {"detail": INVALID_LOGIN_DETAIL},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if is_email_verification_required() and not user.email_verified:
        log_audit_event(
            "login_failure",
            outcome="failure",
            level="warning",
            request=request,
            actor_user=user,
            identifier=identifier,
            reason="email_unverified",
        )
        return Response(
            {"detail": INVALID_LOGIN_DETAIL},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    log_audit_event(
        "login_success",
        request=request,
        actor_user=user,
        identifier=identifier,
    )
    return build_authenticated_response(
        user,
        message="Login successful.",
        status_code=status.HTTP_200_OK,
    )


class SocialProvidersView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response(SocialProvidersResponseSerializer.build(), status=status.HTTP_200_OK)


class SocialAuthStartView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [SocialLoginRateThrottle]
    serializer_class = SocialAuthStartSerializer

    def post(self, request, provider, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = build_social_authorization(
                request,
                provider,
                serializer.validated_data.get("next", ""),
            )
        except SocialAuthException as exc:
            return Response(
                {"detail": exc.detail, "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(payload, status=status.HTTP_200_OK)


class SocialAuthCallbackView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, provider, *args, **kwargs):
        normalized_provider = (provider or "").strip().lower()
        frontend_origin = get_default_frontend_origin()
        next_path = ""

        try:
            normalized_provider = normalize_provider(normalized_provider)
            _, _, frontend_origin, next_path = get_callback_state_data(
                request,
                normalized_provider,
            )
        except SocialAuthStateError as exc:
            fallback_url = build_frontend_callback_url(
                frontend_origin,
                status="error",
                provider=normalized_provider,
                detail=exc.detail,
            )
            if fallback_url:
                return build_social_redirect_response(fallback_url)
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SocialAuthException as exc:
            fallback_url = build_frontend_callback_url(
                frontend_origin,
                status="error",
                provider=normalized_provider,
                detail=exc.detail,
            )
            if fallback_url:
                return build_social_redirect_response(fallback_url)
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = complete_social_login(request, normalized_provider)
        except OAuthError as exc:
            detail = (
                getattr(exc, "description", "")
                or getattr(exc, "error", "")
                or "Social login was cancelled or denied."
            )
            logger.warning("Social login provider returned an OAuth error.", exc_info=True)
            return build_social_redirect_response(
                build_frontend_callback_url(
                    frontend_origin,
                    status="error",
                    provider=normalized_provider,
                    detail=detail,
                    next=next_path,
                )
            )
        except SocialAuthException as exc:
            logger.warning("Social login failed.", exc_info=True)
            return build_social_redirect_response(
                build_frontend_callback_url(
                    frontend_origin,
                    status="error",
                    provider=normalized_provider,
                    detail=exc.detail,
                    next=next_path,
                )
            )
        except Exception:
            logger.exception("Unexpected social login failure.")
            return build_social_redirect_response(
                build_frontend_callback_url(
                    frontend_origin,
                    status="error",
                    provider=normalized_provider,
                    detail="Social login could not be completed right now.",
                    next=next_path,
                )
            )

        if result.status == "verification_required":
            return build_social_redirect_response(
                build_frontend_callback_url(
                    result.frontend_origin,
                    status="verification_required",
                    provider=result.provider,
                    detail=result.detail,
                    email_hint=result.email_hint,
                    next=result.next_path,
                )
            )

        refresh = issue_refresh_token(result.user)
        log_audit_event(
            "login_success",
            request=request,
            actor_user=result.user,
            identifier=result.user.email,
            provider=result.provider,
        )
        return build_social_redirect_response(
            build_frontend_callback_url(
                result.frontend_origin,
                status="success",
                provider=result.provider,
                next=result.next_path,
            ),
            refresh_token=str(refresh),
        )


class VerifiedTokenRefreshView(TokenRefreshView):
    """Refresh tokens while enforcing email verification when required."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        body_refresh_token = (request.data.get("refresh") or "").strip()
        cookie_refresh_token = get_refresh_token_from_request(request)

        if cookie_refresh_token and not has_trusted_refresh_origin(request):
            log_audit_event(
                "token_refresh_denied",
                outcome="failure",
                level="warning",
                request=request,
                reason="untrusted_origin",
            )
            response = Response(
                {"detail": "Refresh request origin is not allowed."},
                status=status.HTTP_403_FORBIDDEN,
            )
            clear_refresh_cookie(response)
            return response

        refresh_token = body_refresh_token or cookie_refresh_token
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                user_id = token.get("user_id")
                user = User.objects.filter(pk=user_id).only("id", "email", "email_verified").first()
                if user and is_email_verification_required() and not user.email_verified:
                    log_audit_event(
                        "token_refresh_denied",
                        outcome="failure",
                        level="warning",
                        request=request,
                        actor_user=user,
                        reason="email_unverified",
                    )
                    response = Response(
                        {"detail": INVALID_LOGIN_DETAIL},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                    clear_refresh_cookie(response)
                    return response
            except TokenError:
                pass

        serializer = self.get_serializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError:
            response = Response({"detail": "Refresh token is invalid or expired."}, status=status.HTTP_401_UNAUTHORIZED)
            clear_refresh_cookie(response)
            return response

        response_payload = dict(serializer.validated_data)
        rotated_refresh = (response_payload.pop("refresh", "") or "").strip()
        response = Response(response_payload, status=status.HTTP_200_OK)
        if rotated_refresh:
            set_refresh_cookie(response, rotated_refresh)
        elif refresh_token:
            set_refresh_cookie(response, refresh_token)
        return response


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    """
    Idempotent logout endpoint.

    The cookie is always expired, including when the refresh token is missing,
    invalid, expired, or already blacklisted.
    """
    refresh_token = (
        (request.data.get("refresh_token") or "").strip()
        or get_refresh_token_from_request(request)
    )

    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            logger.info("Logout received an invalid, expired, or already cleared refresh token.")
        except Exception:
            logger.warning("Refresh token blacklist failed during logout.", exc_info=True)

    response = Response({"message": "Logout successful."}, status=status.HTTP_200_OK)
    clear_refresh_cookie(response)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_view(request):
    """
    Get current authenticated user.
    """
    serializer = UserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateProfileView(generics.UpdateAPIView):
    """
    Update user profile endpoint.
    PATCH/PUT: Update user profile information.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserUpdateSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        return self.request.user


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_verification_email_view(request):
    """Send a verification email for the authenticated user."""
    user = request.user

    if user.email_verified:
        return Response(
            {"detail": "Your email is already verified.", "email_verification_required": False},
            status=status.HTTP_200_OK,
        )

    retry_after_seconds = get_user_verification_retry_after_seconds(user)
    if retry_after_seconds > 0:
        return Response(
            {
                "detail": "Please wait before requesting another verification email.",
                "retry_after_seconds": retry_after_seconds,
                "email_verification_required": True,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    maybe_send_verification_email_or_raise(user)
    return Response(
        {
            "detail": "Verification email sent successfully.",
            "email_verification_required": True,
            "email_hint": mask_email(user.email),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification_email_view(request):
    """Public resend endpoint with generic responses to avoid account enumeration."""
    serializer = VerificationEmailRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if should_throttle_public_resend(get_request_ip_address(request)):
        return Response(get_resend_verification_response(), status=status.HTTP_200_OK)

    user = get_public_resend_user(serializer.validated_data["identifier"])
    if not user or user.email_verified or not is_email_verification_required():
        return Response(get_resend_verification_response(), status=status.HTTP_200_OK)

    retry_after_seconds = get_user_verification_retry_after_seconds(user)
    if retry_after_seconds > 0:
        return Response(get_resend_verification_response(), status=status.HTTP_200_OK)

    try:
        send_verification_email(user)
    except Exception:
        logger.exception("Public resend verification email failed.")

    return Response(get_resend_verification_response(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email_view(request):
    """Verify a user's email from a verification link."""
    serializer = VerifyEmailQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    verification_token = (
        EmailVerificationToken.objects.select_related("user")
        .filter(token=serializer.validated_data["token"])
        .first()
    )

    if not verification_token:
        return Response(
            {"detail": "Invalid or expired verification link."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = verification_token.user
    if verification_token.used:
        if user.email_verified:
            return Response(
                {"detail": "Email already verified.", "email_verified": True},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"detail": "Invalid or expired verification link."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if verification_token.is_expired:
        return Response(
            {"detail": "Invalid or expired verification link."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            activate_pending_social_accounts(user)
        verification_token.used = True
        verification_token.save(update_fields=["used"])

    return Response(
        {"detail": "Email verified successfully.", "email_verified": True},
        status=status.HTTP_200_OK,
    )


class ChangePasswordView(generics.UpdateAPIView):
    """
    Change user password endpoint.
    POST: Change user password.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Set new password
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        log_audit_event("password_change", request=request, actor_user=user)

        return Response(
            {"message": "Password changed successfully."}, status=status.HTTP_200_OK
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account_view(request):
    """
    Delete user account endpoint.
    DELETE: Delete the authenticated user's account.
    """
    user = request.user
    delete_user_account(user, request=request, actor_user=user, audit_event="account_delete")

    return Response(
        {"message": "Account deleted successfully."}, status=status.HTTP_200_OK
    )
