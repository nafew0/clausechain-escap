import fcntl
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from .keys import canonical_json


class DecisionWriterError(RuntimeError):
    pass


class DecisionWriterConflict(DecisionWriterError):
    def __init__(self, current_sha):
        self.current_sha = current_sha
        super().__init__("The authoritative decision file changed concurrently.")


@contextmanager
def decision_domain_lock(domain):
    root_hash = (
        __import__("hashlib")
        .sha256(str(settings.ENGINE_ROOT).encode("utf-8"))
        .hexdigest()[:12]
    )
    lock_dir = Path(settings.WORKSPACE_LOCK_DIR)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"clausechain-{root_hash}-{domain}.lock"
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def apply_authoritative_decision(domain, decisions, *, expected_file_hash=None):
    """Call the engine-owned W2 writer and require a verifiable receipt."""

    writer = Path(settings.WORKSPACE_DECISION_WRITER)
    if not writer.is_file():
        raise DecisionWriterError(
            f"Engine decision writer is unavailable: {writer}. "
            "Install the W2 writer before accepting reviewer decisions."
        )
    command = [
        str(settings.ENGINE_PYTHON),
        str(writer),
        "--domain",
        domain,
        "--root",
        str(settings.ENGINE_ROOT),
    ]
    if expected_file_hash:
        command.extend(["--expected-sha", expected_file_hash])
    try:
        result = subprocess.run(
            command,
            cwd=settings.ENGINE_ROOT,
            input=canonical_json({"decisions": decisions}),
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        stderr = getattr(locals().get("result", None), "stderr", "")
        raise DecisionWriterError(
            f"Authoritative decision write failed: {exc}. {stderr}".strip()
        ) from exc

    receipt = None
    for line in reversed(result.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            receipt = candidate
            break
    if receipt is None:
        raise DecisionWriterError("Engine writer returned no JSON receipt.")
    if result.returncode == 3 and receipt.get("conflict"):
        raise DecisionWriterConflict(str(receipt.get("sha256") or ""))
    if result.returncode != 0 or not receipt.get("ok"):
        raise DecisionWriterError(
            str(
                receipt.get("error")
                or result.stderr
                or "Engine writer rejected the decision batch."
            )
        )
    file_hash = str(receipt.get("sha256") or receipt.get("file_hash") or "")
    if len(file_hash) != 64 or any(
        character not in "0123456789abcdef" for character in file_hash.lower()
    ):
        raise DecisionWriterError(
            "Engine writer receipt has no valid SHA-256 file hash."
        )
    receipt["sha256"] = file_hash.lower()
    return receipt


def current_authoritative_hash(domain):
    name = {
        "findings": "decisions.json",
        "recall": "recall_decisions.json",
        "zone3": "zone3_decisions.json",
    }[domain]
    path = Path(settings.ENGINE_ROOT) / "data" / "review" / name
    if not path.is_file() and domain == "findings":
        path = (
            Path(settings.ENGINE_ROOT)
            / "submission"
            / "review"
            / "decisions.template.json"
        )
    if not path.is_file():
        return __import__("hashlib").sha256(b"").hexdigest()
    return __import__("hashlib").sha256(path.read_bytes()).hexdigest()
