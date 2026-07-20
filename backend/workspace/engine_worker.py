import hashlib
import json
import re
import socket
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .importer import SnapshotImportError, import_snapshot
from .models import EngineAction


class EngineWorkerError(RuntimeError):
    pass


ACTION_ARTIFACTS = {
    "replay": (
        "submission/consolidated_final.csv",
        "submission/consolidated_final.json",
    ),
    "refresh_payload": ("ui_export.zip",),
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


def artifact_hashes(action_name, arguments):
    paths = list(ACTION_ARTIFACTS.get(action_name, ()))
    if action_name == "run_pipeline":
        paths.append(
            f"outputs/final_{arguments['cc']}_p{arguments['pillar']}/output.json"
        )
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
        completed = subprocess.run(
            argv,
            cwd=settings.ENGINE_ROOT,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        output = output[-100_000:]
        if completed.returncode:
            raise EngineWorkerError(
                f"Allowlisted command exited {completed.returncode}.\n{output}".strip()
            )
        hashes = artifact_hashes(action_name, action.arguments_json)
        if action_name in {"replay", "refresh_payload", "run_pipeline"}:
            snapshot, _ = import_snapshot()
            hashes["snapshot"] = {
                "id": str(snapshot.pk),
                "source_hash": snapshot.source_hash,
            }
        action.status = EngineAction.Status.SUCCEEDED
        action.stdout = output
        action.result_hashes_json = hashes
        action.error = ""
    except (OSError, subprocess.SubprocessError, EngineWorkerError, SnapshotImportError) as exc:
        action.status = EngineAction.Status.FAILED
        action.error = str(exc)[-20_000:]
    action.finished_at = timezone.now()
    action.lease_expires_at = None
    action.save(
        update_fields=(
            "status", "stdout", "result_hashes_json", "error", "finished_at",
            "lease_expires_at",
        )
    )
    return action
