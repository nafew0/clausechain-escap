import logging

from django.db import transaction

from clausechain.audit import log_audit_event


logger = logging.getLogger(__name__)


def _schedule_avatar_cleanup(user):
    avatar = getattr(user, "avatar", None)
    avatar_name = getattr(avatar, "name", "")
    if not avatar_name:
        return

    storage = avatar.storage

    def cleanup_avatar():
        try:
            storage.delete(avatar_name)
        except Exception:
            logger.exception("Failed to delete avatar file for deleted user.")

    transaction.on_commit(cleanup_avatar)


def delete_user_account(user, *, request=None, actor_user=None, audit_event="account_delete"):
    resolved_actor = actor_user
    request_user = getattr(request, "user", None)
    if resolved_actor is None and getattr(request_user, "is_authenticated", False):
        resolved_actor = request_user

    deleted_user = {
        "actor_user_id": str(resolved_actor.pk) if resolved_actor is not None else None,
        "deleted_user_id": str(user.pk),
        "deleted_username": user.username,
        "deleted_email": user.email,
        "had_avatar": bool(getattr(getattr(user, "avatar", None), "name", "")),
    }

    with transaction.atomic():
        _schedule_avatar_cleanup(user)
        user.delete()

    log_audit_event(
        audit_event,
        request=request,
        actor_user=actor_user,
        **deleted_user,
    )
    return deleted_user
