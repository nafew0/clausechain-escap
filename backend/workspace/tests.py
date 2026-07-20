import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User

from .importer import SnapshotImportError, import_snapshot
from .decision_writer import (
    DecisionWriterConflict,
    apply_authoritative_decision,
    decision_domain_lock,
)
from .keys import recall_key, zone3_key
from .models import (
    CorrectionRequest,
    EngineSnapshot,
    EngineAction,
    EvidenceRow,
    FindingDecision,
    RecallDecision,
    ReviewItem,
    SnapshotArtifact,
    Zone3Decision,
)
from .engine_worker import EngineWorkerError, build_allowlisted_command, execute_action


HASH = "a" * 64
RECEIPT = {"sha256": "b" * 64, "path": "data/review/decisions.json"}
PROOF_FILENAME = f"{'c' * 64}.png"


def minimal_artifacts():
    common_headers = ["Economy", "Indicator", "Law/instrument", "Article/section"]
    absence_headers = [
        "Economy",
        "Indicator",
        "Configured governing instrument",
        "Official source URL",
    ]
    recall_headers = [
        "Economy",
        "Indicator",
        "Master act/instrument",
        "Master citation",
    ]
    zone_headers = ["Economy", "Indicator"]
    new_row = ["Singapore", "P6-I4", "Privacy Act", "s. 26"]
    known_row = ["Singapore", "P7-I1", "Privacy Act", "s. 3"]
    absence_row = ["Singapore", "P6-I1", "Privacy Act", "https://official.example"]
    key_rows = [
        {
            "finding_key": "1" * 64,
            "economy": "Singapore",
            "indicator": "P6-I4",
            "law": "Privacy Act",
            "article": "s. 26",
            "is_absence": False,
            "blocked": False,
            "proof_asset": f"assets/{PROOF_FILENAME}",
        },
        {
            "finding_key": "2" * 64,
            "economy": "Singapore",
            "indicator": "P7-I1",
            "law": "Privacy Act",
            "article": "s. 3",
            "is_absence": False,
            "blocked": False,
            "proof_asset": None,
        },
        {
            "finding_key": "3" * 64,
            "economy": "Singapore",
            "indicator": "P6-I1",
            "law": "Privacy Act",
            "article": "n/a",
            "is_absence": True,
            "blocked": True,
            "proof_asset": None,
        },
    ]
    for index, item in enumerate(key_rows, start=4):
        item["review_subject_hash"] = str(index) * 64
    consolidated = [
        {
            "Economy": item["economy"],
            "Indicator ID": item["indicator"],
            "Law Name": item["law"],
            "Article / Section": item["article"],
            "Discovery Tag": "KNOWN",
            "Status": "in_force",
            "status_evidence": "Official current compilation",
            "status_evidence_record": {"status": "in_force", "conflicting": False},
            "citation_proof": (
                None
                if item["is_absence"]
                else {
                    "alignment_status": "exact" if item["finding_key"] == "1" * 64 else "anchor",
                    "alignment_score": 1.0,
                    "source_sha256": "d" * 64,
                    "article_path": ["section 26"],
                }
            ),
            "Source URL": "https://official.example/statute",
            "archived_copy": "data/raw/statute.html",
            "access_date": "2026-07-18",
            "citation_tier": "[verified]",
            "Verbatim Snippet": "An exact statutory quotation.",
            "raw_context": "Context before. An exact statutory quotation. Context after.",
            "search_coverage_manifest": (
                {
                    "portals": ["Official register"],
                    "instruments": [item["law"]],
                    "unresolved_failures": [],
                }
                if item["is_absence"]
                else None
            ),
        }
        for item in key_rows
    ]
    return {
        "payload": {
            "schema_version": "2",
            "generated_at": "2026-07-18T12:00:00Z",
            "counts": {"new": 1, "known": 1, "absence": 1, "recall": 1, "zone3": 1},
            "refuter_status": "ready",
            "sheets": {
                "NEW Findings": {"headers": common_headers, "rows": [new_row]},
                "Absence Review": {"headers": absence_headers, "rows": [absence_row]},
                "Recall Misses": {
                    "headers": recall_headers,
                    "rows": [["Singapore", "P7-I3", "Employment Act", "s. 95"]],
                },
                "Zone-3 Scores": {
                    "headers": zone_headers,
                    "rows": [["Singapore", "P7-I3"]],
                },
                "KNOWN Findings": {"headers": common_headers, "rows": [known_row]},
                "Indicator Criteria": {
                    "headers": ["Indicator", "Legal question", "Scoring criteria", "Exclusions", "Polarity"],
                    "rows": [["P6-I4", "Are transfers conditional?", '{"1":"Yes","0":"No"}', "[]", "positive"]],
                },
                "Master Known": {
                    "headers": ["Economy", "Indicator", "Methodology score", "Act/instrument", "Article references"],
                    "rows": [["Singapore", "P6-I4", "1", "Privacy Act", "s. 26"]],
                },
            },
        },
        "key_map": {"rows": key_rows},
        "consolidated": {"rows": consolidated},
        "champion": {"status": "FAIL", "failures": ["human review pending"]},
        "costs": [],
        "runs": {f"run-{index}": {"country": "SG", "pillar": 6} for index in range(6)},
        "ops_stats": {
            "schema_version": 1,
            "generated_at": "2026-07-18T12:00:00Z",
            "acquisition": [{"id": "artifact-1", "economy": None, "sha256": HASH}],
            "eligibility": [{"instrument": "Privacy Act", "units": 10, "evidence_eligible": 9}],
            "extraction": [{"instrument": "Privacy Act", "methods": {"native_text": 10}}],
        },
        "configs": {
            "jurisdictions": {
                code: {"jurisdiction": code, "name": name}
                for code, name in (("SG", "Singapore"), ("MY", "Malaysia"), ("AU", "Australia"))
            },
            "seeds": {"economies": {"Singapore": []}},
        },
        "graph_snapshot": {
            "status": "verified",
            "origin": "neo4j",
            "schema_version": 3,
            "checks": {"schema": True},
            "nodes": [{"id": "p1", "labels": ["Provision"], "properties": {"economy": "Singapore", "law_name": "Privacy Act", "finding_key": "1" * 64}}],
            "edges": [],
        },
    }


