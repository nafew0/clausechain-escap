"""Which model backend's workspace a request works in.

One engine, two model backends: "hybrid" (Model A, the signed ESCAP registry)
and "local" (Model B, open weights). Each has its own snapshot, registry,
decisions and engine files, and a request sees exactly one of them, chosen by
``?mode=`` (default hybrid). The middleware stores it for the request so every
snapshot lookup, decision row, writer call and file path follows it; nothing
here ever mixes the two. Paths mirror engine/packages/core/review_layout.py.
"""

import contextvars
from pathlib import Path

from django.conf import settings

MODES = ("hybrid", "local")
MODE_ENV = "CLAUSECHAIN_REVIEW_MODE"

_mode = contextvars.ContextVar("clausechain_workspace_mode", default="hybrid")


def current_mode():
    return _mode.get()


def use_mode(mode):
    """Set the mode for the current context (tests, commands); returns a reset token."""
    return _mode.set(mode if mode in MODES else "hybrid")


def reset_mode(token):
    _mode.reset(token)


class WorkspaceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = use_mode(request.GET.get("mode") or "hybrid")
        try:
            return self.get_response(request)
        finally:
            reset_mode(token)


def engine_env(mode=None):
    """Environment for engine review scripts run on behalf of a mode."""
    return {MODE_ENV: mode or current_mode()}


def submission_dir(mode=None):
    root = Path(settings.ENGINE_ROOT) / "submission"
    return root / "local" if (mode or current_mode()) == "local" else root


def bundle_dir(mode=None):
    return submission_dir(mode) / "review"


def review_dir(mode=None):
    root = Path(settings.ENGINE_ROOT) / "data" / "review"
    return root / "local" if (mode or current_mode()) == "local" else root


def reports_dir(mode=None):
    root = Path(settings.ENGINE_ROOT) / "reports"
    return root / "local" if (mode or current_mode()) == "local" else root
