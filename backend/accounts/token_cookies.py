from django.conf import settings


def get_refresh_cookie_name():
    return getattr(settings, "AUTH_REFRESH_COOKIE_NAME", "reactdjango_refresh")


def get_refresh_token_from_request(request):
    return (request.COOKIES.get(get_refresh_cookie_name()) or "").strip()


def set_refresh_cookie(response, refresh_token):
    refresh_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    response.set_cookie(
        key=get_refresh_cookie_name(),
        value=refresh_token,
        max_age=int(refresh_lifetime.total_seconds()),
        httponly=True,
        secure=getattr(settings, "AUTH_REFRESH_COOKIE_SECURE", not settings.DEBUG),
        samesite=getattr(settings, "AUTH_REFRESH_COOKIE_SAMESITE", "Strict"),
        domain=getattr(settings, "AUTH_REFRESH_COOKIE_DOMAIN", None) or None,
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/api/auth/"),
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        key=get_refresh_cookie_name(),
        domain=getattr(settings, "AUTH_REFRESH_COOKIE_DOMAIN", None) or None,
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/api/auth/"),
        samesite=getattr(settings, "AUTH_REFRESH_COOKIE_SAMESITE", "Strict"),
    )