class SnapshotImportTests(TestCase):
    def test_import_is_atomic_idempotent_and_builds_all_domains(self):
        snapshot, created = import_snapshot(minimal_artifacts())
        self.assertTrue(created)
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.review_items.count(), 5)
        self.assertEqual(snapshot.evidence_rows.count(), 3)
        self.assertEqual(snapshot.run_records.count(), 6)
        self.assertEqual(
            snapshot.reference_json["indicator_criteria"]["rows"][0][0], "P6-I4"
        )
        self.assertFalse(
            snapshot.review_items.get(queue=ReviewItem.Queue.ABSENCE).blocked
        )
        self.assertEqual(
            snapshot.review_items.get(queue=ReviewItem.Queue.RECALL).stable_key,
            recall_key("Singapore", "P7-I3", "Employment Act", "s. 95"),
        )
        self.assertEqual(
            snapshot.review_items.get(queue=ReviewItem.Queue.ZONE3).stable_key,
            zone3_key("Singapore", "P7-I3"),
        )

        same, created = import_snapshot(minimal_artifacts())
        self.assertFalse(created)
        self.assertEqual(same.pk, snapshot.pk)
        self.assertEqual(EngineSnapshot.objects.count(), 1)

        refreshed = minimal_artifacts()
        refreshed["payload"]["generated_at"] = "2026-07-18T12:05:00Z"
        same, created = import_snapshot(refreshed)
        self.assertFalse(created)
        self.assertEqual(same.pk, snapshot.pk)

    def test_missing_finding_mapping_rolls_back(self):
        artifacts = minimal_artifacts()
        artifacts["key_map"]["rows"] = []
        with self.assertRaises(SnapshotImportError):
            import_snapshot(artifacts)
        self.assertEqual(EngineSnapshot.objects.count(), 0)


