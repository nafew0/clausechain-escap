import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .importer import SnapshotImportError, import_snapshot
from .models import EngineAction, EngineActionEvent


class EngineWorkerError(RuntimeError):
    pass


class EngineActionCancelled(RuntimeError):
    pass


CANCEL_POLL_SECONDS = 2.0


def _stop_process_group(process):
    """SIGTERM the whole group (the pipeline may have children), then SIGKILL."""
    for sig, grace in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def event_log_path(action):
    return settings.ENGINE_ROOT / "logs" / "events" / f"{action.pk}.jsonl"


class EventTail:
    """Copies new JSON lines from the engine's event log into EngineActionEvent."""

    def __init__(self, action, path):
        self.action, self.path, self.offset = action, path, 0

    def pump(self):
        from datetime import datetime, timezone as dt_timezone

        try:
            with self.path.open("rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
        except OSError:
            return 0
        if not chunk:
            return 0
        complete = chunk[: chunk.rfind(b"\n") + 1]  # never ingest a half-written line
        self.offset += len(complete)
        rows = []
        for raw in complete.decode("utf-8", errors="replace").splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            rows.append(EngineActionEvent(
                action=self.action, seq=int(event.get("seq") or 0),
                ts=datetime.fromtimestamp(float(event.get("ts") or 0), tz=dt_timezone.utc),
                stage=str(event.get("stage") or "")[:32], label=str(event.get("label") or "")[:160],
                level=str(event.get("level") or "info")[:8], message=str(event.get("message") or ""),
                detail=str(event.get("detail") or ""),
            ))
        EngineActionEvent.objects.bulk_create(rows, ignore_conflicts=True)
        return len(rows)


def run_allowlisted(argv, timeout, should_cancel, env=None, on_poll=None):
    """Run the allowlisted command, polling for cancellation. Returns
    (returncode, combined output); raises EngineActionCancelled or
    subprocess.TimeoutExpired."""
    process = subprocess.Popen(
        argv,
        cwd=settings.ENGINE_ROOT,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # own process group, so cancel stops all of it
        env=env,
    )
    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = process.communicate(timeout=CANCEL_POLL_SECONDS)
            return process.returncode, "\n".join(part for part in (stdout, stderr) if part)
        except subprocess.TimeoutExpired:
            if on_poll:
                on_poll()
            cancelled = should_cancel()
            if cancelled or time.monotonic() > deadline:
                _stop_process_group(process)
                stdout, stderr = process.communicate()
                output = "\n".join(part for part in (stdout, stderr) if part)
                if cancelled:
                    raise EngineActionCancelled(output)
                raise subprocess.TimeoutExpired(argv, timeout, output=output)


ACTION_ARTIFACTS = {
    "replay": (
        "submission/consolidated_final.csv",
        "submission/consolidated_final.json",
    ),
    "refresh_payload": (
        "ui_export.zip",
        "submission/consolidated.json",
        "submission/review/decisions.template.json",
    ),
}


def load_allowlist():
    try:
        payload = json.loads(settings.ENGINE_ALLOWLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineWorkerError(f"Engine allowlist is unavailable: {exc}") from exc
    actions = payload.get("actions")
    if not isinstance(actions, dict):
        raise EngineWorkerError("Engine allowlist has no actions object.")
    return actions


def _validate_value(name, value, rule):
    normalized = str(value)
    if "enum" in rule and normalized not in {str(item) for item in rule["enum"]}:
        raise EngineWorkerError(f"Parameter {name} is outside the allowlist.")
    pattern = rule.get("pattern") or rule.get("param_constraints", {}).get("pattern")
    if pattern and not re.fullmatch(pattern, normalized):
        raise EngineWorkerError(f"Parameter {name} does not match the allowlist.")
    return normalized


def build_allowlisted_command(arguments):
    action_name = str(arguments.get("action") or "")
    spec = load_allowlist().get(action_name)
    if not isinstance(spec, dict):
        raise EngineWorkerError(f"Engine action is not allowlisted: {action_name!r}")
    values = {}
    for name, rule in (spec.get("params") or {}).items():
        if name not in arguments:
            raise EngineWorkerError(f"Required engine parameter is missing: {name}")
        values[name] = _validate_value(name, arguments[name], rule)
    constraints = spec.get("param_constraints") or {}
    optional = spec.get("optional_flags") or {}
    optional_argv = []
    for name, template in optional.items():
        if name not in arguments or arguments[name] in (None, False, ""):
            continue
        raw = arguments[name]
        if raw is True:
            value = "true"
        else:
            value = _validate_value(name, raw, constraints.get(name, {}))
        optional_argv.extend(str(token).format(**{**values, name: value}) for token in template)
    try:
        argv = [str(token).format(**values) for token in spec.get("argv") or []]
    except KeyError as exc:
        raise EngineWorkerError(f"Unresolved allowlist placeholder: {exc}") from exc
    if not argv:
        raise EngineWorkerError("Allowlisted engine command has no argv.")
    return action_name, argv + optional_argv, int(spec.get("timeout_s") or 300)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def review_mode_env(action_name, arguments):
    """Review actions work on one model backend's files; runs are never namespaced."""
    mode = (arguments or {}).get("mode")
    if action_name in {"refresh_payload", "replay"} and mode in ("hybrid", "local"):
        return {"CLAUSECHAIN_REVIEW_MODE": mode}
    return {}


def run_output_path(arguments):
    prefix = arguments.get("out_prefix") or "final"
    return f"outputs/{prefix}_{arguments['cc']}_p{arguments['pillar']}/output.json"


# Debug fields dropped from the stored copy; the full envelope stays on disk as
# the immutable artifact whose hash is recorded. Proof, status record and search
# coverage are kept: Local mode reviews straight from this copy, and the next run
# of the same economy/pillar overwrites the file on disk.
ENVELOPE_DROP_FIELDS = ("raw_context", "graph_path", "review")


def compact_envelope(envelope):
    findings = [
        {key: value for key, value in finding.items() if key not in ENVELOPE_DROP_FIELDS}
        for finding in envelope.get("findings") or []
    ]
    return {
        key: envelope.get(key)
        for key in ("run_id", "generated_at", "country", "pillar", "provider_profile",
                    "warnings", "metadata")
    } | {"findings": findings}


def artifact_hashes(action_name, arguments):
    paths = list(ACTION_ARTIFACTS.get(action_name, ()))
    if (arguments or {}).get("mode") == "local":  # the Local workspace's own files
        paths = [path.replace("submission/", "submission/local/", 1) for path in paths
                 if path.startswith("submission/")]
    if action_name == "run_pipeline":
        paths.append(run_output_path(arguments))
    result = {}
    for relative in paths:
        path = settings.ENGINE_ROOT / relative
        if path.is_file():
            result[relative] = {"sha256": _sha256(path), "size": path.stat().st_size}
    return result


def claim_next_action(worker_id=None):
    worker_id = worker_id or f"{socket.gethostname()}:{socket.getfqdn()}"
    now = timezone.now()
    with transaction.atomic():
        queryset = EngineAction.objects.filter(
            Q(status=EngineAction.Status.QUEUED)
            | Q(status=EngineAction.Status.RUNNING, lease_expires_at__lt=now)
        ).order_by("requested_at")
        if connection.features.has_select_for_update_skip_locked:
            queryset = queryset.select_for_update(skip_locked=True)
        else:
            queryset = queryset.select_for_update()
        action = queryset.first()
        if action is None:
            return None
        _, _, timeout = build_allowlisted_command(action.arguments_json)
        action.status = EngineAction.Status.RUNNING
        action.started_at = action.started_at or now
        action.lease_owner = worker_id[:255]
        action.lease_expires_at = now + timedelta(seconds=timeout + 120)
        action.error = ""
        action.save(
            update_fields=(
                "status", "started_at", "lease_owner", "lease_expires_at", "error"
            )
        )
        return action


def execute_action(action):
    action_name, argv, timeout = build_allowlisted_command(action.arguments_json)
    try:
        events_path = event_log_path(action)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        tail = EventTail(action, events_path)
        try:
            returncode, output = run_allowlisted(
                argv,
                timeout,
                lambda: EngineAction.objects.filter(
                    pk=action.pk, cancel_requested_at__isnull=False
                ).exists(),
                env={**os.environ, "CLAUSECHAIN_EVENT_LOG": str(events_path),
                     "PYTHONUNBUFFERED": "1", **review_mode_env(action_name, action.arguments_json)},
                on_poll=tail.pump,
            )
        finally:
            tail.pump()
        output = output[-100_000:]
        if returncode:
            raise EngineWorkerError(
                f"Allowlisted command exited {returncode}.\n{output}".strip()
            )
        hashes = artifact_hashes(action_name, action.arguments_json)
        if action_name == "run_pipeline":
            output = settings.ENGINE_ROOT / run_output_path(action.arguments_json)
            try:
                action.result_json = compact_envelope(
                    json.loads(output.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError):
                action.result_json = {}
        # run_pipeline deliberately does NOT auto-import: a live run produces
        # immutable artifacts only, and the reviewed app snapshot changes solely
        # through the explicit refresh action. (Auto-importing also fails closed
        # whenever fresh run outputs diverge from the consolidated candidate set,
        # which marked otherwise-successful runs as failed.)
        if action_name in {"replay", "refresh_payload"}:
            snapshot, _ = import_snapshot(mode=(action.arguments_json or {}).get("mode") or "hybrid")
            hashes["snapshot"] = {
                "id": str(snapshot.pk),
                "source_hash": snapshot.source_hash,
            }
        action.status = EngineAction.Status.SUCCEEDED
        action.stdout = output
        action.result_hashes_json = hashes
        action.error = ""
    except EngineActionCancelled as exc:
        action.refresh_from_db(fields=("cancelled_by",))
        action.status = EngineAction.Status.CANCELLED
        action.stdout = str(exc)[-100_000:]
        action.error = f"Cancelled by {action.cancelled_by or 'a user'} while running."
    except (OSError, subprocess.SubprocessError, EngineWorkerError, SnapshotImportError) as exc:
        action.status = EngineAction.Status.FAILED
        action.error = str(exc)[-20_000:]
    action.finished_at = timezone.now()
    action.lease_expires_at = None
    action.save(
        update_fields=(
            "status", "stdout", "result_hashes_json", "result_json", "error",
            "finished_at", "lease_expires_at",
        )
    )
    return action
