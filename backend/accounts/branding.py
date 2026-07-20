import os
import uuid
from dataclasses import dataclass
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_BRANDING_ASSET_URLS = {
    "branding_logo": "/branding/logo.svg",
    "branding_favicon": "/branding/logo.ico",
    "branding_login_banner": "/branding/loginpage.webp",
    "branding_register_banner": "/branding/registerpage.webp",
}

BRANDING_ASSET_LABELS = {
    "branding_logo": "Logo",
    "branding_favicon": "Favicon",
    "branding_login_banner": "Login banner",
    "branding_register_banner": "Registration banner",
}

FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


@dataclass(frozen=True)
class BrandingAssetRule:
    label: str
    max_width: int
    max_height: int
    max_size_bytes: int
    allowed_formats: tuple[str, ...]


BRANDING_ASSET_RULES = {
    "branding_logo": BrandingAssetRule(
        label=BRANDING_ASSET_LABELS["branding_logo"],
        max_width=1600,
        max_height=600,
        max_size_bytes=3 * 1024 * 1024,
        allowed_formats=("PNG", "JPEG", "WEBP"),
    ),
    "branding_favicon": BrandingAssetRule(
        label=BRANDING_ASSET_LABELS["branding_favicon"],
        max_width=512,
        max_height=512,
        max_size_bytes=1024 * 1024,
        allowed_formats=("PNG", "WEBP"),
    ),
    "branding_login_banner": BrandingAssetRule(
        label=BRANDING_ASSET_LABELS["branding_login_banner"],
        max_width=2400,
        max_height=2400,
        max_size_bytes=5 * 1024 * 1024,
        allowed_formats=("PNG", "JPEG", "WEBP"),
    ),
    "branding_register_banner": BrandingAssetRule(
        label=BRANDING_ASSET_LABELS["branding_register_banner"],
        max_width=2400,
        max_height=2400,
        max_size_bytes=5 * 1024 * 1024,
        allowed_formats=("PNG", "JPEG", "WEBP"),
    ),
}


def branding_asset_upload_to(instance, filename):
    extension = os.path.splitext(filename or "")[1].lower()
    extension = extension if extension in {".jpg", ".jpeg", ".png", ".webp"} else ""
    return f"branding/{uuid.uuid4().hex}{extension}"


def get_branding_asset_limits():
    return {
        field_name: {
            "label": rule.label,
            "max_width": rule.max_width,
            "max_height": rule.max_height,
            "max_size_bytes": rule.max_size_bytes,
            "allowed_formats": [value.lower() for value in rule.allowed_formats],
        }
        for field_name, rule in BRANDING_ASSET_RULES.items()
    }


def has_custom_branding_asset(site_settings, field_name):
    file_field = getattr(site_settings, field_name, None)
    return bool(file_field and getattr(file_field, "name", ""))


def resolve_branding_asset_url(site_settings, field_name, *, public_app_url=""):
    file_field = getattr(site_settings, field_name, None)
    resolved_url = ""

    if file_field and getattr(file_field, "name", ""):
        try:
            resolved_url = file_field.url
        except ValueError:
            resolved_url = ""

    if not resolved_url:
        resolved_url = DEFAULT_BRANDING_ASSET_URLS[field_name]

    normalized_origin = (public_app_url or "").strip().rstrip("/")
    if normalized_origin and resolved_url.startswith("/"):
        return f"{normalized_origin}{resolved_url}"
    return resolved_url


def _build_sanitized_branding_filename(field_name, image_format):
    extension = FORMAT_EXTENSIONS[image_format]
    slug = field_name.replace("branding_", "").replace("_", "-")
    return f"{slug}-{uuid.uuid4().hex[:10]}{extension}"


def sanitize_branding_upload(uploaded_file, field_name):
    rule = BRANDING_ASSET_RULES[field_name]

    if uploaded_file.size > rule.max_size_bytes:
        limit_mb = rule.max_size_bytes / (1024 * 1024)
        raise ValueError(f"{rule.label} must be {limit_mb:.0f} MB or smaller.")

    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as image:
            image_format = (image.format or "").upper()
            if image_format not in rule.allowed_formats:
                allowed_formats = ", ".join(rule.allowed_formats)
                raise ValueError(
                    f"{rule.label} must be one of: {allowed_formats}."
                )

            normalized = ImageOps.exif_transpose(image)
            width, height = normalized.size
            if width > rule.max_width or height > rule.max_height:
                raise ValueError(
                    f"{rule.label} must be at most {rule.max_width}x{rule.max_height} pixels."
                )

            if image_format == "JPEG" and normalized.mode not in {"RGB", "L"}:
                normalized = normalized.convert("RGB")

            buffer = BytesIO()
            normalized.save(buffer, format=image_format)
            buffer.seek(0)
            return SimpleUploadedFile(
                _build_sanitized_branding_filename(field_name, image_format),
                buffer.getvalue(),
                content_type=FORMAT_CONTENT_TYPES[image_format],
            )
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Upload a valid image file for {rule.label.lower()}.") from exc
    finally:
        uploaded_file.seek(0)
