#!/bin/zsh
# A4 final sweep: all six economy×pillar runs on current code -> eval -> consolidate -> zone3.
cd "$(dirname "$0")/.."
set -e
for run in "Singapore 6" "Singapore 7" "Malaysia 6" "Malaysia 7" "Australia 6" "Australia 7"; do
  economy=${run% *}; pillar=${run#* }
  cc=$(echo $economy | cut -c1-2 | tr 'A-Z' 'a-z')
  echo "=== $economy P$pillar ==="
  .venv/bin/python run.py --economy $economy --pillar $pillar --out outputs/final_${cc}_p${pillar}
  .venv/bin/python scripts/eval_vs_master.py --output outputs/final_${cc}_p${pillar}/output.csv \
      --economy $economy --pillar $pillar | grep recall || true
done
.venv/bin/python scripts/consolidate_submission.py \
  outputs/final_si_p6 outputs/final_si_p7 outputs/final_ma_p6 outputs/final_ma_p7 \
  outputs/final_au_p6 outputs/final_au_p7
.venv/bin/python scripts/zone3_score.py \
  outputs/final_si_p6 outputs/final_si_p7 outputs/final_ma_p6 outputs/final_ma_p7 \
  outputs/final_au_p6 outputs/final_au_p7
.venv/bin/python scripts/export_review_md.py outputs/final_si_p6 outputs/final_si_p7 \
  outputs/final_ma_p6 outputs/final_ma_p7 outputs/final_au_p6 outputs/final_au_p7
echo "SWEEP COMPLETE"
