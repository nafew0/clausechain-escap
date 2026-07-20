"""Create/refresh the public read-only demo account shown on the login page.

The viewer is a plain authenticated user with NO reviewer groups and no staff
bits: every decision endpoint requires a reviewer role (workspace.views
require_role) and run-launch requires superuser, so this account can browse the
entire workspace but cannot write anything. Idempotent — safe to run on every
deploy.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEMO_USERNAME = "viewer"
DEMO_EMAIL = "viewer@clausechain.demo"
DEMO_PASSWORD = "escap-rdtii-2026"  # intentionally public: read-only account


class Command(BaseCommand):
    help = "Ensure the public read-only demo viewer account exists"

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"email": DEMO_EMAIL, "first_name": "Demo",
                      "last_name": "Viewer", "email_verified": True},
        )
        user.email = DEMO_EMAIL
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.email_verified = True
        user.set_password(DEMO_PASSWORD)
        user.save()
        user.groups.clear()  # NO reviewer roles: read-only by construction
        self.stdout.write(f"demo viewer {'created' if created else 'refreshed'}: "
                          f"{DEMO_USERNAME} / {DEMO_PASSWORD} (read-only)")
