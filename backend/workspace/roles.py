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


def reviewer_roles(user):
    """Return the canonical review capabilities exposed to the client."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return ["admin"]
    groups = set(
        user.groups.filter(name__in=REVIEWER_GROUPS).values_list("name", flat=True)
    )
    if "admin" in groups:
        return ["admin"]
    return [group for group in REVIEWER_GROUPS if group in groups]


def has_review_role(user, role):
    group = ROLE_GROUPS.get(role, role)
    capabilities = reviewer_roles(user)
    return "admin" in capabilities or group in capabilities


def reviewer_identity(user):
    return user.full_name, str(user.pk)