class WorkspaceApiTests(TestCase):
    def setUp(self):
        self.snapshot, _ = import_snapshot(minimal_artifacts())
        self.client = APIClient()
        self.citation = self.make_user(
            "citation", "Citation Reviewer", "citation_reviewer"
        )
        self.mapping = self.make_user("mapping", "Mapping Reviewer", "mapping_reviewer")
        self.status_user = self.make_user(
            "status", "Status Reviewer", "status_reviewer"
        )

    def make_user(self, username, full_name, group_name):
        first_name, last_name = full_name.split(" ", 1)
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="SafePass123!",
            first_name=first_name,
            last_name=last_name,
            email_verified=True,
        )
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        return user

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def test_read_apis_require_auth_and_expose_real_snapshot(self):
        self.assertEqual(self.client.get("/api/workspace/summary/").status_code, 401)
        self.authenticate(self.citation)
        response = self.client.get("/api/workspace/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["counts"]["new"], 1)
        response = self.client.get("/api/workspace/review/new/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["finding_key"], "1" * 64)
        response = self.client.get(
            "/api/workspace/evidence/?pillar=6&economy=Singapore"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        response = self.client.get(f"/api/workspace/evidence/{'1' * 64}/")
        self.assertEqual(
            response.data["proof_asset_url"],
            f"/api/workspace/proof/{PROOF_FILENAME}/",
        )
        self.assertEqual(
            self.client.get("/api/workspace/runs/").data["results"].__len__(), 6
        )
        context = self.client.get(f"/api/workspace/review-context/new/{'1' * 64}/")
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.data["indicator_criteria"]["Indicator"], "P6-I4")
        self.assertEqual(context.data["master_known"][0]["Act/instrument"], "Privacy Act")
        self.assertEqual(context.data["score_semantics"]["level"], "indicator")
        self.assertTrue(context.data["approval_eligibility"]["eligible"])

        runs = self.client.get("/api/workspace/runs/").data
        self.assertEqual(len(runs["results"]), 6)
        self.assertEqual(runs["results"][0]["rows_produced"], 0)
        self.assertIn("champion", runs)

        submission = self.client.get("/api/workspace/submission/?economy=Singapore")
        self.assertEqual(submission.status_code, 200)
        self.assertEqual(submission.data["count"], 3)
        self.assertEqual(len(submission.data["template_columns"]), 13)
        self.assertIn("verification", submission.data["results"][0])
        self.assertFalse(submission.data["final_artifacts"]["available"])

    def test_summary_uses_canonical_reviewer_capabilities(self):
        self.authenticate(self.citation)
        self.assertEqual(
            self.client.get("/api/workspace/summary/").data["reviewer_roles"],
            ["citation_reviewer"],
        )

        superuser = User.objects.create_superuser(
            username="root-reviewer",
            email="root-reviewer@example.com",
            password="SafePass123!",
        )
        self.authenticate(superuser)
        self.assertEqual(
            self.client.get("/api/workspace/summary/").data["reviewer_roles"],
            ["admin"],
        )

    def test_d6r_read_apis_are_real_read_only_and_path_safe(self):
        self.authenticate(self.citation)
        summary = self.client.get("/api/workspace/summary/")
        self.assertEqual(len(summary.data["runs"]), 6)
        ops = self.client.get("/api/workspace/ops-stats/")
        self.assertEqual(ops.status_code, 200)
        self.assertEqual(ops.data["ops_stats"]["acquisition"][0]["id"], "artifact-1")
        config = self.client.get("/api/workspace/config/")
        self.assertEqual([row["code"] for row in config.data["jurisdictions"]], ["SG", "MY", "AU"])
        self.assertEqual(self.client.post("/api/workspace/config/", {}, format="json").status_code, 405)
        manifest = self.client.get("/api/workspace/raw/")
        self.assertGreaterEqual(manifest.data["count"] if "count" in manifest.data else len(manifest.data["results"]), 1)
        artifact = self.snapshot.artifacts.get(key="ops-stats")
        detail = self.client.get("/api/workspace/raw/ops-stats/")
        self.assertEqual(detail.data["artifact"]["sha256"], artifact.sha256)
        download = self.client.get("/api/workspace/raw/ops-stats/download/")
        self.assertEqual(download["X-Content-SHA256"], artifact.sha256)
        self.assertEqual(download.content.decode("utf-8"), artifact.raw_text)
        self.assertEqual(self.client.get("/api/workspace/raw/../../etc/passwd/").status_code, 404)
        graph = self.client.get("/api/workspace/knowledge-graph/")
        self.assertEqual(graph.data["status"], "verified")
        subgraph = self.client.get("/api/workspace/knowledge-graph/subgraph/?economy=Singapore")
        self.assertLessEqual(len(subgraph.data["nodes"]), 500)
        invalid = self.client.get("/api/workspace/knowledge-graph/subgraph/?relationship=DELETE")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.client.post("/api/workspace/knowledge-graph/", {}, format="json").status_code, 405)

    def test_snapshot_artifacts_are_append_only(self):
        artifact = self.snapshot.artifacts.get(key="ops-stats")
        artifact.raw_text = "mutated"
        with self.assertRaises(DjangoValidationError):
            artifact.save()

    def test_engine_actions_are_superuser_only_and_deduplicated(self):
        self.authenticate(self.citation)
        self.assertEqual(
            self.client.post("/api/workspace/engine/replay/", {}, format="json").status_code,
            403,
        )
        admin = self.make_user("admin", "Admin User", "admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save(update_fields=("is_superuser", "is_staff"))
        self.authenticate(admin)
        response = self.client.post("/api/workspace/engine/replay/", {}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "queued")
        self.assertEqual(
            self.client.post("/api/workspace/engine/replay/", {}, format="json").status_code,
            409,
        )
        self.assertEqual(self.client.get("/api/workspace/engine/actions/").status_code, 200)
        invalid = self.client.post(
            "/api/workspace/engine/run/",
            {"economy": "Neverland", "pillar": 6},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_worker_executes_only_allowlisted_commands_and_hashes_artifacts(self):
        admin = self.make_user("worker-admin", "Worker Admin", "admin")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "submission").mkdir()
            final_csv = root / "submission" / "consolidated_final.csv"
            final_json = root / "submission" / "consolidated_final.json"
            final_csv.write_text("Economy\nSingapore\n", encoding="utf-8")
            final_json.write_text('{"rows": [{"Economy": "Singapore"}]}', encoding="utf-8")
            allowlist = root / "allowlist.json"
            allowlist.write_text(
                json.dumps(
                    {
                        "actions": {
                            "replay": {
                                "argv": [".venv/bin/python", "scripts/submission_replay.py"],
                                "params": {},
                                "timeout_s": 30,
                            },
                            "run_pipeline": {
                                "argv": ["python", "run.py", "--economy", "{economy}"],
                                "params": {"economy": {"enum": ["Singapore"]}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            action = EngineAction.objects.create(
                kind=EngineAction.Kind.REPLAY,
                arguments_json={"action": "replay"},
                requested_by=admin,
            )
            with override_settings(ENGINE_ROOT=root, ENGINE_ALLOWLIST=allowlist), patch(
                "workspace.engine_worker.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="submission replay: 1", stderr=""),
            ), patch(
                "workspace.engine_worker.import_snapshot",
                return_value=(self.snapshot, False),
            ):
                execute_action(action)
                action.refresh_from_db()
                self.assertEqual(action.status, EngineAction.Status.SUCCEEDED)
                self.assertIn("submission/consolidated_final.csv", action.result_hashes_json)
                with self.assertRaises(EngineWorkerError):
                    build_allowlisted_command(
                        {"action": "run_pipeline", "economy": "Singapore; rm -rf /"}
                    )

    def test_source_match_supports_exact_anchor_blocked_and_queue_navigation(self):
        self.authenticate(self.citation)
        exact_key = "1" * 64
        anchor_key = "2" * 64
        blocked_key = "3" * 64

        response = self.client.get(
            f"/api/workspace/source-match/{exact_key}/?queue=new"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["match"]["mode"], "exact")
        self.assertEqual(response.data["match"]["label"], "VERBATIM · exact")
        self.assertEqual(response.data["source_sha256"], "d" * 64)
        self.assertEqual(response.data["navigation"]["total"], 1)

        response = self.client.get(f"/api/workspace/source-match/{anchor_key}/")
        self.assertEqual(response.data["match"]["mode"], "anchor")
        self.assertIsNone(response.data["proof_asset_url"])
        self.assertIn("Context before", response.data["row"]["raw_context"])

        response = self.client.get(f"/api/workspace/source-match/{blocked_key}/")
        self.assertEqual(response.data["match"]["mode"], "blocked")
        self.assertTrue(response.data["blocked"])
        self.assertTrue(response.data["block_reason"])

    def test_proof_asset_is_authenticated_and_served_from_engine_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = root / "submission" / "review" / "assets"
            asset_dir.mkdir(parents=True)
            (asset_dir / PROOF_FILENAME).write_bytes(b"png-proof")
            url = f"/api/workspace/proof/{PROOF_FILENAME}/"
            with override_settings(ENGINE_ROOT=root):
                self.client.force_authenticate(user=None)
                self.assertEqual(self.client.get(url).status_code, 401)
                self.authenticate(self.citation)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"png-proof")
                self.assertEqual(
                    self.client.get("/api/workspace/proof/not-a-proof.png/").status_code,
                    404,
                )

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_staged_reviews_require_distinct_users_and_are_append_only(self, writer):
        key = "1" * 64
        self.authenticate(self.citation)
        citation_response = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": key,
                "queue": "new",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "status_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(citation_response.status_code, 201, citation_response.data)
        self.assertEqual(citation_response.data["outcome"], "stage_recorded")
        self.assertFalse(citation_response.data["engine_exported"])
        citation_row = FindingDecision.objects.get()
        self.assertIsNone(citation_response.data["review_state"]["decision"])
        with self.assertRaises(DjangoValidationError):
            citation_row.save()

        self.authenticate(self.mapping)
        mapping_response = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": key,
                "queue": "new",
                "review_stage": "mapping",
                "decision": "approved",
                "mapping_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(mapping_response.status_code, 201, mapping_response.data)
        self.assertEqual(mapping_response.data["outcome"], "engine_decision_written")
        self.assertTrue(mapping_response.data["engine_exported"])
        self.assertEqual(mapping_response.data["review_state"]["decision"], "approved")
        self.assertEqual(FindingDecision.objects.count(), 2)
        self.assertEqual(writer.call_count, 2)
        self.assertEqual(writer.call_args_list[0].args[1], [])
        final_batch = writer.call_args_list[1].args[1]
        self.assertEqual(final_batch[0]["review"]["decision"], "approved")
        self.assertEqual(
            final_batch[0]["review"]["citation_reviewer_name"],
            self.citation.full_name,
        )
        self.assertEqual(
            final_batch[0]["review"]["mapping_reviewer_name"],
            self.mapping.full_name,
        )
        history = self.client.get(f"/api/workspace/decisions/findings/{key}/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data["results"]), 2)
        self.assertEqual(history.data["effective_review"]["decision"], "approved")

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_same_user_cannot_approve_citation_and_mapping(self, writer):
        self.citation.groups.add(Group.objects.get(name="mapping_reviewer"))
        self.authenticate(self.citation)
        key = "1" * 64
        first = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": key,
                "queue": "new",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": key,
                "queue": "new",
                "review_stage": "mapping",
                "decision": "approved",
                "mapping_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(FindingDecision.objects.count(), 1)

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_optimistic_concurrency_rejects_stale_write(self, writer):
        self.authenticate(self.citation)
        payload = {
            "finding_key": "1" * 64,
            "queue": "new",
            "review_stage": "citation",
            "decision": "approved",
            "citation_checked": True,
            "expected_latest_decision_id": None,
        }
        self.assertEqual(
            self.client.post(
                "/api/workspace/decisions/findings/", payload, format="json"
            ).status_code,
            201,
        )
        response = self.client.post(
            "/api/workspace/decisions/findings/", payload, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(FindingDecision.objects.count(), 1)

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_recall_zone3_and_correction_use_separate_domains(self, writer):
        self.authenticate(self.mapping)
        recall_item = ReviewItem.objects.get(queue=ReviewItem.Queue.RECALL)
        response = self.client.post(
            "/api/workspace/decisions/recall/",
            {
                "recall_key": recall_item.stable_key,
                "verdict": "REAL_MISS",
                "reasoning": "Verified against the official instrument.",
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        zone_item = ReviewItem.objects.get(queue=ReviewItem.Queue.ZONE3)
        response = self.client.post(
            "/api/workspace/decisions/zone3/",
            {
                "score_key": zone_item.stable_key,
                "verdict": "overridden",
                "score": "0.5",
                "reasoning": "Legal scope supports the intermediate score.",
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(RecallDecision.objects.count(), 1)
        self.assertEqual(Zone3Decision.objects.count(), 1)

        response = self.client.post(
            "/api/workspace/corrections/",
            {
                "finding_key": "1" * 64,
                "queue": "new",
                "explanation": "The quoted span needs correction.",
                "expected_latest_correction_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(CorrectionRequest.objects.count(), 1)
        self.assertEqual(writer.call_count, 3)
        self.assertEqual(writer.call_args_list[0].args[0], "recall")
        self.assertEqual(
            writer.call_args_list[0].args[1][0]["recall_key"],
            recall_item.stable_key,
        )
        self.assertEqual(writer.call_args_list[1].args[0], "zone3")
        self.assertEqual(writer.call_args_list[1].args[1][0]["action"], "override")
        self.assertEqual(writer.call_args_list[2].args[0], "findings")
        self.assertEqual(
            writer.call_args_list[2].args[1][0]["review"]["decision"],
            "rejected",
        )
        review_state = self.client.get("/api/workspace/review/new/").data["results"][0][
            "review_state"
        ]
        self.assertTrue(review_state["correction_pending"])

    @patch(
        "workspace.views.apply_authoritative_decision",
        side_effect=RuntimeError("should not be called"),
    )
    def test_blocked_finding_cannot_be_approved(self, writer):
        self.authenticate(self.citation)
        item = ReviewItem.objects.get(queue=ReviewItem.Queue.NEW)
        item.blocked = True
        item.block_reason = "Citation alignment is unresolved."
        item.save(update_fields=["blocked", "block_reason"])
        response = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": "1" * 64,
                "queue": "new",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        writer.assert_not_called()

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_rejection_requires_reason_and_stale_snapshot_blocks_writes(self, writer):
        self.authenticate(self.citation)
        payload = {
            "finding_key": "1" * 64,
            "queue": "new",
            "review_stage": "citation",
            "decision": "rejected",
            "expected_latest_decision_id": None,
        }
        response = self.client.post(
            "/api/workspace/decisions/findings/", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.data)
        self.snapshot.stale = True
        self.snapshot.save(update_fields=["stale"])
        payload.update(decision="approved", citation_checked=True, note="")
        response = self.client.post(
            "/api/workspace/decisions/findings/", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        writer.assert_not_called()

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_individual_approval_fails_closed_on_missing_proof(self, writer):
        evidence = EvidenceRow.objects.get(finding_key="1" * 64)
        evidence.row_json = {**evidence.row_json, "citation_proof": None}
        evidence.save(update_fields=["row_json"])
        self.authenticate(self.citation)
        response = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": "1" * 64,
                "queue": "new",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        writer.assert_not_called()

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_bulk_known_approval_fails_closed_on_incomplete_proof(self, writer):
        evidence = EvidenceRow.objects.get(finding_key="2" * 64)
        evidence.row_json = {**evidence.row_json, "citation_proof": None}
        evidence.save(update_fields=["row_json"])
        self.authenticate(self.citation)
        response = self.client.post(
            "/api/workspace/decisions/findings/bulk/",
            {
                "finding_keys": ["2" * 64],
                "review_stage": "citation",
                "citation_checked": True,
                "expected_latest_decision_ids": {"2" * 64: None},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ineligible", response.data)
        writer.assert_not_called()

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_bulk_known_approval_writes_one_authoritative_batch(self, writer):
        evidence = EvidenceRow.objects.get(finding_key="2" * 64)
        evidence.row_json = {
            **evidence.row_json,
            "Status": "in_force",
            "status_evidence": "Official current compilation",
            "citation_proof": {"alignment_status": "exact"},
        }
        evidence.save(update_fields=["row_json"])
        FindingDecision.objects.create(
            finding_key="2" * 64,
            review_subject_hash=evidence.review_subject_hash,
            queue="known",
            review_stage="citation",
            decision="approved",
            citation_checked=True,
            status_checked=True,
            reviewer_name=self.citation.full_name,
            reviewer_role="citation",
            reviewed_at=timezone.now(),
            created_by=self.citation,
            authoritative_file_hash=HASH,
        )
        self.authenticate(self.mapping)
        response = self.client.post(
            "/api/workspace/decisions/findings/bulk/",
            {
                "finding_keys": ["2" * 64],
                "review_stage": "mapping",
                "mapping_checked": True,
                "expected_latest_decision_ids": {"2" * 64: None},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["outcome"], "engine_decision_written")
        self.assertTrue(response.data["engine_exported"])
        self.assertEqual(response.data["review_states"]["2" * 64]["decision"], "approved")
        self.assertEqual(FindingDecision.objects.count(), 2)
        engine_batch = writer.call_args.args[1]
        self.assertEqual(len(engine_batch), 1)
        self.assertEqual(engine_batch[0]["review"]["decision"], "approved")
        writer.assert_called_once()

    def test_missing_engine_writer_returns_503_without_audit_row(self):
        self.authenticate(self.citation)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            ENGINE_ROOT=temp_dir,
            WORKSPACE_DECISION_WRITER=f"{temp_dir}/missing.py",
        ):
            response = self.client.post(
                "/api/workspace/decisions/findings/",
                {
                    "finding_key": "1" * 64,
                    "queue": "new",
                    "review_stage": "citation",
                    "decision": "approved",
                    "citation_checked": True,
                    "expected_latest_decision_id": None,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(FindingDecision.objects.count(), 0)

    @patch(
        "workspace.views.apply_authoritative_decision",
        side_effect=DecisionWriterConflict("c" * 64),
    )
    def test_external_file_change_returns_409_without_audit_row(self, writer):
        self.authenticate(self.citation)
        response = self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": "1" * 64,
                "queue": "new",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["current_file_hash"], "c" * 64)
        self.assertEqual(FindingDecision.objects.count(), 0)

    def test_wrong_role_is_forbidden(self):
        self.authenticate(self.citation)
        item = ReviewItem.objects.get(queue=ReviewItem.Queue.RECALL)
        response = self.client.post(
            "/api/workspace/decisions/recall/",
            {
                "recall_key": item.stable_key,
                "verdict": "REAL_MISS",
                "expected_latest_decision_id": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class AppendOnlyModelTests(TestCase):
    def test_recall_decision_cannot_be_updated(self):
        user = User.objects.create_user(
            username="audit", email="audit@example.com", password="SafePass123!"
        )
        row = RecallDecision.objects.create(
            recall_key=HASH,
            verdict="REAL_MISS",
            reviewer_name="Audit User",
            reviewer_role="mapping",
            reviewed_at=timezone.now(),
            created_by=user,
            authoritative_file_hash=HASH,
        )
        row.reasoning = "mutated"
        with self.assertRaises(DjangoValidationError):
            row.save()
        with self.assertRaises(DjangoValidationError):
            row.delete()
        with self.assertRaises(DjangoValidationError):
            RecallDecision.objects.filter(pk=row.pk).delete()


class EngineWriterContractTests(TestCase):
    def test_app_lock_uses_configured_persistent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            WORKSPACE_LOCK_DIR=Path(temp_dir) / "locks"
        ):
            with decision_domain_lock("findings"):
                lock_files = list((Path(temp_dir) / "locks").glob("*.lock"))
                self.assertEqual(len(lock_files), 1)

    def test_real_w2_recall_writer_round_trip_and_sha_conflict(self):
        writer = settings.WORKSPACE_DECISION_WRITER
        engine_python = settings.ENGINE_PYTHON
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            ENGINE_ROOT=temp_dir,
            ENGINE_PYTHON=engine_python,
            WORKSPACE_DECISION_WRITER=writer,
        ):
            decision = {
                "recall_key": "f" * 64,
                "verdict": "REAL_MISS",
                "reasoning": "Verified fixture",
                "reviewer_name": "Mapping Reviewer",
                "reviewed_at": "2026-07-18T12:00:00Z",
            }
            receipt = apply_authoritative_decision("recall", [decision])
            self.assertEqual(len(receipt["sha256"]), 64)
            written = json.loads(
                (
                    Path(temp_dir) / "data" / "review" / "recall_decisions.json"
                ).read_text()
            )
            self.assertEqual(written, [decision])
            with self.assertRaises(DecisionWriterConflict):
                apply_authoritative_decision(
                    "recall", [decision], expected_file_hash="0" * 64
                )
