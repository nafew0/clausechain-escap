#!/bin/zsh
cd "$(dirname "$0")/.."
set -e
for run in "Malaysia 6" "Malaysia 7" "Australia 6" "Australia 7"; do
  economy=${run% *}; pillar=${run#* }
  cc=$(echo $economy | cut -c1-2 | tr 'A-Z' 'a-z')
  echo "=== $economy P$pillar ==="
  .venv/bin/python run.py --economy $economy --pillar $pillar --out outputs/final_${cc}_p${pillar}
  .venv/bin/python scripts/eval_vs_master.py --output outputs/final_${cc}_p${pillar}/output.csv \
      --economy $economy --pillar $pillar || true
done
.venv/bin/python scripts/consolidate_submission.py \
  outputs/final_si_p6 outputs/final_si_p7 outputs/final_ma_p6 outputs/final_ma_p7 \
  outputs/final_au_p6 outputs/final_au_p7
.venv/bin/python scripts/adjudicate_recall.py \
  outputs/final_si_p6 outputs/final_si_p7 outputs/final_ma_p6 outputs/final_ma_p7 \
  outputs/final_au_p6 outputs/final_au_p7
.venv/bin/python scripts/export_review_md.py outputs/final_si_p6 outputs/final_si_p7 \
  outputs/final_ma_p6 outputs/final_ma_p7 outputs/final_au_p6 outputs/final_au_p7
.venv/bin/python scripts/build_review_bundle.py
echo "CANDIDATE SWEEP COMPLETE — NO FINAL ARTIFACT CREATED"
