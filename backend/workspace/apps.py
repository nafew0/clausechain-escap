from django.apps import AppConfig
from django.db.models.signals import post_migrate


REVIEWER_GROUPS = (
    "citation_reviewer",
    "mapping_reviewer",
    "status_reviewer",
    "admin",
)


def ensure_reviewer_groups(**kwargs):
    from django.contrib.auth.models import Group

    for name in REVIEWER_GROUPS:
        Group.objects.get_or_create(name=name)


class WorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workspace"

    def ready(self):
        post_migrate.connect(
            ensure_reviewer_groups,
            sender=self,
            dispatch_uid="workspace.ensure_reviewer_groups",
        )
