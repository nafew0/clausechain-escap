"""Final-round export (ESCAP OUTPUT_TEMPLATE_FINAL_ROUND), built on request.

The rows are the active snapshot's findings for the requested mode, each with its
current review state, and the scores are the RDTII matrix as it stands, so the file
matches what the matrix page shows. Provisions a reviewer approved and provisions
still awaiting review are exported; rejected findings and no-evidence placeholders
are left out. The engine's scripts/export_final_round.py fills ESCAP's workbook
(openpyxl lives in the engine environment); nothing here writes decisions.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.views import APIView

from .decision_state import bulk_finding_stages, stages_verdict
from .mode import current_mode, engine_env
from .models import EngineSnapshot, FindingDecision
from .registry import finding_type
from .views import zone3_matrix_payload

EXPORT_STEM = "OUTPUT_FINAL_ROUND"
CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
}


class ExportFailed(APIException):
    status_code = 500
    default_detail = "The export could not be built."


def review_summary(stages):
    """A finding's current review state as the export's review columns read it."""
    stage = FindingDecision.Stage
    citation, mapping, status = (
        stages.get(stage.CITATION), stages.get(stage.MAPPING), stages.get(stage.STATUS)
    )
    status = status or next((row for row in stages.values() if row.status_checked), None)
    dates = [row.reviewed_at for row in stages.values() if row.reviewed_at]
    notes = [row.note.strip() for row in (mapping, citation, status) if row and (row.note or "").strip()]
    return {
        "decision": stages_verdict(stages) or "pending",
        "citation_reviewer_name": citation.reviewer_name if citation else "",
        "mapping_reviewer_name": mapping.reviewer_name if mapping else "",
        "status_reviewer_name": status.reviewer_name if status else "",
        "reviewed_at": max(dates).isoformat() if dates else "",
        "correction_note": " ".join(dict.fromkeys(notes)),
    }


def export_payload(snapshot):
    """What the engine exporter needs: rows with review state, matrix cells, counts left out."""
    revisions = list(snapshot.evidence_revisions.order_by("finding_key"))
    stages_by_key = bulk_finding_stages(revisions)
    rows, excluded = [], {"rejected": 0, "absence": 0}
    for revision in revisions:
        if finding_type(revision.row_json) == "absence":
            excluded["absence"] += 1
            continue
        review = review_summary(
            stages_by_key.get((revision.finding_key, revision.review_subject_hash), {})
        )
        if review["decision"] == "rejected":
            excluded["rejected"] += 1
            continue
        rows.append({"finding": revision.row_json, "review": review})
    return {
        "mode": snapshot.mode,
        "source": {
            "id": str(snapshot.pk),
            "source_hash": snapshot.source_hash,
            "created_at": snapshot.generated_at.isoformat(),
        },
        "excluded": excluded,
        "rows": rows,
        "scores": zone3_matrix_payload(snapshot)["cells"],
    }


def build_export(snapshot, fmt, out_dir):
    """Run the engine exporter for one format; return the written file's path."""
    script = Path(settings.ENGINE_ROOT) / "scripts" / "export_final_round.py"
    try:
        result = subprocess.run(
            [str(settings.ENGINE_PYTHON), str(script), "--out", str(out_dir), "--type", fmt],
            cwd=settings.ENGINE_ROOT,
            input=json.dumps(export_payload(snapshot), ensure_ascii=False, default=str),
            text=True,
            capture_output=True,
            check=False,
            timeout=180,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **engine_env(snapshot.mode)},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExportFailed(f"The export could not be built: {exc}") from exc
    path = Path(out_dir) / f"{EXPORT_STEM}.{fmt}"
    if result.returncode != 0 or not path.is_file():
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or ["no output"]
        raise ExportFailed(f"The export could not be built: {tail[0]}")
    return path


class FinalRoundExportView(APIView):
    """GET ?type=xlsx|csv|json[&mode=local] — the current results in ESCAP's final-round template.

    (Not ?format=: REST framework reserves that name for choosing a renderer.)
    """

    def get(self, request):
        fmt = str(request.query_params.get("type") or "xlsx").lower()
        if fmt not in CONTENT_TYPES:
            raise ValidationError({"type": "Use xlsx, csv or json."})
        mode = current_mode()
        snapshot = EngineSnapshot.objects.filter(active=True, mode=mode).first()
        if snapshot is None:
            raise NotFound(f"No {mode} results to export yet.")
        with tempfile.TemporaryDirectory(prefix="clausechain-export-") as out_dir:
            content = build_export(snapshot, fmt, out_dir).read_bytes()
        stamp = timezone.now().strftime("%Y-%m-%d")
        response = HttpResponse(content, content_type=CONTENT_TYPES[fmt])
        response["Content-Disposition"] = (
            f'attachment; filename="ClauseChain_RDTII_FinalRound_{mode.capitalize()}_{stamp}.{fmt}"'
        )
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
