from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.extractors.metrics import cer, citation_token_accuracy, section_structure_accuracy, wer  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/extraction_gold_v1.json")
    data = json.loads(path.read_text())
    if len(data.get("pages", [])) < 30 or not all(p.get("human_checked") for p in data["pages"]):
        raise SystemExit("benchmark refused: 30 pages with named human sign-off are required")
    metrics = []
    for page in data["pages"]:
        ref, hyp = page["human_transcription"], page["extracted_text"]
        metrics.append({"cer": cer(ref, hyp), "wer": wer(ref, hyp),
                        "citation_token_accuracy": citation_token_accuracy(ref, hyp),
                        "structure_accuracy": section_structure_accuracy(
                            page["human_structure_labels"], page["extracted_structure_labels"])})
    summary = {name: sum(m[name] for m in metrics) / len(metrics) for name in metrics[0]}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/extraction_benchmark.json").write_text(json.dumps({"pages": metrics, "summary": summary}, indent=2))
    print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
