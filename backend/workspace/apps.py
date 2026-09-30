from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate, post_save


REVIEWER_GROUPS = (
    "citation_reviewer",
    "mapping_reviewer",
    "status_reviewer",
    "admin",
    "reviewer",
    "viewer",
)


def ensure_reviewer_groups(**kwargs):
    from django.contrib.auth.models import Group

    for name in REVIEWER_GROUPS:
        Group.objects.get_or_create(name=name)


def assign_default_role(sender, instance, created, raw=False, **kwargs):
    """Every new account starts with a role: Admin for a superuser, else Viewer.
    Covers email and social sign-up, createsuperuser and the admin site alike."""
    if not created or raw:
        return
    from django.contrib.auth.models import Group

    from .roles import ROLE_ADMIN, ROLE_GROUP_NAMES, ROLE_VIEWER

    if instance.groups.filter(name__in=ROLE_GROUP_NAMES).exists():
        return
    role = ROLE_ADMIN if instance.is_superuser else ROLE_VIEWER
    instance.groups.add(Group.objects.get_or_create(name=role)[0])


class WorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workspace"

    def ready(self):
        post_migrate.connect(
            ensure_reviewer_groups,
            sender=self,
            dispatch_uid="workspace.ensure_reviewer_groups",
        )
        post_save.connect(
            assign_default_role,
            sender=settings.AUTH_USER_MODEL,
            dispatch_uid="workspace.assign_default_role",
        )
