"""Model A (hybrid) vs Model B (local): the only place the two workspaces meet.

Each side is that backend's reviewed snapshot run for an economy x pillar, or a
newer finished app run of the same backend. Provisions are paired the way the
final template's "Engine Comparison" sheet reads them (found by, indicator /
citation / quote differences), and indicator scores are compared from each
backend's own Zone-3 matrix (deterministic proposal and reviewer-effective score).
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from django.utils.dateparse import parse_datetime

from .keys import normalized_part
from .models import EngineAction, EngineSnapshot, RunRecord
from .registry import identity_payload

ABSENCE_MARK = "NO_EVIDENCE_FOUND"
ECONOMY_BY_COUNTRY = {
    "SG": "Singapore", "MY": "Malaysia", "MA": "Malaysia", "AU": "Australia",
    "TH": "Thailand", "IN": "India", "ID": "Indonesia",
    "RU": "Russian Federation", "MN": "Mongolia", "LA": "Lao PDR", "TL": "Timor-Leste",
}
MODE_LABELS = {
    "hybrid": "Model A — commercial (hybrid)",
    "local": "Model B — open weights (local)",
}


def is_absence(finding):
    return ABSENCE_MARK in str(finding.get("Verbatim Snippet") or "")


def finding_key(finding, mode):
    """The key the finding has in its own workspace (engine finalization.finding_key;
    Local keys carry the engine's "local" namespace)."""
    payload = "\x1f".join(
        str(finding.get(field) or "")
        for field in ("Economy", "Indicator ID", "Law Name", "Article / Section",
                      "source_artifact_id", "Verbatim Snippet")
    )
    if mode == "local":
        payload = f"local\x1f{payload}"
    return hashlib.sha256(payload.encode()).hexdigest()


def envelope_economy(envelope):
    country = str(envelope.get("country") or "").upper()
    return ECONOMY_BY_COUNTRY.get(country, country)


def finished_runs(mode):
    """Succeeded app runs of a backend that stored an envelope, newest first."""
    queryset = EngineAction.objects.filter(kind=EngineAction.Kind.RUN, status=EngineAction.Status.SUCCEEDED)
    queryset = (queryset.filter(arguments_json__mode="local") if mode == "local"
                else queryset.exclude(arguments_json__mode="local"))
    return [action for action in queryset.order_by("-finished_at")
            if (action.result_json or {}).get("findings") is not None]


def backend_runs(mode):
    """Newest envelope per (economy, pillar) for one backend."""
    runs = {}
    for record in RunRecord.objects.filter(snapshot__active=True, snapshot__mode=mode):
        envelope = record.envelope_json or {}
        scope = (envelope_economy(envelope), str(envelope.get("pillar") or ""))
        runs[scope] = {
            "source": "reviewed snapshot" if mode == "hybrid" else "Local snapshot",
            "name": record.run_name,
            "envelope": envelope,
            "total_usd": (record.cost_json or {}).get("total_usd"),
            "started_at": None,
            "finished_at": None,
            "in_snapshot": True,
        }
    for action in finished_runs(mode):
        arguments = action.arguments_json or {}
        envelope = action.result_json or {}
        scope = (str(arguments.get("economy") or envelope_economy(envelope)),
                 str(arguments.get("pillar") or envelope.get("pillar") or ""))
        current = runs.get(scope)
        if current and str(current["envelope"].get("generated_at") or "") >= str(envelope.get("generated_at") or ""):
            continue
        runs[scope] = {
            "source": "app run, not yet in the snapshot",
            "name": f"{arguments.get('out_prefix', 'local' if mode == 'local' else 'final')}_"
                    f"{arguments.get('cc')}_p{scope[1]}",
            "envelope": envelope,
            "total_usd": ((envelope.get("metadata") or {}).get("cost_report") or {}).get("total_usd"),
            "started_at": action.started_at.isoformat() if action.started_at else None,
            "finished_at": action.finished_at.isoformat() if action.finished_at else None,
            "in_snapshot": False,
        }
    return runs


def _engine_card(mode, run):
    if not run:
        return None
    envelope = run["envelope"]
    metadata = envelope.get("metadata") or {}
    cost = metadata.get("cost_report") or {}
    findings = envelope.get("findings") or []
    absences = sum(1 for finding in findings if is_absence(finding))
    models = list((cost.get("models") or {}).keys()) or sorted(
        {str(f.get("model_version")) for f in findings if f.get("model_version")})
    elapsed = metadata.get("elapsed_seconds") or cost.get("elapsed_seconds")
    finished = run.get("finished_at") or envelope.get("generated_at") or cost.get("at")
    started = run.get("started_at")
    if not started and finished and elapsed:
        # Snapshot envelopes are stamped when the run ended; its start is that minus elapsed.
        ended = parse_datetime(str(finished))
        started = (ended - timedelta(seconds=float(elapsed))).isoformat() if ended else None
    total = run.get("total_usd")
    return {
        "label": MODE_LABELS[mode],
        "mode": mode,
        "source": run["source"],
        "in_snapshot": run["in_snapshot"],
        "name": run["name"],
        "run_id": envelope.get("run_id") or cost.get("run_id"),
        "models": models,
        "started_at": started,
        "finished_at": finished,
        "elapsed_seconds": elapsed,
        "total_usd": total if total is not None else cost.get("total_usd"),
        # The run path reads the archived corpus only (no HTTP in packages/core,
        # rdtii, retrieval or extractors); the fingerprint proves which archive.
        "documents_fetched": 0,
        "corpus_fingerprint": metadata.get("corpus_fingerprint"),
        "rows": len(findings),
        "evidence": len(findings) - absences,
        "absences": absences,
        "calls": sum(int(model.get("calls") or 0) for model in (cost.get("models") or {}).values()),
    }


def comparison_scopes():
    hybrid, local = backend_runs("hybrid"), backend_runs("local")
    return [
        {"economy": scope[0], "pillar": scope[1], "model_a": scope in hybrid, "model_b": scope in local}
        for scope in sorted(set(hybrid) | set(local))
    ]


def _instrument(finding):
    return identity_payload(finding)["instrument_key"]


def _citation(finding):
    return identity_payload(finding)["citation_key"]


def _base_citation(finding):
    return re.sub(r"\(.*$", "", _citation(finding)) or _citation(finding)


def _quote(finding):
    return normalized_part(finding.get("Verbatim Snippet"))


def _pair(a_rows, b_rows):
    a_left, b_left, pairs = list(a_rows), list(b_rows), []
    rules = (
        lambda a, b: (_instrument(a), _citation(a), a.get("Indicator ID"))
        == (_instrument(b), _citation(b), b.get("Indicator ID")),
        lambda a, b: (_instrument(a), _citation(a)) == (_instrument(b), _citation(b)),
        lambda a, b: (_instrument(a), _base_citation(a), a.get("Indicator ID"))
        == (_instrument(b), _base_citation(b), b.get("Indicator ID")),
        lambda a, b: (_instrument(a), _base_citation(a)) == (_instrument(b), _base_citation(b)),
    )
    for rule in rules:
        for a in list(a_left):
            match = next((b for b in b_left if rule(a, b)), None)
            if match is not None:
                pairs.append((a, match))
                a_left.remove(a)
                b_left.remove(match)
    return pairs, a_left, b_left


def _difference(a, b):
    if a is None:
        return "Only Model B found this provision."
    if b is None:
        return "Only Model A found this provision."
    notes = []
    if a.get("Indicator ID") != b.get("Indicator ID"):
        notes.append(f"Model A mapped it to {a.get('Indicator ID')}, Model B to {b.get('Indicator ID')}")
    if _citation(a) != _citation(b):
        notes.append(f"Model A cited {a.get('Article / Section')}, Model B cited {b.get('Article / Section')}")
    if _quote(a) != _quote(b):
        notes.append("they quote different words from it")
    if not notes:
        return "Same provision, indicator, citation and quote."
    sentence = "; ".join(notes) + "."
    return sentence[0].upper() + sentence[1:]


def _side(finding, mode):
    if finding is None:
        return None
    return {
        "indicator": finding.get("Indicator ID"),
        "article": finding.get("Article / Section"),
        "snippet": str(finding.get("Verbatim Snippet") or "")[:700],
        "rationale": str(finding.get("Mapping Rationale") or "")[:700],
        "confidence": finding.get("Confidence"),
        "tag": finding.get("Discovery Tag"),
        "source_url": finding.get("Source URL"),
        "finding_key": finding_key(finding, mode),
    }


def _provision_row(a, b, *, in_snapshot):
    base = a or b
    return {
        "law": base.get("Law Name"),
        "article": base.get("Article / Section"),
        "indicator": base.get("Indicator ID"),
        "found_by": "Both" if a and b else ("Model A only" if a else "Model B only"),
        "indicator_differs": bool(a and b and a.get("Indicator ID") != b.get("Indicator ID")),
        "citation_differs": bool(a and b and _citation(a) != _citation(b)),
        "quote_differs": bool(a and b and _quote(a) != _quote(b)),
        "how": _difference(a, b),
        "model_a": _side(a, "hybrid"),
        "model_b": _side(b, "local"),
        "in_snapshot": in_snapshot,
    }


def score_comparison(economy, pillar):
    """Each backend's Zone-3 cell for every indicator of the pillar."""
    from .views import zone3_matrix_payload

    rows = {}
    for mode in ("hybrid", "local"):
        snapshot = EngineSnapshot.objects.filter(active=True, mode=mode).first()
        if snapshot is None:
            continue
        for cell in zone3_matrix_payload(snapshot)["cells"]:
            indicator = str(cell["indicator"])
            if cell["economy"] != economy or not indicator.upper().startswith(f"P{pillar}"):
                continue
            entry = rows.setdefault(indicator, {"indicator": indicator, "question": cell.get("question")})
            entry["model_a" if mode == "hybrid" else "model_b"] = {
                "deterministic": cell.get("deterministic"),
                "effective": cell.get("effective"),
                "state": cell.get("state"),
                "master_gold": cell.get("master_gold"),
                "judge_scores": cell.get("judge_scores"),
                "flagged": cell.get("flagged"),
                "evidence": len(cell.get("evidence") or []),
            }
    result = []
    for indicator in sorted(rows):
        entry = rows[indicator]
        a, b = entry.get("model_a"), entry.get("model_b")
        entry["deterministic_agrees"] = (
            None if not (a and b) or a["deterministic"] is None or b["deterministic"] is None
            else float(a["deterministic"]) == float(b["deterministic"]))
        entry["effective_agrees"] = (
            None if not (a and b) or a["effective"] is None or b["effective"] is None
            else float(a["effective"]) == float(b["effective"]))
        result.append(entry)
    return result


def comparison(economy, pillar):
    scope = (economy, str(pillar))
    a_run, b_run = backend_runs("hybrid").get(scope), backend_runs("local").get(scope)
    a_all = (a_run or {}).get("envelope", {}).get("findings") or []
    b_all = (b_run or {}).get("envelope", {}).get("findings") or []
    a_rows = [f for f in a_all if not is_absence(f)]
    b_rows = [f for f in b_all if not is_absence(f)]
    pairs, a_only, b_only = _pair(a_rows, b_rows)
    in_snapshot = bool(b_run and b_run["in_snapshot"])
    rows = [_provision_row(a, b, in_snapshot=in_snapshot) for a, b in pairs]
    rows += [_provision_row(a, None, in_snapshot=in_snapshot) for a in a_only]
    rows += [_provision_row(None, b, in_snapshot=in_snapshot) for b in b_only]
    rows.sort(key=lambda row: (str(row["indicator"]), str(row["law"]), str(row["article"])))
    for number, row in enumerate(rows, 1):
        row["number"] = number

    indicators = sorted({str(f.get("Indicator ID")) for f in a_all + b_all if f.get("Indicator ID")})
    by_indicator = []
    for indicator in indicators:
        a_found = sum(1 for f in a_rows if f.get("Indicator ID") == indicator)
        b_found = sum(1 for f in b_rows if f.get("Indicator ID") == indicator)
        by_indicator.append({
            "indicator": indicator, "model_a": a_found, "model_b": b_found,
            "agreement": ("both found" if a_found and b_found else "both none" if not (a_found or b_found)
                          else "Model A only" if a_found else "Model B only"),
        })
    both = sum(1 for row in rows if row["found_by"] == "Both")
    a_meta = ((a_run or {}).get("envelope") or {}).get("metadata") or {}
    b_meta = ((b_run or {}).get("envelope") or {}).get("metadata") or {}
    return {
        "economy": economy,
        "pillar": str(pillar),
        "model_a": _engine_card("hybrid", a_run),
        "model_b": _engine_card("local", b_run),
        "same_corpus": bool(a_meta.get("corpus_fingerprint")
                            and a_meta.get("corpus_fingerprint") == b_meta.get("corpus_fingerprint")),
        "counts": {
            "provisions": len(rows),
            "both": both,
            "model_a_only": len(a_only),
            "model_b_only": len(b_only),
            "indicator_differs": sum(row["indicator_differs"] for row in rows),
            "citation_differs": sum(row["citation_differs"] for row in rows),
            "quote_differs": sum(row["quote_differs"] for row in rows),
            "agreement_pct": round(100 * both / len(rows)) if rows else None,
        },
        "rows": rows,
        "by_indicator": by_indicator,
        "scores": score_comparison(economy, pillar),
    }
