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
from .decision_state import effective_finding_review
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
    EvidenceChange,
    EvidenceChangeSet,
    EvidenceIdentity,
    EvidenceRegistryEntry,
    EvidenceRevision,
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

    def test_rerun_creates_revision_and_retains_published_registry(self):
        first, _ = import_snapshot(minimal_artifacts(), keep=1)
        self.assertEqual(EvidenceIdentity.objects.count(), 3)
        self.assertEqual(EvidenceRevision.objects.count(), 3)
        self.assertEqual(EvidenceRegistryEntry.objects.count(), 3)
        self.assertEqual(
            first.evidence_change_set.state, EvidenceChangeSet.State.PUBLISHED
        )

        artifacts = minimal_artifacts()
        artifacts["consolidated"]["rows"][0]["Verbatim Snippet"] = (
            "A refreshed, source-exact statutory quotation."
        )
        artifacts["key_map"]["rows"][0]["finding_key"] = "9" * 64
        artifacts["key_map"]["rows"][0]["review_subject_hash"] = "8" * 64
        second, created = import_snapshot(artifacts, keep=1)

        self.assertTrue(created)
        self.assertEqual(EngineSnapshot.objects.count(), 2)
        self.assertEqual(second.evidence_change_set.state, EvidenceChangeSet.State.DRAFT)
        change = second.evidence_change_set.changes.get(
            identity__indicator_id="P6-I4"
        )
        self.assertEqual(change.kind, EvidenceChange.Kind.REVISED)
        self.assertEqual(change.invalidated_stages_json, ["citation"])
        entry = EvidenceRegistryEntry.objects.get(identity=change.identity)
        self.assertEqual(entry.active_revision.snapshot_id, first.pk)

    def test_unchanged_review_components_carry_to_new_revision(self):
        first, _ = import_snapshot(minimal_artifacts())
        citation_user = User.objects.create_user(
            username="carry-citation", email="carry-citation@example.com", password="pw"
        )
        mapping_user = User.objects.create_user(
            username="carry-mapping", email="carry-mapping@example.com", password="pw"
        )
        revision = first.evidence_revisions.get(finding_key="1" * 64)
        for stage, user, checks in (
            (FindingDecision.Stage.CITATION, citation_user, (True, False, False)),
            (FindingDecision.Stage.MAPPING, mapping_user, (False, True, False)),
            (FindingDecision.Stage.STATUS, citation_user, (False, False, True)),
        ):
            FindingDecision.objects.create(
                finding_key=revision.finding_key,
                review_subject_hash=revision.review_subject_hash,
                queue=ReviewItem.Queue.NEW,
                review_stage=stage,
                decision=FindingDecision.Verdict.APPROVED,
                citation_checked=checks[0],
                mapping_checked=checks[1],
                status_checked=checks[2],
                reviewer_name=user.full_name or user.username,
                reviewer_role=stage,
                reviewed_at=timezone.now(),
                created_by=user,
                authoritative_file_hash=HASH,
                writer_receipt_json={},
            )

        artifacts = minimal_artifacts()
        artifacts["consolidated"]["rows"][0]["Verbatim Snippet"] = "A better exact quote."
        artifacts["key_map"]["rows"][0]["finding_key"] = "9" * 64
        artifacts["key_map"]["rows"][0]["review_subject_hash"] = "8" * 64
        second, _ = import_snapshot(artifacts)
        current = second.evidence_revisions.get(finding_key="9" * 64)
        state = effective_finding_review(
            current.finding_key, review_subject_hash=current.review_subject_hash
        )
        self.assertNotIn(FindingDecision.Stage.CITATION, state["stages"])
        self.assertTrue(state["stages"][FindingDecision.Stage.MAPPING]["carried_forward"])
        self.assertTrue(state["stages"][FindingDecision.Stage.STATUS]["carried_forward"])


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

        # Sandbox ENGINE_ROOT: the developer machine's real engine tree may hold
        # replayed final artifacts, which is environment state, not app behavior.
        with tempfile.TemporaryDirectory() as empty_root:
            with override_settings(ENGINE_ROOT=Path(empty_root)):
                submission = self.client.get(
                    "/api/workspace/submission/?economy=Singapore"
                )
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
        graph_artifact = self.snapshot.artifacts.get(key="neo4j-graph-snapshot")
        graph_payload = dict(graph_artifact.parsed_json)
        graph_payload["edges"] = [
            {"id": "valid", "source": "p1", "target": "p1", "type": "CROSS_REFERENCES", "properties": {}},
            {"id": "orphan", "source": "p1", "target": "missing", "type": "CROSS_REFERENCES", "properties": {}},
        ]
        SnapshotArtifact.objects.filter(pk=graph_artifact.pk).update(parsed_json=graph_payload)
        subgraph = self.client.get("/api/workspace/knowledge-graph/subgraph/?economy=Singapore")
        self.assertLessEqual(len(subgraph.data["nodes"]), 500)
        self.assertEqual([edge["id"] for edge in subgraph.data["edges"]], ["valid"])
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
                "workspace.engine_worker.run_allowlisted",
                return_value=(0, "submission replay: 1"),
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

            # A live pipeline run produces artifacts only — it must never
            # auto-import a snapshot (the reviewed app data changes solely
            # through the explicit refresh action).
            run_action = EngineAction.objects.create(
                kind=EngineAction.Kind.RUN,
                arguments_json={"action": "run_pipeline", "economy": "Singapore", "pillar": "6", "cc": "si"},
                requested_by=admin,
            )
            with override_settings(ENGINE_ROOT=root, ENGINE_ALLOWLIST=allowlist), patch(
                "workspace.engine_worker.run_allowlisted",
                return_value=(0, "wrote outputs"),
            ), patch("workspace.engine_worker.import_snapshot") as auto_import:
                execute_action(run_action)
                run_action.refresh_from_db()
                self.assertEqual(run_action.status, EngineAction.Status.SUCCEEDED)
                auto_import.assert_not_called()

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
        self.assertEqual(response.data["review_queue"], "new")
        self.assertEqual(response.data["stable_key"], exact_key)
        self.assertTrue(response.data["approval_eligibility"]["eligible"])

        response = self.client.get(
            f"/api/workspace/source-match/{exact_key}/"
            "?economy=Singapore,Malaysia&pillar=6,7&indicator=P6-I4,P7-I1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["navigation"]["total"], 2)

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
    def test_admin_can_complete_all_finding_stages_as_single_reviewer(self, writer):
        admin = self.make_user("review-admin", "Review Admin", "admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save(update_fields=("is_superuser", "is_staff"))
        self.authenticate(admin)
        key = "1" * 64
        stages = (
            ("citation", {"citation_checked": True}),
            ("status", {"status_checked": True}),
            ("mapping", {"mapping_checked": True}),
        )
        responses = []
        for stage, checks in stages:
            responses.append(self.client.post(
                "/api/workspace/decisions/findings/",
                {
                    "finding_key": key,
                    "queue": "new",
                    "review_stage": stage,
                    "decision": "approved",
                    "expected_latest_decision_id": None,
                    **checks,
                },
                format="json",
            ))
        self.assertEqual([response.status_code for response in responses], [201, 201, 201])
        self.assertFalse(responses[0].data["engine_exported"])
        self.assertFalse(responses[1].data["engine_exported"])
        self.assertTrue(responses[2].data["engine_exported"])
        self.assertEqual(responses[2].data["review_state"]["decision"], "approved")
        self.assertEqual(
            set(FindingDecision.objects.values_list("reviewer_role", flat=True)),
            {"admin"},
        )
        final_batch = writer.call_args_list[-1].args[1]
        self.assertEqual(final_batch[0]["review"]["reviewer_role"], "admin")
        self.assertEqual(final_batch[0]["review"]["citation_reviewer_name"], admin.full_name)
        self.assertEqual(final_batch[0]["review"]["mapping_reviewer_name"], admin.full_name)

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

    def test_run_events_stream_from_engine_log_to_console_endpoint(self):
        admin = self.make_user("events-admin", "Events Admin", "admin")
        self.authenticate(self.citation)
        action = EngineAction.objects.create(
            kind=EngineAction.Kind.RUN, requested_by=admin,
            arguments_json={"action": "run_pipeline", "economy": "Singapore", "pillar": "6", "cc": "si",
                            "mode": "local", "provider_profile": "local_openweights", "out_prefix": "local"},
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def fake_run(argv, timeout, should_cancel, env=None, on_poll=None):
                log = Path(env["CLAUSECHAIN_EVENT_LOG"])
                lines = [json.dumps({"seq": i, "ts": 1790000000 + i, "stage": stage, "label": "P6-I4",
                                     "message": msg, "detail": "prompt text" if stage == "llm" else ""})
                         for i, (stage, msg) in enumerate([("start", "Singapore P6"), ("llm", "-> model"),
                                                           ("done", "finished")], start=1)]
                log.write_text("\n".join(lines[:2]) + "\n" + lines[2][:10])  # last line half-written
                on_poll()
                self.assertEqual(action.events.count(), 2)
                log.write_text("\n".join(lines) + "\n")
                return 0, "ok"

            with override_settings(ENGINE_ROOT=root), patch(
                "workspace.engine_worker.run_allowlisted", side_effect=fake_run
            ):
                execute_action(action)
        page = self.client.get(f"/api/workspace/engine/actions/{action.pk}/events/").data
        self.assertEqual([e["stage"] for e in page["events"]], ["start", "llm", "done"])
        self.assertEqual(page["events"][1]["detail"], "prompt text")
        self.assertEqual(page["last_seq"], 3)
        later = self.client.get(f"/api/workspace/engine/actions/{action.pk}/events/?after=2").data
        self.assertEqual([e["seq"] for e in later["events"]], [3])
        self.assertEqual(self.client.get(f"/api/workspace/engine/actions/{action.pk}/events/?after=x").status_code, 400)

    def test_cancel_one_and_cancel_and_clear_all(self):
        from .engine_worker import EngineActionCancelled

        admin = self.make_user("cancel-admin", "Cancel Admin", "admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save(update_fields=("is_superuser", "is_staff"))
        self.authenticate(self.citation)
        queued = EngineAction.objects.create(
            kind=EngineAction.Kind.RUN, requested_by=admin,
            arguments_json={"action": "run_pipeline", "economy": "Singapore", "pillar": "6",
                            "cc": "si", "mode": "local", "provider_profile": "local_openweights",
                            "out_prefix": "local"},
        )
        self.assertEqual(
            self.client.post(f"/api/workspace/engine/actions/{queued.pk}/cancel/").status_code, 403
        )
        self.authenticate(admin)

        # Queued -> cancelled immediately, and it is no longer claimable.
        response = self.client.post(f"/api/workspace/engine/actions/{queued.pk}/cancel/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["status"], response.data["cancelled_by"]), ("cancelled", "Cancel Admin"))
        self.assertEqual(self.client.post(f"/api/workspace/engine/actions/{queued.pk}/cancel/").status_code, 409)

        # Running with a live worker -> stop request; the worker stops the process group.
        running = EngineAction.objects.create(
            kind=EngineAction.Kind.RUN, requested_by=admin, status=EngineAction.Status.RUNNING,
            started_at=timezone.now(), arguments_json=queued.arguments_json,
        )
        with patch("workspace.views.worker_status",
                   return_value={"alive": True, "current_action_id": str(running.pk)}):
            response = self.client.post(f"/api/workspace/engine/actions/{running.pk}/cancel/")
        self.assertEqual(response.data["status"], "running")
        self.assertTrue(response.data["cancel_requested_at"])
        with patch("workspace.engine_worker.run_allowlisted",
                   side_effect=EngineActionCancelled("partial output")):
            execute_action(running)
        running.refresh_from_db()
        self.assertEqual(running.status, EngineAction.Status.CANCELLED)
        self.assertIn("Cancel Admin", running.error)

        # Cancel & clear all (local tab): cancels active local work, hides finished
        # local rows, leaves hybrid actions alone, keeps every row.
        orphan = EngineAction.objects.create(
            kind=EngineAction.Kind.RUN, requested_by=admin, status=EngineAction.Status.RUNNING,
            started_at=timezone.now(), arguments_json=queued.arguments_json,
        )
        hybrid = EngineAction.objects.create(
            kind=EngineAction.Kind.REPLAY, requested_by=admin, arguments_json={"action": "replay"},
        )
        # A live worker busy with something else is not running the orphan: close it directly.
        with patch("workspace.views.worker_status",
                   return_value={"alive": True, "current_action_id": None}):
            response = self.client.post(
                "/api/workspace/engine/actions/cancel-all/", {"mode": "local"}, format="json"
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["cancelled"], response.data["cleared"]), (1, 3))
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, EngineAction.Status.CANCELLED)  # nobody running it: closed directly
        self.assertEqual(self.client.get("/api/workspace/runs/?mode=local").data["actions"], [])
        hybrid.refresh_from_db()
        self.assertEqual(hybrid.status, EngineAction.Status.QUEUED)
        self.assertEqual(EngineAction.objects.filter(pk__in=[queued.pk, running.pk, orphan.pk]).count(), 3)

    def test_queueing_starts_a_worker_only_when_none_is_alive(self):
        from datetime import timedelta
        from .models import EngineWorkerHeartbeat
        from .worker_supervisor import ensure_worker

        admin = self.make_user("worker-boss", "Worker Boss", "admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save(update_fields=("is_superuser", "is_staff"))
        self.authenticate(admin)
        self.assertFalse(self.client.get("/api/workspace/engine/worker/").data["alive"])

        with tempfile.TemporaryDirectory() as temporary, override_settings(
            ENGINE_WORKER_AUTOSTART=True,
            WORKSPACE_LOCK_DIR=Path(temporary),
            ENGINE_WORKER_LOG=Path(temporary) / "worker.log",
        ), patch("workspace.worker_supervisor.subprocess.Popen",
                 return_value=SimpleNamespace(pid=4242)) as popen:
            queued = self.client.post(
                "/api/workspace/engine/run/",
                {"economy": "Singapore", "pillar": 6, "mode": "local"},
                format="json",
            )
            self.assertEqual(queued.status_code, 202, queued.data)
            self.assertTrue(queued.data["worker"]["started"])
            self.assertEqual(popen.call_count, 1)
            self.assertIn("run_engine_worker", popen.call_args.args[0])
            # A second request while the first worker is still booting does not pile on.
            self.assertFalse(ensure_worker()["started"])
            self.assertEqual(popen.call_count, 1)

            # A fresh heartbeat means a worker is alive: nothing is started.
            (Path(temporary) / "engine_worker.spawned").unlink()
            EngineWorkerHeartbeat.objects.create(
                worker_id="host:1", hostname="host", pid=1,
                started_at=timezone.now(), last_seen=timezone.now(),
            )
            self.assertFalse(ensure_worker()["started"])
            self.assertEqual(popen.call_count, 1)
            self.assertTrue(self.client.get("/api/workspace/runs/").data["worker"]["alive"])

            # A stale heartbeat (crashed worker) triggers a new start.
            EngineWorkerHeartbeat.objects.update(last_seen=timezone.now() - timedelta(minutes=5))
            self.assertTrue(ensure_worker()["started"])
            self.assertEqual(popen.call_count, 2)

        with override_settings(ENGINE_WORKER_AUTOSTART=False), patch(
            "workspace.worker_supervisor.subprocess.Popen"
        ) as popen:
            status = ensure_worker()
            self.assertEqual((status["started"], status["autostart"]), (False, False))
            popen.assert_not_called()

    def test_local_mode_runs_are_separate_and_feed_local_tabs(self):
        admin = self.make_user("mode-admin", "Mode Admin", "admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save(update_fields=("is_superuser", "is_staff"))
        self.authenticate(admin)

        # Local tabs start blank; hybrid keeps reading the reviewed snapshot.
        local_runs = self.client.get("/api/workspace/runs/?mode=local")
        self.assertEqual(local_runs.status_code, 200)
        self.assertEqual((local_runs.data["mode"], local_runs.data["results"]), ("local", []))
        self.assertEqual([mode["id"] for mode in local_runs.data["modes"]], ["hybrid", "local"])
        local_matrix = self.client.get("/api/workspace/zone3-matrix/?mode=local")
        self.assertEqual(local_matrix.status_code, 200)
        self.assertEqual((local_matrix.data["cells"], local_matrix.data["snapshot"]), ([], None))
        self.assertEqual(self.client.get("/api/workspace/zone3-matrix/").data["mode"], "hybrid")
        self.assertEqual(self.client.get("/api/workspace/runs/?mode=cloudy").status_code, 400)

        # The run endpoint maps the mode onto the engine profile + output folder.
        allowlist = settings.ENGINE_ALLOWLIST
        queued = self.client.post(
            "/api/workspace/engine/run/",
            {"economy": "Singapore", "pillar": 6, "mode": "local"},
            format="json",
        )
        self.assertEqual(queued.status_code, 202, queued.data)
        self.assertEqual(queued.data["mode"], "local")
        self.assertEqual(queued.data["arguments"]["provider_profile"], "local_openweights")
        self.assertEqual(queued.data["arguments"]["out_prefix"], "local")
        _, argv, _ = build_allowlisted_command(queued.data["arguments"])
        self.assertIn("local_openweights", argv)
        self.assertIn("outputs/local_si_p6", argv)
        self.assertEqual(
            self.client.post(
                "/api/workspace/engine/run/",
                {"economy": "Singapore", "pillar": 6, "mode": "cloudy"},
                format="json",
            ).status_code,
            400,
        )
        self.assertTrue(allowlist.is_file())

        # A succeeded local run captures its envelope and appears only in local views.
        action = EngineAction.objects.get(pk=queued.data["id"])
        envelope = {
            "run_id": "local-run-1", "generated_at": "2026-09-24T10:00:00Z", "country": "SG",
            "pillar": 6, "provider_profile": "local_openweights", "warnings": [],
            "metadata": {"pipeline_stats": {"mapped": 2}},
            "findings": [
                {"Economy": "Singapore", "Indicator ID": "P6-I2", "Law Name": "PDPA 2012",
                 "Article / Section": "s. 26", "Discovery Tag": "KNOWN",
                 "Verbatim Snippet": "An organisation shall not transfer any personal data",
                 "Source URL": "https://sso.agc.gov.sg/Act/PDPA2012", "raw_context": "x" * 50,
                 "model_version": "unsloth/Qwen3.8-27B-NVFP4/escalate:unsloth/Qwen3.8-27B-NVFP4+BAAI/bge-m3"},
                {"Economy": "Singapore", "Indicator ID": "P6-I1", "Law Name": "PDPA 2012",
                 "Discovery Tag": "KNOWN", "Verbatim Snippet": "NO_EVIDENCE_FOUND_PENDING_REVIEW"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "outputs" / "local_si_p6" / "output.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps(envelope), encoding="utf-8")
            with override_settings(ENGINE_ROOT=root), patch(
                "workspace.engine_worker.run_allowlisted",
                return_value=(0, "wrote outputs"),
            ), patch("workspace.engine_worker.import_snapshot") as auto_import:
                execute_action(action)
                auto_import.assert_not_called()
        action.refresh_from_db()
        self.assertEqual(action.status, EngineAction.Status.SUCCEEDED, action.error)
        self.assertIn("outputs/local_si_p6/output.json", action.result_hashes_json)
        self.assertNotIn("raw_context", action.result_json["findings"][0])

        local_runs = self.client.get("/api/workspace/runs/?mode=local").data
        self.assertEqual(len(local_runs["results"]), 1)
        self.assertEqual(local_runs["results"][0]["provider_profile"], "local_openweights")
        self.assertEqual(local_runs["results"][0]["rows_produced"], 2)
        self.assertEqual([row["id"] for row in local_runs["actions"]], [str(action.pk)])
        hybrid_runs = self.client.get("/api/workspace/runs/").data
        self.assertNotIn(str(action.pk), [row["id"] for row in hybrid_runs["actions"]])
        self.assertNotIn("local_openweights", [run["provider_profile"] for run in hybrid_runs["results"]])

        # A finished run reaches the Local matrix only through a Local snapshot refresh.
        matrix = self.client.get("/api/workspace/zone3-matrix/?mode=local").data
        self.assertEqual((matrix["snapshot"], matrix["cells"]), (None, []))

    def test_run_output_folders_match_what_the_snapshot_imports(self):
        admin = self.make_user("folder-admin", "Folder Admin", "admin")
        admin.is_superuser = True
        admin.save(update_fields=("is_superuser",))
        self.authenticate(admin)
        expected = {
            # "Indonesia"[:2] is "in": it must not land in India's folders.
            ("Indonesia", "hybrid"): ("id", "final_r2", "outputs/final_r2_id_p6"),
            ("India", "hybrid"): ("in", "final_r2", "outputs/final_r2_in_p6"),
            # Round-2 hybrid reruns write the folders the snapshot import reads.
            ("Thailand", "hybrid"): ("th", "final_r2", "outputs/final_r2_th_p6"),
            ("Singapore", "hybrid"): ("si", "final", "outputs/final_si_p6"),
            ("Indonesia", "local"): ("id", "local", "outputs/local_id_p6"),
        }
        for (economy, mode), (code, prefix, folder) in expected.items():
            queued = self.client.post(
                "/api/workspace/engine/run/",
                {"economy": economy, "pillar": 6, "mode": mode},
                format="json",
            )
            self.assertEqual(queued.status_code, 202, queued.data)
            arguments = queued.data["arguments"]
            self.assertEqual((arguments["cc"], arguments["out_prefix"]), (code, prefix))
            _, argv, _ = build_allowlisted_command(arguments)
            self.assertIn(folder, argv)
            EngineAction.objects.filter(pk=queued.data["id"]).update(
                status=EngineAction.Status.SUCCEEDED
            )

    @patch("workspace.views.apply_authoritative_decision")
    def test_local_snapshot_mirrors_hybrid_and_stays_separate(self, writer):
        from .mode import current_mode

        # The engine's Local layout namespaces every key; the fixture mirrors that.
        text = json.dumps(minimal_artifacts())
        for digit in "123":
            text = text.replace(digit * 64, "a" + digit * 63)
        local, created = import_snapshot(json.loads(text), mode="local")
        self.assertTrue(created)
        self.assertEqual(EngineSnapshot.objects.get(active=True, mode="hybrid").pk, self.snapshot.pk)
        self.assertEqual(local.mode, "local")
        # Its own registry: bootstrapped, and no hybrid evidence marked "not reproduced".
        self.assertEqual(local.evidence_change_set.counts_json["not_reproduced"], 0)
        self.assertEqual(EvidenceIdentity.objects.filter(mode="local").count(), 3)
        self.assertEqual(EvidenceIdentity.objects.filter(mode="hybrid").count(), 3)

        self.authenticate(self.citation)
        self.assertEqual(self.client.get("/api/workspace/summary/?mode=local").data["snapshot"]["id"], str(local.pk))
        self.assertEqual(self.client.get("/api/workspace/summary/").data["snapshot"]["id"], str(self.snapshot.pk))
        local_new = self.client.get("/api/workspace/review/new/?mode=local").data["results"]
        self.assertEqual([item["finding_key"] for item in local_new], ["a" + "1" * 63])

        # A Local decision goes through the writer in Local mode and is recorded as Local.
        seen = []
        writer.side_effect = lambda *args, **kwargs: seen.append(current_mode()) or RECEIPT
        response = self.client.post(
            "/api/workspace/decisions/findings/?mode=local",
            {"finding_key": "a" + "1" * 63, "queue": "new", "review_stage": "citation",
             "decision": "approved", "citation_checked": True, "status_checked": True,
             "expected_latest_decision_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(seen, ["local"])
        self.assertEqual(FindingDecision.objects.get().mode, "local")
        self.assertEqual(self.client.get("/api/workspace/ledger/?mode=local").data["count"], 1)
        self.assertEqual(self.client.get("/api/workspace/ledger/").data["count"], 0)
        # A Local key does not exist in the Hybrid workspace.
        self.assertEqual(self.client.post(
            "/api/workspace/decisions/findings/",
            {"finding_key": "a" + "1" * 63, "queue": "new", "review_stage": "citation",
             "decision": "approved", "citation_checked": True, "status_checked": True,
             "expected_latest_decision_id": None},
            format="json",
        ).status_code, 404)

        # Each matrix is its own snapshot's; the comparison sets their scores side by side.
        hybrid_cell = self.client.get("/api/workspace/zone3-matrix/").data["cells"][0]
        local_cell = self.client.get("/api/workspace/zone3-matrix/?mode=local").data["cells"][0]
        self.assertNotEqual(hybrid_cell["score_key"], local_cell["score_key"])
        comparison = self.client.get("/api/workspace/comparison/?economy=Singapore&pillar=7").data
        scores = {entry["indicator"]: entry for entry in comparison["selected"]["scores"]}
        self.assertIn("model_a", scores["P7-I3"])
        self.assertIn("model_b", scores["P7-I3"])
        export = self.client.get("/api/workspace/comparison/export/?economy=Singapore&pillar=7")
        self.assertIn("3 · Indicator scores (Zone-3)", export.content.decode("utf-8-sig"))

    def test_several_runs_can_wait_in_the_queue_but_not_duplicates(self):
        admin = self.make_user("queue-admin", "Queue Admin", "admin")
        admin.is_superuser = True
        admin.save(update_fields=("is_superuser",))
        self.authenticate(admin)

        def queue(economy, pillar, mode):
            return self.client.post("/api/workspace/engine/run/",
                                    {"economy": economy, "pillar": pillar, "mode": mode}, format="json")

        with patch("workspace.views.ensure_worker", return_value={"alive": True}):
            self.assertEqual(queue("Russian Federation", 6, "local").status_code, 202)
            self.assertEqual(queue("Mongolia", 7, "local").status_code, 202)
            self.assertEqual(queue("Russian Federation", 6, "hybrid").status_code, 202)
            # The same run twice would write the same output folder.
            self.assertEqual(queue("Russian Federation", 6, "local").status_code, 409)
        self.assertEqual(EngineAction.objects.filter(status=EngineAction.Status.QUEUED).count(), 3)

    def test_sources_are_built_and_cleared_from_the_app_with_a_download_record(self):
        from .models import EngineActionEvent

        admin = self.make_user("sources-admin", "Sources Admin", "admin")
        admin.is_superuser = True
        admin.save(update_fields=("is_superuser",))
        self.authenticate(admin)
        with patch("workspace.views.ensure_worker", return_value={"alive": True}):
            clear = self.client.post("/api/workspace/engine/sources/",
                                     {"economy": "Lao PDR", "operation": "clear"}, format="json")
            build = self.client.post("/api/workspace/engine/sources/",
                                     {"economy": "Lao PDR", "operation": "build", "pillar": 6}, format="json")
            again = self.client.post("/api/workspace/engine/sources/",
                                     {"economy": "Lao PDR", "operation": "build", "pillar": 7}, format="json")
            bad = self.client.post("/api/workspace/engine/sources/",
                                   {"economy": "Atlantis", "operation": "build", "pillar": 6}, format="json")
        self.assertEqual((clear.status_code, build.status_code, again.status_code, bad.status_code),
                         (202, 202, 409, 400))
        _, argv, _ = build_allowlisted_command(build.data["arguments"])
        self.assertIn("--pillars", argv)
        self.assertEqual(argv[argv.index("--pillars") + 1], "P6")
        _, clear_argv, _ = build_allowlisted_command(clear.data["arguments"])
        self.assertIn("scripts/archive_sources.py", clear_argv)
        # Source work serves both models, so both tabs list it.
        local_actions = self.client.get("/api/workspace/runs/?mode=local").data["actions"]
        self.assertEqual({row["kind"] for row in local_actions}, {"corpus"})
        hybrid_actions = self.client.get("/api/workspace/runs/").data["actions"]
        self.assertEqual({row["kind"] for row in hybrid_actions}, {"corpus"})

        action = EngineAction.objects.get(pk=build.data["id"])
        EngineActionEvent.objects.create(
            action=action, seq=1, ts=timezone.now(), stage="fetch", label="", level="info",
            message="downloaded · Law on Electronic Transactions · 820 KB PDF",
            detail=json.dumps({"kind": "download", "url": "https://bol.gov.la/et.pdf",
                               "final_url": "https://bol.gov.la/et.pdf", "act": "Law on Electronic Transactions",
                               "bytes": 839680, "file_type": "PDF", "sha256": "ab" * 32,
                               "fetched_at": "2026-10-15T03:12:00+00:00"}))
        EngineActionEvent.objects.create(
            action=action, seq=2, ts=timezone.now(), stage="fetch", label="", level="info",
            message="already archived · Old law", detail=json.dumps({"kind": "cached", "url": "https://x"}))
        documents = self.client.get(f"/api/workspace/engine/actions/{action.pk}/documents/").data
        self.assertEqual(documents["count"], 1)
        self.assertEqual((documents["documents"][0]["size_kb"], documents["documents"][0]["file_type"]), (820.0, "PDF"))
        csv_text = self.client.get(
            f"/api/workspace/engine/actions/{action.pk}/documents/?export=csv").content.decode("utf-8-sig")
        self.assertIn("Source URL,Fetched during,Time (hh:mm),Size (KB),File type", csv_text)
        self.assertIn("https://bol.gov.la/et.pdf,Sources · Lao PDR", csv_text)

    def test_local_spend_is_never_attached_to_a_hybrid_run(self):
        from .importer import _cost_for_run

        costs = [
            {"run_id": "hybrid", "economy": "Singapore", "pillar": 6, "total_usd": 1.25},
            {"run_id": "local", "economy": "Singapore", "pillar": 6, "total_usd": 0.0,
             "provider_profile": "local_openweights"},
        ]
        self.assertEqual(_cost_for_run(costs, {"country": "SG", "pillar": 6})["run_id"], "hybrid")

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_zone3_matrix_overlays_decisions_and_traces_evidence(self, writer):
        self.authenticate(self.citation)
        response = self.client.get("/api/workspace/zone3-matrix/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["counts"], {"total": 1, "decided": 0, "pending": 1})
        cell = response.data["cells"][0]
        self.assertEqual((cell["economy"], cell["indicator"]), ("Singapore", "P7-I3"))
        self.assertEqual(cell["state"], "pending")
        self.assertIsNone(cell["latest_decision_id"])
        self.assertIn("evidence", cell)

        self.authenticate(self.mapping)
        zone_item = ReviewItem.objects.get(queue=ReviewItem.Queue.ZONE3)
        decision = self.client.post(
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
        self.assertEqual(decision.status_code, 201, decision.data)
        response = self.client.get("/api/workspace/zone3-matrix/")
        cell = response.data["cells"][0]
        self.assertEqual(cell["state"], "overridden")
        self.assertEqual(float(cell["effective"]), 0.5)
        self.assertEqual(cell["reviewer_name"], self.mapping.full_name)
        self.assertEqual(cell["reasoning"], "Legal scope supports the intermediate score.")
        self.assertTrue(cell["latest_decision_id"])
        self.assertEqual(response.data["counts"]["decided"], 1)

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

    def absence_approval(self):
        return self.client.post(
            "/api/workspace/decisions/findings/",
            {
                "finding_key": "3" * 64,
                "queue": "absence",
                "review_stage": "citation",
                "decision": "approved",
                "citation_checked": True,
                "expected_latest_decision_id": None,
            },
            format="json",
        )

    @patch("workspace.views.apply_authoritative_decision", return_value=RECEIPT)
    def test_absence_conclusion_is_approvable_despite_placeholder_flag(self, writer):
        # Older engine key maps flag every absence placeholder as blocked. The
        # search-coverage manifest, not that flag, decides whether it can be approved.
        self.assertTrue(EvidenceRow.objects.get(finding_key="3" * 64).blocked)
        self.authenticate(self.citation)
        response = self.absence_approval()
        self.assertEqual(response.status_code, 201, response.data)

    @patch(
        "workspace.views.apply_authoritative_decision",
        side_effect=RuntimeError("should not be called"),
    )
    def test_absence_with_unresolved_search_failures_cannot_be_approved(self, writer):
        evidence = EvidenceRow.objects.get(finding_key="3" * 64)
        manifest = dict(evidence.row_json["search_coverage_manifest"])
        manifest["unresolved_failures"] = ["Official register timed out"]
        evidence.row_json = {**evidence.row_json, "search_coverage_manifest": manifest}
        evidence.save(update_fields=["row_json"])
        self.authenticate(self.citation)
        response = self.absence_approval()
        self.assertEqual(response.status_code, 400)
        self.assertIn("unresolved acquisition failures", str(response.data))
        writer.assert_not_called()

    @patch(
        "workspace.views.apply_authoritative_decision",
        side_effect=RuntimeError("should not be called"),
    )
    def test_blocked_provision_evidence_still_cannot_be_approved(self, writer):
        EvidenceRow.objects.filter(finding_key="1" * 64).update(blocked=True)
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
        self.assertIn("technically blocked", str(response.data))
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
    def test_warn_gates_stay_approvable_but_fail_gates_block(self, writer):
        # Engine contract: FAIL = the row can never ship; WARN = a signal the
        # named reviewer weighs individually. WARN must not disable approval.
        evidence = EvidenceRow.objects.get(finding_key="1" * 64)
        proof = dict(evidence.row_json["citation_proof"])
        payload = {
            "finding_key": "1" * 64,
            "queue": "new",
            "review_stage": "citation",
            "decision": "approved",
            "citation_checked": True,
            "expected_latest_decision_id": None,
        }
        self.authenticate(self.citation)

        proof["gate_results"] = [
            {"gate_id": "G1", "status": "PASS"},
            {"gate_id": "G4", "status": "WARN",
             "reason": "no current-version assertion found on the source page"},
        ]
        evidence.row_json = {**evidence.row_json, "citation_proof": proof}
        evidence.save(update_fields=["row_json"])
        response = self.client.post(
            "/api/workspace/decisions/findings/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

        proof["gate_results"] = [{"gate_id": "G9", "status": "FAIL"}]
        evidence.row_json = {**evidence.row_json, "citation_proof": proof}
        evidence.save(update_fields=["row_json"])
        payload["expected_latest_decision_id"] = str(FindingDecision.objects.get().pk)
        response = self.client.post(
            "/api/workspace/decisions/findings/", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("G9", str(response.data))

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


class ImportDecisionsCommandTests(TestCase):
    def test_signed_ledger_becomes_decision_rows_once(self):
        from io import StringIO

        from django.core.management import call_command

        import_snapshot(minimal_artifacts())
        signed = {
            "reviewer_name": "Citation Reviewer",
            "reviewer_role": "Team Lead",
            "reviewed_at": "2026-07-20T16:46:48+00:00",
            "citation_checked": True,
            "mapping_checked": True,
            "status_checked": True,
            "citation_reviewer_name": "Citation Reviewer",
            "mapping_reviewer_name": "Mapping Reviewer",
            "status_reviewer_name": "Citation Reviewer",
            "decision": "approved",
            "correction_note": "Supported.",
        }
        findings = [
            {"finding_key": "1" * 64, "review_subject_hash": "4" * 64, "review": signed},
            {"finding_key": "2" * 64, "review_subject_hash": "5" * 64,
             "review": {**signed, "decision": "rejected"}},
            {"finding_key": "9" * 64, "review_subject_hash": "9" * 64, "review": signed},
            {"finding_key": "2" * 64, "review_subject_hash": "5" * 64,
             "review": {**signed, "reviewer_name": "", "decision": "rejected"}},
        ]
        zone3 = [{"economy": "Singapore", "indicator": "P7-I3", "action": "override",
                  "score": 0.5, "reasoning": "Narrow measure.", "reviewer_name": "Citation Reviewer",
                  "reviewed_at": "2026-07-20T16:46:48+00:00"}]
        recall = [{"recall_key": recall_key("Singapore", "P7-I3", "Employment Act", "s. 95"),
                   "verdict": "REAL_MISS", "note": "Engine gap.", "reviewer_name": "Citation Reviewer",
                   "reviewed_at": "2026-07-19T12:50:04+00:00"}]
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(ENGINE_ROOT=temp_dir):
            folder = Path(temp_dir) / "data" / "review"
            folder.mkdir(parents=True)
            (folder / "decisions.json").write_text(json.dumps(findings))
            (folder / "zone3_decisions.json").write_text(json.dumps(zone3))
            (folder / "recall_decisions.json").write_text(json.dumps(recall))
            out = StringIO()
            call_command("import_decisions", "--mode", "hybrid", stdout=out)
            summary = json.loads(out.getvalue())["hybrid"]
            call_command("import_decisions", "--mode", "hybrid", stdout=StringIO())

        self.assertEqual(summary["findings"], {"created": 2, "kept": 0, "unsigned": 1, "not_in_snapshot": 1})
        self.assertEqual(FindingDecision.objects.count(), 4)
        approved = effective_finding_review("1" * 64, review_subject_hash="4" * 64)
        self.assertEqual(approved["decision"], "approved")
        self.assertEqual(approved["mapping_reviewer_name"], "Mapping Reviewer")
        self.assertEqual(
            effective_finding_review("2" * 64, review_subject_hash="5" * 64)["decision"], "rejected"
        )
        score = Zone3Decision.objects.get()
        self.assertEqual((score.verdict, str(score.score)), ("overridden", "0.5"))
        self.assertEqual(score.score_key, zone3_key("Singapore", "P7-I3"))
        self.assertEqual(RecallDecision.objects.get().verdict, "REAL_MISS")
        self.assertFalse(User.objects.get(username="ledger-import").has_usable_password())
