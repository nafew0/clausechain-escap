import os
from io import BytesIO

from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from subscriptions.serializers import PlanSummarySerializer
from subscriptions.services import LicenseService

from .branding import resolve_branding_asset_url
from .signup_protection import (
    GENERIC_SIGNUP_FAILURE_MESSAGE,
    is_disposable_email_domain,
    validate_signup_captcha,
    validate_signup_request_token,
)
from .social_auth import get_social_provider_statuses, sanitize_next_path
from .verification import get_site_settings

User = get_user_model()
FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".gif": "GIF",
}


def _normalize_avatar_frame(frame, image_format):
    normalized = ImageOps.exif_transpose(frame)
    if image_format == "JPEG" and normalized.mode not in {"RGB", "L"}:
        normalized = normalized.convert("RGB")
    return normalized.copy()


def sanitize_avatar_upload(uploaded_file):
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as image:
        image_format = (image.format or "").upper()
        if image_format not in FORMAT_CONTENT_TYPES:
            extension = os.path.splitext(uploaded_file.name or "")[1].lower()
            image_format = EXTENSION_FORMATS.get(extension, "PNG")

        if getattr(image, "is_animated", False):
            frames = [
                _normalize_avatar_frame(frame.copy(), image_format)
                for frame in ImageSequence.Iterator(image)
            ]
        else:
            frames = [_normalize_avatar_frame(image, image_format)]

        buffer = BytesIO()
        save_kwargs = {}
        if len(frames) > 1 and image_format in {"GIF", "WEBP"}:
            save_kwargs["save_all"] = True
            save_kwargs["append_images"] = frames[1:]
            if "duration" in image.info:
                save_kwargs["duration"] = image.info["duration"]
            if "loop" in image.info:
                save_kwargs["loop"] = image.info["loop"]

        frames[0].save(buffer, format=image_format, **save_kwargs)
        buffer.seek(0)

        return SimpleUploadedFile(
            uploaded_file.name,
            buffer.getvalue(),
            content_type=FORMAT_CONTENT_TYPES.get(image_format, "application/octet-stream"),
        )


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    current_plan = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "bio",
            "avatar",
            "organization",
            "designation",
            "phone",
            "is_superuser",
            "email_verified",
            "current_plan",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_superuser", "created_at", "updated_at"]

    def get_current_plan(self, obj):
        plan = LicenseService.get_user_plan(obj)
        return PlanSummarySerializer(plan).data


