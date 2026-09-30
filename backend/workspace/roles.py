ROLE_GROUPS = {
    "citation": "citation_reviewer",
    "mapping": "mapping_reviewer",
    "status": "status_reviewer",
    "recall": "mapping_reviewer",
    "zone3": "mapping_reviewer",
    "admin": "admin",
}

REVIEWER_GROUPS = (
    "citation_reviewer",
    "mapping_reviewer",
    "status_reviewer",
    "admin",
)
STAGE_GROUPS = ("citation_reviewer", "mapping_reviewer", "status_reviewer")

# Account roles, one per user, held as a group. Admin runs the engine and manages
# users; Reviewer records decisions at every review stage; Viewer only reads.
ROLE_ADMIN, ROLE_REVIEWER, ROLE_VIEWER = "admin", "reviewer", "viewer"
ROLES = (ROLE_ADMIN, ROLE_REVIEWER, ROLE_VIEWER)
ROLE_DETAILS = {
    ROLE_ADMIN: {
        "label": "Admin",
        "description": "Runs pillars and every engine action, reviews at every stage, and manages users and roles.",
        "permissions": ["Run pillars, replay and refresh snapshots", "Record decisions at every review stage",
                        "Manage users and roles", "Read everything"],
    },
    ROLE_REVIEWER: {
        "label": "Reviewer",
        "description": "Records citation, mapping and status decisions, recall verdicts and indicator scores.",
        "permissions": ["Record decisions at every review stage", "Read everything"],
    },
    ROLE_VIEWER: {
        "label": "Viewer",
        "description": "Reads the workspace and downloads exports; cannot record decisions or run the engine.",
        "permissions": ["Read everything", "Download exports"],
    },
}
ROLE_GROUP_NAMES = ROLES + STAGE_GROUPS


def user_role(user):
    """The account role: superusers and the admin group are Admin; the reviewer
    group or any per-stage reviewer group is Reviewer; everyone else is Viewer."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLE_ADMIN
    groups = set(user.groups.filter(name__in=ROLE_GROUP_NAMES).values_list("name", flat=True))
    if ROLE_ADMIN in groups:
        return ROLE_ADMIN
    if ROLE_REVIEWER in groups or groups & set(STAGE_GROUPS):
        return ROLE_REVIEWER
    return ROLE_VIEWER


def is_admin(user):
    return user_role(user) == ROLE_ADMIN


def set_user_role(user, role):
    """Give a user exactly one role. Admin also carries superuser/staff, so every
    check that reads is_superuser (engine, admin API, Django admin) agrees."""
    from django.contrib.auth.models import Group

    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    user.groups.remove(*Group.objects.filter(name__in=ROLE_GROUP_NAMES))
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    is_admin_role = role == ROLE_ADMIN
    if user.is_superuser != is_admin_role or user.is_staff != is_admin_role:
        user.is_superuser = user.is_staff = is_admin_role
        user.save(update_fields=["is_superuser", "is_staff"])


def reviewer_roles(user):
    """Return the canonical review capabilities exposed to the client."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return ["admin"]
    groups = set(
        user.groups.filter(name__in=REVIEWER_GROUPS + (ROLE_REVIEWER,)).values_list("name", flat=True)
    )
    if "admin" in groups:
        return ["admin"]
    if ROLE_REVIEWER in groups:
        return list(STAGE_GROUPS)
    return [group for group in REVIEWER_GROUPS if group in groups]


def has_review_role(user, role):
    group = ROLE_GROUPS.get(role, role)
    capabilities = reviewer_roles(user)
    return "admin" in capabilities or group in capabilities


def reviewer_identity(user):
    return user.full_name, str(user.pk)


def decision_reviewer_role(user, stage):
    """Persist an admin override explicitly; otherwise retain the stage role."""
    return "admin" if "admin" in reviewer_roles(user) else stage
