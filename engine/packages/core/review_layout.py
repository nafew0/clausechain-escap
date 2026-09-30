"""Where one model backend's review inputs live.

The engine is one pipeline with two model backends. Hybrid (Model A) keeps the
historical paths the signed ESCAP snapshot is built from. Local (Model B, the
open-weights model) mirrors every one of them in a separate ``local`` location,
so the two review workspaces never share a file, a decision or a key:

  artifact                hybrid                          local
  run outputs             outputs/final_*                 outputs/local_*
  refuter verdicts        data/review/refutation_<run>    (same pattern, local_* run names)
  recall adjudication     data/review/                    data/review/local/
  decisions files         data/review/                    data/review/local/
  zone-3 suggestions      data/zone3/                     data/zone3/local/
  candidates + bundle     submission/                     submission/local/
  champion report         reports/                        reports/local/

The review scripts read ``current()``; the mode comes from
``CLAUSECHAIN_REVIEW_MODE=local`` (default hybrid), which prepare_review_inputs.py
and the app's importer set. Local finding, recall and review keys are
namespaced so an identical provision found by both models still has two keys.
The corpus, the gold (known_index) and the rubrics are shared.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MODE_ENV = "CLAUSECHAIN_REVIEW_MODE"
ECONOMY_CODES = ("si", "ma", "au", "th", "in", "id", "ru", "mn", "la", "tl")
ROUND1_CODES = ("si", "ma", "au")
ECONOMY_BY_CODE = {"si": "Singapore", "ma": "Malaysia", "au": "Australia",
                   "th": "Thailand", "in": "India", "id": "Indonesia",
                   "ru": "Russian Federation", "mn": "Mongolia", "la": "Lao PDR",
                   "tl": "Timor-Leste"}

# The signed hybrid snapshot requires these runs.
HYBRID_RUNS = [
    "final_si_p6", "final_si_p7", "final_ma_p6", "final_ma_p7", "final_au_p6", "final_au_p7",
    "final_r2_th_p6", "final_r2_th_p7", "final_r2_in_p6", "final_r2_in_p7",
    "final_r2_id_p6", "final_r2_id_p7",
]
# Later round-2 economies join the hybrid snapshot once their run has an output,
# so adding an economy never breaks the snapshot that is already signed.
OPTIONAL_HYBRID_CODES = ("ru", "mn", "la", "tl")
# Pillar 2 (public procurement) runs, any economy: final_r2_<code>_p2 / local_<code>_p2.
OPTIONAL_PILLARS = (2,)


def _has_output(base: Path, run: str) -> bool:
    output = base / run / "output.json"
    return output.is_file() and output.stat().st_size > 0


def hybrid_runs(root: Path | str = ".") -> list[str]:
    base = Path(root) / "outputs"
    return HYBRID_RUNS + [
        f"final_r2_{code}_p{pillar}"
        for code in OPTIONAL_HYBRID_CODES for pillar in (6, 7)
        if _has_output(base, f"final_r2_{code}_p{pillar}")
    ] + [
        f"final_r2_{code}_p{pillar}"
        for code in ECONOMY_CODES for pillar in OPTIONAL_PILLARS
        if _has_output(base, f"final_r2_{code}_p{pillar}")
    ]


def mode() -> str:
    return "local" if os.getenv(MODE_ENV) == "local" else "hybrid"


def key_namespace() -> str:
    """Salt for finding/recall keys: empty for hybrid, so its keys never change."""
    return "local" if mode() == "local" else ""


def namespaced(payload: str) -> str:
    namespace = key_namespace()
    return f"{namespace}\x1f{payload}" if namespace else payload


def local_runs(root: Path | str = ".") -> list[str]:
    """Local run folders that hold an output, in economy then pillar order."""
    base = Path(root) / "outputs"
    return [
        f"local_{code}_p{pillar}"
        for code in ECONOMY_CODES for pillar in (6, 7, *OPTIONAL_PILLARS)
        if _has_output(base, f"local_{code}_p{pillar}")
    ]


def run_code(run: str) -> str:
    """"final_r2_th_p6" -> "th"; "local_si_p7" -> "si"."""
    return run.rsplit("_p", 1)[0].rsplit("_", 1)[-1]


@dataclass(frozen=True)
class Layout:
    mode: str
    runs: tuple[str, ...]
    provider_profile: str
    submission_dir: Path
    review_dir: Path
    zone3_dir: Path
    reports_dir: Path

    @property
    def round1_runs(self) -> list[str]:
        # The signed Round-1 runs only (final_si_p6 ...); a later final_r2_si_p2
        # Pillar-2 run is not part of the Round-1 recall/champion baseline.
        return [run for run in self.runs
                if run_code(run) in ROUND1_CODES and not run.startswith("final_r2_")]

    @property
    def consolidated(self) -> Path:
        return self.submission_dir / "consolidated.json"

    @property
    def bundle_dir(self) -> Path:
        return self.submission_dir / "review"

    @property
    def decisions_template(self) -> Path:
        return self.bundle_dir / "decisions.template.json"

    @property
    def recall_adjudication(self) -> Path:
        return self.review_dir / "recall_adjudication.json"

    @property
    def champion_report(self) -> Path:
        return self.reports_dir / "champion_validation.json"

    def run_dir(self, run: str) -> Path:
        return Path("outputs") / run

    def refutation(self, run: str) -> Path:
        return Path("data/review") / f"refutation_{run}.json"


def current(root: Path | str = ".") -> Layout:
    if mode() == "local":
        return Layout(
            mode="local",
            runs=tuple(local_runs(root)),
            provider_profile="local_openweights",
            submission_dir=Path("submission/local"),
            review_dir=Path("data/review/local"),
            zone3_dir=Path("data/zone3/local"),
            reports_dir=Path("reports/local"),
        )
    return Layout(
        mode="hybrid",
        runs=tuple(hybrid_runs(root)),
        provider_profile="hybrid_accuracy",
        submission_dir=Path("submission"),
        review_dir=Path("data/review"),
        zone3_dir=Path("data/zone3"),
        reports_dir=Path("reports"),
    )
