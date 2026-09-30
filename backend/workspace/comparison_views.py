"""Model A vs Model B comparison API (final template "Engine Comparison" sheet)."""

import csv
import io

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import comparison as cmp
from .views import RUN_CODES, RUN_MODES


def _scope_order(scope):
    economies = list(RUN_CODES)
    economy = scope.get("economy")
    return (economies.index(economy) if economy in economies else 99, str(scope.get("pillar")))


class ComparisonView(APIView):
    def get(self, request):
        scopes = sorted(cmp.comparison_scopes(), key=_scope_order)
        economy = request.query_params.get("economy")
        pillar = request.query_params.get("pillar")
        if not economy:
            first = next((scope for scope in scopes if scope["model_a"] and scope["model_b"]), None)
            economy, pillar = (first["economy"], first["pillar"]) if first else (None, None)
        selected = cmp.comparison(economy, pillar) if economy and pillar else None
        return Response({"scopes": scopes, "selected": selected,
                         "models": {key: value["models"] for key, value in RUN_MODES.items()}})


def _minutes(seconds):
    return "" if seconds in (None, "") else f"{float(seconds) / 60:.1f}"


def _score(value):
    return "" if value is None else value


class ComparisonExportView(APIView):
    """CSV in the final template's "Engine Comparison" sheet shape, plus scores."""

    def get(self, request):
        economy = request.query_params.get("economy") or ""
        pillar = request.query_params.get("pillar") or ""
        if not economy or not pillar:
            raise ValidationError({"scope": "Choose an economy and pillar."})
        result = cmp.comparison(economy, pillar)
        a, b = result["model_a"] or {}, result["model_b"] or {}

        def cell(card, field):
            return card.get(field) if card else ""

        rows = [
            [f"Engine comparison — {economy} · Pillar {pillar}"],
            ["1 · Per-engine summary"],
            ["Field", "Engine A — first pass (Model A: commercial, hybrid)",
             "Engine B — second pass (Model B: open weights, local)"],
            ["Provider and model name", " + ".join(cell(a, "models") or []), " + ".join(cell(b, "models") or [])],
            ["Start time", cell(a, "started_at") or "", cell(b, "started_at") or ""],
            ["End time", cell(a, "finished_at") or "", cell(b, "finished_at") or ""],
            ["Elapsed (minutes)", _minutes(cell(a, "elapsed_seconds")), _minutes(cell(b, "elapsed_seconds"))],
            ["Documents fetched during this pass", cell(a, "documents_fetched"), cell(b, "documents_fetched")],
            ["Cost of this pass (US$)", cell(a, "total_usd"), cell(b, "total_usd") or 0],
            ["Archived corpus fingerprint", cell(a, "corpus_fingerprint") or "", cell(b, "corpus_fingerprint") or ""],
            [],
            ["2 · Provision-by-provision comparison"],
            ["#", "Law Name", "Article / Section", "Indicator ID", "Found by", "Indicator differs?",
             "Citation differs?", "Quoted words differ?", "How they differ — one line"],
        ]
        for row in result["rows"]:
            rows.append([
                row["number"], row["law"], row["article"], row["indicator"],
                {"Both": "Both", "Model A only": "Engine A only", "Model B only": "Engine B only"}[row["found_by"]],
                *[("Yes" if row[flag] else "No") if row["found_by"] == "Both" else "—"
                  for flag in ("indicator_differs", "citation_differs", "quote_differs")],
                row["how"],
            ])
        rows += [
            [],
            ["3 · Indicator scores (Zone-3)"],
            ["Indicator ID", "Engine A deterministic", "Engine A effective", "Engine B deterministic",
             "Engine B effective", "Master gold", "Deterministic agrees?", "Effective agrees?"],
        ]
        for entry in result["scores"]:
            ea, eb = entry.get("model_a") or {}, entry.get("model_b") or {}
            rows.append([
                entry["indicator"], _score(ea.get("deterministic")), _score(ea.get("effective")),
                _score(eb.get("deterministic")), _score(eb.get("effective")),
                _score(ea.get("master_gold") if ea else eb.get("master_gold")),
                {True: "Yes", False: "No", None: "—"}[entry["deterministic_agrees"]],
                {True: "Yes", False: "No", None: "—"}[entry["effective_agrees"]],
            ])
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        response = HttpResponse(("﻿" + buffer.getvalue()).encode("utf-8"), content_type="text/csv; charset=utf-8")
        slug = f"{economy.lower().replace(' ', '_')}_p{pillar}"
        response["Content-Disposition"] = f'attachment; filename="clausechain_engine_comparison_{slug}.csv"'
        return response