class PublicBrandingSerializer(serializers.Serializer):
    branding_logo_url = serializers.SerializerMethodField()
    branding_favicon_url = serializers.SerializerMethodField()
    branding_login_banner_url = serializers.SerializerMethodField()
    branding_register_banner_url = serializers.SerializerMethodField()

    def get_branding_logo_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_logo")

    def get_branding_favicon_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_favicon")

    def get_branding_login_banner_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_login_banner")

    def get_branding_register_banner_url(self, obj):
        return resolve_branding_asset_url(obj, "branding_register_banner")


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)
    captcha_id = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=255)
    captcha_answer = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=64
    )
    registration_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512
    )
    company_website = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=255
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "organization",
            "captcha_id",
            "captcha_answer",
            "registration_token",
            "company_website",
        ]

    def get_site_settings(self):
        return self.context.get("site_settings") or get_site_settings()

    def validate_email(self, value):
        normalized = (value or "").strip()
        if not normalized:
            raise serializers.ValidationError("Email is required.")

        site_settings = self.get_site_settings()
        if (
            site_settings.signup_disposable_email_blocking_enabled
            and is_disposable_email_domain(normalized)
        ):
            raise serializers.ValidationError(
                "Disposable email addresses are not allowed. Use a regular inbox."
            )
        return normalized

    def validate(self, attrs):
        """Validate that passwords match."""
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )

        if (attrs.get("company_website") or "").strip():
            raise serializers.ValidationError(
                {"non_field_errors": [GENERIC_SIGNUP_FAILURE_MESSAGE]}
            )

        try:
            validate_signup_request_token(attrs.get("registration_token", ""))
        except ValueError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": [str(exc) or GENERIC_SIGNUP_FAILURE_MESSAGE]}
            ) from exc

        try:
            validate_signup_captcha(
                self.get_site_settings(),
                captcha_id=attrs.get("captcha_id", ""),
                captcha_answer=attrs.get("captcha_answer", ""),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"captcha_answer": str(exc)}) from exc
        return attrs

    def create(self, validated_data):
        """Create a new user with encrypted password."""
        for field_name in (
            "password2",
            "captcha_id",
            "captcha_answer",
            "registration_token",
            "company_website",
        ):
            validated_data.pop(field_name, None)
        user = User.objects.create_user(**validated_data)
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "bio",
            "avatar",
            "organization",
            "designation",
            "phone",
        ]

    def validate(self, attrs):
        if "email" in getattr(self, "initial_data", {}):
            raise serializers.ValidationError(
                {
                    "email": "Email changes require a dedicated verification flow and are not available here."
                }
            )
        return attrs

    def validate_phone(self, value):
        """Allow common international phone formats without being overly strict."""
        normalized = (value or "").strip()
        if not normalized:
            return ""

        allowed_characters = set("0123456789+()-. ")
        if any(character not in allowed_characters for character in normalized):
            raise serializers.ValidationError(
                "Phone number may contain only digits, spaces, and + ( ) - . characters."
            )
        return normalized

    def validate_avatar(self, value):
        """Validate avatar uploads to common safe image formats and a sane size."""
        if not value:
            return value

        max_size_bytes = 5 * 1024 * 1024
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        allowed_content_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
        }

        if value.size > max_size_bytes:
            raise serializers.ValidationError("Avatar image must be 5 MB or smaller.")

        extension = os.path.splitext(value.name or "")[1].lower()
        if extension and extension not in allowed_extensions:
            raise serializers.ValidationError(
                "Avatar must be a JPG, PNG, WEBP, or GIF image."
            )

        content_type = getattr(value, "content_type", "")
        if content_type and content_type.lower() not in allowed_content_types:
            raise serializers.ValidationError(
                "Avatar must be a JPG, PNG, WEBP, or GIF image."
            )

        try:
            image = Image.open(value)
            image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise serializers.ValidationError("Upload a valid image file.") from exc
        finally:
            value.seek(0)

        try:
            return sanitize_avatar_upload(value)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise serializers.ValidationError("Upload a valid image file.") from exc


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing user password."""

    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True, write_only=True, validators=[validate_password]
    )
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        """Validate that new passwords match."""
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password": "Password fields didn't match."}
            )
        return attrs

    def validate_old_password(self, value):
        """Validate that old password is correct."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class VerificationEmailRequestSerializer(serializers.Serializer):
    """Public resend request payload."""

    identifier = serializers.CharField(required=True, max_length=255)

    def validate_identifier(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Identifier is required.")
        return normalized


class PasswordResetRequestSerializer(serializers.Serializer):
    """Public forgot-password request payload."""

    identifier = serializers.CharField(required=True, max_length=255)

    def validate_identifier(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Identifier is required.")
        return normalized


class VerifyEmailQuerySerializer(serializers.Serializer):
    """Verification query string payload."""

    token = serializers.CharField(required=True, max_length=64)

    def validate_token(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Verification token is required.")
        if len(normalized) != 64:
            raise serializers.ValidationError("Verification token is invalid.")
        return normalized


class SocialProviderSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    enabled = serializers.BooleanField()
    configured = serializers.BooleanField()
    available = serializers.BooleanField()
    source = serializers.CharField()


class SocialProvidersResponseSerializer(serializers.Serializer):
    providers = SocialProviderSerializer(many=True)

    @staticmethod
    def build(site_settings_obj=None):
        return {
            "providers": [
                {
                    "id": status.id,
                    "name": status.name,
                    "enabled": status.enabled,
                    "configured": status.configured,
                    "available": status.available,
                    "source": status.source,
                }
                for status in get_social_provider_statuses(site_settings_obj)
            ]
        }


class SocialAuthStartSerializer(serializers.Serializer):
    next = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_next(self, value):
        return sanitize_next_path(value)
