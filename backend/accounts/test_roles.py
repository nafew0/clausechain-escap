"""Account roles: Admin, Reviewer, Viewer (workspace.roles)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from workspace.roles import has_review_role, reviewer_roles, user_role

User = get_user_model()


class AccountRoleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="lead", email="lead@example.com", password="SafePass123!",
            first_name="Team", last_name="Lead", email_verified=True)
        self.member = User.objects.create_user(
            username="member", email="member@example.com", password="SafePass123!",
            first_name="Legal", last_name="Member", email_verified=True)

    def patch_role(self, user, role):
        return self.client.patch(f"/api/admin/users/{user.pk}/", {"role": role}, format="json")

    def test_new_accounts_start_as_viewer_and_superusers_as_admin(self):
        self.assertEqual(user_role(self.member), "viewer")
        self.assertEqual(user_role(self.admin), "admin")
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/auth/user/").data["role"], "viewer")

    def test_viewer_is_read_only(self):
        self.assertEqual(reviewer_roles(self.member), [])
        self.assertFalse(has_review_role(self.member, "citation"))
        self.client.force_authenticate(self.member)
        response = self.client.post("/api/workspace/decisions/findings/", {
            "finding_key": "1" * 64, "queue": "new", "review_stage": "citation",
            "decision": "approved", "citation_checked": True, "expected_latest_decision_id": None,
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/admin/_gate/").status_code, 403)

    def test_admin_makes_a_reviewer_who_reviews_every_stage_but_cannot_run_pillars(self):
        self.client.force_authenticate(self.admin)
        response = self.patch_role(self.member, "reviewer")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["role"], "reviewer")
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser)
        self.assertEqual(reviewer_roles(self.member), ["citation_reviewer", "mapping_reviewer", "status_reviewer"])
        for stage in ("citation", "mapping", "status", "recall", "zone3"):
            self.assertTrue(has_review_role(self.member, stage))
        self.client.force_authenticate(self.member)
        run = self.client.post("/api/workspace/engine/run/", {"economy": "Singapore", "pillar": 6}, format="json")
        self.assertEqual(run.status_code, 403)
        self.assertEqual(self.client.post("/api/workspace/engine/replay/", {}, format="json").status_code, 403)

    def test_admin_role_carries_superuser_and_can_be_removed(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.patch_role(self.member, "admin").status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_superuser and self.member.is_staff)
        self.assertEqual(self.patch_role(self.member, "viewer").status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser or self.member.is_staff)
        self.assertEqual(user_role(self.member), "viewer")

    def test_role_changes_keep_an_admin_in_charge(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.patch_role(self.admin, "viewer").status_code, 400)  # own role
        other = User.objects.create_superuser(username="second", email="second@example.com", password="SafePass123!")
        self.client.force_authenticate(other)
        self.assertEqual(self.patch_role(self.admin, "reviewer").status_code, 200)
        # An admin can demote another admin, never themselves, so an admin always remains.
        third = User.objects.create_superuser(username="third", email="third@example.com", password="SafePass123!")
        self.client.force_authenticate(third)
        self.assertEqual(self.patch_role(third, "viewer").status_code, 400)  # own role
        self.assertEqual(self.patch_role(other, "viewer").status_code, 200)
        self.client.force_authenticate(third)
        other.refresh_from_db()
        self.assertEqual(user_role(other), "viewer")
        self.assertEqual(user_role(third), "admin")

    def test_roles_endpoint_lists_the_three_roles_with_members(self):
        self.client.force_authenticate(self.admin)
        roles = {role["key"]: role for role in self.client.get("/api/admin/roles/").data["roles"]}
        self.assertEqual(list(roles), ["admin", "reviewer", "viewer"])
        self.assertTrue(roles["viewer"]["default_for_new_users"])
        self.assertEqual(roles["admin"]["user_count"], 1)
        self.assertEqual([m["username"] for m in roles["viewer"]["members"]], ["member"])
        users = self.client.get("/api/admin/users/?role=viewer").data["results"]
        self.assertEqual([u["username"] for u in users], ["member"])
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/admin/roles/").status_code, 403)
