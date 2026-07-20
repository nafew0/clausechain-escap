from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from packages.core.schemas import SourceArtifact, StatusEvidence


class SourceValidationError(ValueError):
    pass


def validate_source_bytes(data: bytes, expected_mime: str | None = None) -> str:
    if len(data) < 32:
        raise SourceValidationError("source is empty or truncated")
    head = data[:512].lstrip().lower()
    if head.startswith(b"<html") or head.startswith(b"<!doctype html"):
        text = data[:4096].decode("utf-8", errors="ignore").lower()
        if any(marker in text for marker in ("access denied", "sign in", "login", "captcha", "error 404")):
            raise SourceValidationError("download is an HTML error/login page")
        detected = "text/html"
    elif data.startswith(b"%PDF-"):
        eof = data.rfind(b"%%EOF")
        if eof < 0:
            raise SourceValidationError("PDF has no terminal EOF marker")
        trailing = data[eof + len(b"%%EOF"):]
        suffix = trailing.strip(b"\x00\t\n\r\f ")
        # Some AGC-generated PDFs preallocate NUL padding and finish with the
        # byte offset of that decimal marker. Accept only a self-verifying offset,
        # never an arbitrary numeric or executable trailing payload.
        offset_marker_ok = False
        if suffix.isdigit():
            marker_index = data.rfind(suffix)
            offset_marker_ok = marker_index >= eof and int(suffix) == marker_index
        if suffix and not offset_marker_ok:
            raise SourceValidationError("PDF has non-padding data after terminal EOF marker")
        detected = "application/pdf"
    elif data.startswith(b"PK"):
        detected = "application/epub+zip"
    else:
        detected = expected_mime or "application/octet-stream"
    if expected_mime == "application/pdf" and detected != expected_mime:
        raise SourceValidationError(f"expected PDF, detected {detected}")
    return detected


def source_artifact_from_file(
    path: str | Path,
    *,
    original_url: str,
    retrieved_url: str | None = None,
    source_type: str,
    status_evidence: StatusEvidence,
    accessed_at: datetime | None = None,
    register_id: str | None = None,
    version_id: str | None = None,
    official_domains: set[str] | None = None,
    expected_mime: str | None = None,
    metadata: dict | None = None,
) -> SourceArtifact:
    local = Path(path)
    data = local.read_bytes()
    mime = validate_source_bytes(data, expected_mime)
    digest = hashlib.sha256(data).hexdigest()
    resolved = retrieved_url or original_url
    host = (urlparse(resolved).hostname or "").lower()
    domains = {d.lower() for d in (official_domains or set())}
    official = bool(host) and any(host == d or host.endswith("." + d) for d in domains)
    guessed = mimetypes.guess_type(local.name)[0]
    return SourceArtifact(
        id=f"sha256:{digest}",
        original_url=original_url,
        retrieved_url=resolved,
        source_type=source_type,
        mime_type=mime or guessed or "application/octet-stream",
        byte_length=len(data),
        sha256=digest,
        accessed_at=accessed_at or datetime.now(timezone.utc),
        official_domain=host,
        official=official,
        local_path=str(local),
        register_id=register_id,
        version_id=version_id,
        status_evidence=status_evidence,
        metadata=metadata or {},
    )


def verify_artifact(artifact: SourceArtifact) -> None:
    path = Path(artifact.local_path)
    data = path.read_bytes()
    if len(data) != artifact.byte_length:
        raise SourceValidationError("archived source byte length changed")
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise SourceValidationError("archived source hash changed")
    validate_source_bytes(data, artifact.mime_type)
