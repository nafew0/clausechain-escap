"""Account roles: Admin, Reviewer, Viewer (one per user, held as a group).

Existing accounts: superusers and the admin group become Admin; members of a
per-stage reviewer group become Reviewer; everyone else becomes Viewer.
"""
from django.db import migrations

STAGE_GROUPS = ("citation_reviewer", "mapping_reviewer", "status_reviewer")


def assign_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    groups = {name: Group.objects.get_or_create(name=name)[0] for name in ("admin", "reviewer", "viewer")}
    for user in User.objects.all():
        names = set(user.groups.values_list("name", flat=True))
        if user.is_superuser or "admin" in names:
            role = "admin"
        elif "reviewer" in names or names & set(STAGE_GROUPS):
            role = "reviewer"
        else:
            role = "viewer"
        user.groups.add(groups[role])


class Migration(migrations.Migration):
    dependencies = [
        ("workspace", "0013_corpus_action_kind"),
        ("accounts", "0006_rename_accounts_em_user_id_idx_accounts_em_user_id_6989e4_idx_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(assign_roles, migrations.RunPython.noop)]
