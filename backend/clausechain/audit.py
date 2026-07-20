import json
import logging

from clausechain.client_ip import get_client_ip


audit_logger = logging.getLogger("audit")


def _normalize_audit_value(value):
    if value in (None, ""):
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        normalized = {
            key: _normalize_audit_value(item)
            for key, item in value.items()
        }
        return {
            key: item
            for key, item in normalized.items()
            if item not in (None, "", [], {})
        }

    if isinstance(value, (list, tuple, set)):
        normalized_items = [
            _normalize_audit_value(item)
            for item in value
        ]
        return [
            item
            for item in normalized_items
            if item not in (None, "", [], {})
        ]

    return str(value)


def build_audit_payload(
    event,
    *,
    outcome="success",
    request=None,
    actor_user=None,
    target_user=None,
    **fields,
):
    payload = {
        "event": event,
        "outcome": outcome,
    }

    if request is not None:
        payload["ip"] = get_client_ip(request) or ""
        payload["path"] = request.path
        payload["method"] = request.method

        request_user = getattr(request, "user", None)
        if actor_user is None and getattr(request_user, "is_authenticated", False):
            actor_user = request_user

    if actor_user is not None:
        payload["actor_user_id"] = str(actor_user.pk)

    if target_user is not None:
        payload["target_user_id"] = str(target_user.pk)

    payload.update(fields)

    normalized = {
        key: _normalize_audit_value(value)
        for key, value in payload.items()
    }
    return {
        key: value
        for key, value in normalized.items()
        if value not in (None, "", [], {})
    }


def log_audit_event(
    event,
    *,
    outcome="success",
    level="info",
    request=None,
    actor_user=None,
    target_user=None,
    **fields,
):
    payload = build_audit_payload(
        event,
        outcome=outcome,
        request=request,
        actor_user=actor_user,
        target_user=target_user,
        **fields,
    )
    log_method = getattr(audit_logger, level, audit_logger.info)
    log_method(json.dumps(payload, sort_keys=True, default=str))
